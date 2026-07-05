"""
Job domain — Service layer.

Contains the most critical business logic:
1. Job creation (immediate, delayed, scheduled, recurring)
2. Atomic job claiming using FOR UPDATE SKIP LOCKED
3. Job completion/failure handling with retry logic
4. Batch operations
5. Job lifecycle enforcement
"""

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from croniter import croniter
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
    ConflictError,
    NotFoundError,
    QueuePausedError,
    ValidationError,
)
from src.dlq import DeadLetterQueueEntry
from src.jobs import Job, JobExecution, JobLog
from src.jobs.lifecycle import is_retriable, validate_transition
from src.jobs.schemas import (
    BatchCreateJobRequest,
    BatchJobResponse,
    CreateJobRequest,
    JobDetailResponse,
    JobExecutionResponse,
    JobListResponse,
    JobResponse,
)
from src.queues import Queue, RetryPolicy

logger = structlog.get_logger()


class JobService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Job Creation ────────────────────────────────────────

    async def create(
        self, queue_id: uuid.UUID, data: CreateJobRequest
    ) -> JobResponse:
        """
        Create a new job in the specified queue.
        
        Handles all job types:
        - immediate: Enqueued directly with status 'queued'
        - delayed: Set to 'scheduled' with a future scheduled_at
        - scheduled: Same as delayed (one-time at specific time)
        - recurring: Cron-based, creates first instance as 'scheduled'
        """
        queue = await self._get_queue(queue_id)

        # Validate job type requirements
        if data.type in ("delayed", "scheduled") and not data.scheduled_at:
            raise ValidationError(
                f"scheduled_at is required for '{data.type}' jobs"
            )
        if data.type == "recurring" and not data.cron_expression:
            raise ValidationError(
                "cron_expression is required for 'recurring' jobs"
            )
        if data.cron_expression:
            try:
                croniter(data.cron_expression)
            except (ValueError, KeyError):
                raise ValidationError(
                    f"Invalid cron expression: '{data.cron_expression}'"
                )

        # Check idempotency
        if data.idempotency_key:
            existing = await self.db.execute(
                select(Job).where(
                    Job.queue_id == queue_id,
                    Job.idempotency_key == data.idempotency_key,
                )
            )
            existing_job = existing.scalar_one_or_none()
            if existing_job:
                # Idempotent: return existing job instead of creating duplicate
                return JobResponse.model_validate(existing_job)

        # Determine initial status and scheduled_at
        initial_status = "queued"
        scheduled_at = data.scheduled_at

        if data.type in ("delayed", "scheduled"):
            initial_status = "scheduled"
        elif data.type == "recurring":
            initial_status = "scheduled"
            # Calculate next run time from cron
            cron = croniter(data.cron_expression, datetime.now(timezone.utc))
            scheduled_at = cron.get_next(datetime)

        job = Job(
            queue_id=queue_id,
            name=data.name,
            type=data.type,
            status=initial_status,
            payload=data.payload,
            priority=data.priority,
            max_retries=data.max_retries if data.max_retries is not None else queue.max_retries,
            idempotency_key=data.idempotency_key,
            scheduled_at=scheduled_at,
            cron_expression=data.cron_expression,
        )
        self.db.add(job)
        await self.db.flush()

        logger.info(
            "job_created",
            job_id=str(job.id),
            queue_id=str(queue_id),
            type=data.type,
            status=initial_status,
        )

        return JobResponse.model_validate(job)

    async def batch_create(
        self, queue_id: uuid.UUID, data: BatchCreateJobRequest
    ) -> BatchJobResponse:
        """Create multiple jobs in a single transaction."""
        queue = await self._get_queue(queue_id)
        
        created_jobs = []
        errors = []

        for i, job_data in enumerate(data.jobs):
            try:
                job_response = await self.create(queue_id, job_data)
                created_jobs.append(job_response)
            except Exception as e:
                errors.append({"index": i, "error": str(e)})

        return BatchJobResponse(
            created=len(created_jobs),
            failed=len(errors),
            jobs=created_jobs,
            errors=errors,
        )

    # ─── Job Queries ─────────────────────────────────────────

    async def list_by_queue(
        self,
        queue_id: uuid.UUID,
        status: Optional[str] = None,
        type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> JobListResponse:
        """List jobs with pagination and filtering."""
        query = select(Job).where(Job.queue_id == queue_id)

        if status:
            query = query.where(Job.status == status)
        if type:
            query = query.where(Job.type == type)

        # Count total
        count_query = select(func.count()).select_from(
            query.subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        # Paginate
        query = query.order_by(Job.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        jobs = result.scalars().all()

        return JobListResponse(
            items=[JobResponse.model_validate(j) for j in jobs],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, (total + page_size - 1) // page_size),
        )

    async def get_by_id(self, job_id: uuid.UUID) -> JobDetailResponse:
        """Get job with full execution history."""
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundError("Job", str(job_id))

        # Load executions
        exec_result = await self.db.execute(
            select(JobExecution)
            .where(JobExecution.job_id == job_id)
            .order_by(JobExecution.attempt_number)
        )
        executions = exec_result.scalars().all()

        return JobDetailResponse(
            **JobResponse.model_validate(job).model_dump(),
            executions=[JobExecutionResponse.model_validate(e) for e in executions],
        )

    async def get_logs(
        self, job_id: uuid.UUID, page: int = 1, page_size: int = 100
    ) -> list[dict]:
        """Get execution logs for a job."""
        result = await self.db.execute(
            select(JobLog)
            .where(JobLog.job_id == job_id)
            .order_by(JobLog.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        logs = result.scalars().all()
        return [
            {
                "id": log.id,
                "level": log.level,
                "message": log.message,
                "metadata": log.metadata_,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]

    # ─── Job Lifecycle Operations ────────────────────────────

    async def claim_jobs(
        self,
        queue_id: uuid.UUID,
        worker_id: uuid.UUID,
        batch_size: int = 1,
    ) -> list[JobResponse]:
        """
        Atomically claim jobs for a worker using FOR UPDATE SKIP LOCKED.

        This is THE critical path for the entire system. The query:
        1. Selects queued jobs ordered by priority DESC, created_at ASC
        2. Locks them exclusively (FOR UPDATE) so no other worker can claim
        3. SKIP LOCKED ensures no contention — workers don't wait for each other
        4. Updates status to 'claimed' in a single atomic operation

        The composite index (queue_id, status, priority, created_at) ensures
        this query uses an efficient index scan.
        """
        queue = await self._get_queue(queue_id)
        if queue.is_paused:
            return []

        # Check concurrency limit
        running_count = await self.db.execute(
            select(func.count()).where(
                Job.queue_id == queue_id,
                Job.status.in_(["claimed", "running"]),
            )
        )
        current_running = running_count.scalar() or 0
        available_slots = max(0, queue.concurrency_limit - current_running)
        if available_slots == 0:
            return []

        claim_count = min(batch_size, available_slots)

        # THE ATOMIC CLAIM QUERY — heart of the system
        claimed_jobs = await self.db.execute(
            text("""
                WITH claimable AS (
                    SELECT j.id
                    FROM jobs j
                    WHERE j.queue_id = :queue_id
                      AND j.status = 'queued'
                    ORDER BY j.priority DESC, j.created_at ASC
                    LIMIT :limit
                    FOR UPDATE OF j SKIP LOCKED
                )
                UPDATE jobs
                SET status = 'claimed',
                    claimed_at = NOW(),
                    updated_at = NOW(),
                    worker_id = :worker_id
                WHERE id IN (SELECT id FROM claimable)
                RETURNING id, queue_id, name, idempotency_key, type, status,
                          payload, result, priority, max_retries, retry_count,
                          scheduled_at, cron_expression, worker_id,
                          created_at, updated_at, claimed_at, started_at, completed_at
            """),
            {
                "queue_id": str(queue_id),
                "worker_id": str(worker_id),
                "limit": claim_count,
            },
        )

        rows = claimed_jobs.fetchall()
        if not rows:
            return []

        jobs = []
        for row in rows:
            jobs.append(
                JobResponse(
                    id=row.id,
                    queue_id=row.queue_id,
                    name=row.name,
                    idempotency_key=row.idempotency_key,
                    type=row.type,
                    status=row.status,
                    payload=row.payload,
                    result=row.result,
                    priority=row.priority,
                    max_retries=row.max_retries,
                    retry_count=row.retry_count,
                    scheduled_at=row.scheduled_at,
                    cron_expression=row.cron_expression,
                    worker_id=row.worker_id,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    claimed_at=row.claimed_at,
                    started_at=row.started_at,
                    completed_at=row.completed_at,
                )
            )

        logger.info(
            "jobs_claimed",
            count=len(jobs),
            queue_id=str(queue_id),
            worker_id=str(worker_id),
        )

        return jobs

    async def start_execution(
        self, job_id: uuid.UUID, worker_id: uuid.UUID
    ) -> JobExecutionResponse:
        """Mark a claimed job as running and create an execution record."""
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundError("Job", str(job_id))

        validate_transition(job.status, "running")

        now = datetime.now(timezone.utc)
        job.status = "running"
        job.started_at = now
        job.updated_at = now

        # Create execution record
        execution = JobExecution(
            job_id=job_id,
            worker_id=worker_id,
            attempt_number=job.retry_count + 1,
            status="running",
            started_at=now,
        )
        self.db.add(execution)
        await self.db.flush()

        return JobExecutionResponse.model_validate(execution)

    async def complete_job(
        self,
        job_id: uuid.UUID,
        execution_id: uuid.UUID,
        result_data: Optional[dict] = None,
    ) -> JobResponse:
        """
        Mark a running job as completed.
        
        For recurring jobs, schedules the next execution.
        """
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundError("Job", str(job_id))

        validate_transition(job.status, "completed")

        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.result = result_data
        job.completed_at = now
        job.updated_at = now

        # Update execution
        exec_result = await self.db.execute(
            select(JobExecution).where(JobExecution.id == execution_id)
        )
        execution = exec_result.scalar_one_or_none()
        if execution:
            execution.status = "completed"
            execution.completed_at = now
            execution.duration_ms = int((now - execution.started_at).total_seconds() * 1000)

        # For recurring jobs, schedule next run
        if job.type == "recurring" and job.cron_expression:
            await self._schedule_next_recurring(job)

        # Add completion log
        log = JobLog(
            job_id=job_id,
            execution_id=execution_id,
            level="info",
            message=f"Job completed successfully (attempt {job.retry_count + 1})",
        )
        self.db.add(log)

        await self.db.flush()

        logger.info("job_completed", job_id=str(job_id))
        return JobResponse.model_validate(job)

    async def fail_job(
        self,
        job_id: uuid.UUID,
        execution_id: uuid.UUID,
        error_message: str,
        error_traceback: Optional[str] = None,
    ) -> JobResponse:
        """
        Handle job failure with retry logic.
        
        If retries remain: re-queue with calculated delay
        If max retries exhausted: move to Dead Letter Queue
        """
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundError("Job", str(job_id))

        validate_transition(job.status, "failed")

        now = datetime.now(timezone.utc)
        job.status = "failed"
        job.retry_count += 1
        job.updated_at = now

        # Update execution
        exec_result = await self.db.execute(
            select(JobExecution).where(JobExecution.id == execution_id)
        )
        execution = exec_result.scalar_one_or_none()
        if execution:
            execution.status = "failed"
            execution.completed_at = now
            execution.duration_ms = int((now - execution.started_at).total_seconds() * 1000)
            execution.error_message = error_message
            execution.error_traceback = error_traceback

        # Add error log
        log = JobLog(
            job_id=job_id,
            execution_id=execution_id,
            level="error",
            message=f"Job failed (attempt {job.retry_count}): {error_message}",
        )
        self.db.add(log)

        # Retry or DLQ
        if job.retry_count < job.max_retries:
            # Calculate retry delay
            delay = await self._calculate_retry_delay(job)
            job.status = "scheduled"
            job.scheduled_at = now + timedelta(milliseconds=delay)

            retry_log = JobLog(
                job_id=job_id,
                level="info",
                message=f"Scheduling retry {job.retry_count + 1}/{job.max_retries} in {delay}ms",
            )
            self.db.add(retry_log)

            logger.info(
                "job_retry_scheduled",
                job_id=str(job_id),
                attempt=job.retry_count,
                delay_ms=delay,
            )
        else:
            # Move to Dead Letter Queue
            job.status = "dead"
            failure_summary = self._generate_failure_summary(error_message, error_traceback)

            dlq_entry = DeadLetterQueueEntry(
                job_id=job_id,
                queue_id=job.queue_id,
                original_payload=job.payload,
                failure_reason=error_message,
                failure_summary=failure_summary,
                last_error_traceback=error_traceback,
                total_attempts=job.retry_count,
            )
            self.db.add(dlq_entry)

            dlq_log = JobLog(
                job_id=job_id,
                level="error",
                message=f"Job moved to Dead Letter Queue after {job.retry_count} failed attempts",
            )
            self.db.add(dlq_log)

            logger.warning(
                "job_moved_to_dlq",
                job_id=str(job_id),
                attempts=job.retry_count,
            )

        await self.db.flush()
        return JobResponse.model_validate(job)

    async def retry_job(self, job_id: uuid.UUID, reset_count: bool = False) -> JobResponse:
        """Manually retry a failed or dead job."""
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundError("Job", str(job_id))

        if not is_retriable(job.status):
            raise ConflictError(
                f"Cannot retry job in '{job.status}' status. Only 'failed' or 'dead' jobs can be retried."
            )

        if reset_count:
            job.retry_count = 0
        job.status = "queued"
        job.worker_id = None
        job.claimed_at = None
        job.started_at = None
        job.completed_at = None
        job.result = None
        job.updated_at = datetime.now(timezone.utc)

        log = JobLog(
            job_id=job_id,
            level="info",
            message=f"Job manually retried (reset_count={reset_count})",
        )
        self.db.add(log)

        await self.db.flush()
        logger.info("job_manually_retried", job_id=str(job_id))
        return JobResponse.model_validate(job)

    async def cancel_job(self, job_id: uuid.UUID) -> JobResponse:
        """Cancel a pending job (queued or scheduled only)."""
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundError("Job", str(job_id))

        validate_transition(job.status, "cancelled")

        job.status = "cancelled"
        job.updated_at = datetime.now(timezone.utc)

        log = JobLog(
            job_id=job_id,
            level="info",
            message="Job cancelled",
        )
        self.db.add(log)

        await self.db.flush()
        return JobResponse.model_validate(job)

    # ─── Private Helpers ─────────────────────────────────────

    async def _get_queue(self, queue_id: uuid.UUID) -> Queue:
        """Get queue or raise NotFoundError."""
        result = await self.db.execute(
            select(Queue).where(Queue.id == queue_id)
        )
        queue = result.scalar_one_or_none()
        if not queue:
            raise NotFoundError("Queue", str(queue_id))
        return queue

    async def _calculate_retry_delay(self, job: Job) -> int:
        """Calculate retry delay based on queue's retry policy."""
        # Load retry policy from queue
        queue = await self._get_queue(job.queue_id)
        
        strategy = "exponential"
        base_delay = 1000
        max_delay = 300000
        multiplier = 2.0
        jitter_pct = 0.2

        if queue.retry_policy:
            policy = queue.retry_policy
            strategy = policy.strategy
            base_delay = policy.base_delay_ms
            max_delay = policy.max_delay_ms
            multiplier = policy.multiplier
            jitter_pct = policy.jitter

        attempt = job.retry_count

        if strategy == "fixed":
            delay = base_delay
        elif strategy == "linear":
            delay = base_delay * attempt
        elif strategy == "exponential":
            delay = base_delay * (multiplier ** (attempt - 1))
        else:
            delay = base_delay

        # Add jitter to prevent thundering herd
        jitter = delay * jitter_pct * (random.random() * 2 - 1)
        delay = max(base_delay, min(delay + jitter, max_delay))

        return int(delay)

    async def _schedule_next_recurring(self, job: Job) -> None:
        """Create the next instance of a recurring job."""
        if not job.cron_expression:
            return

        cron = croniter(job.cron_expression, datetime.now(timezone.utc))
        next_run = cron.get_next(datetime)

        next_job = Job(
            queue_id=job.queue_id,
            name=job.name,
            type="recurring",
            status="scheduled",
            payload=job.payload,
            priority=job.priority,
            max_retries=job.max_retries,
            cron_expression=job.cron_expression,
            scheduled_at=next_run,
        )
        self.db.add(next_job)

        logger.info(
            "recurring_job_scheduled",
            parent_job_id=str(job.id),
            next_run=next_run.isoformat(),
        )

    def _generate_failure_summary(
        self, error_message: str, traceback: Optional[str] = None
    ) -> str:
        """
        Generate an AI-style failure summary from error patterns.
        
        Uses pattern matching to classify common error types and provide
        actionable summaries for operators reviewing the DLQ.
        """
        error_lower = (error_message or "").lower()
        traceback_lower = (traceback or "").lower()

        # Pattern-based classification
        if "timeout" in error_lower or "timed out" in error_lower:
            category = "Timeout Error"
            suggestion = "The job exceeded its execution time limit. Consider increasing the timeout or optimizing the job's workload."
        elif "connection" in error_lower or "connect" in error_lower:
            category = "Connection Error"
            suggestion = "The job failed to connect to an external service. Check network connectivity and service availability."
        elif "memory" in error_lower or "oom" in error_lower:
            category = "Memory Error"
            suggestion = "The job exhausted available memory. Consider processing data in smaller batches."
        elif "permission" in error_lower or "forbidden" in error_lower or "unauthorized" in error_lower:
            category = "Authorization Error"
            suggestion = "The job lacks necessary permissions. Verify API keys and access credentials."
        elif "rate limit" in error_lower or "429" in error_lower or "throttl" in error_lower:
            category = "Rate Limit Error"
            suggestion = "The job was rate-limited by an external service. Implement backoff or reduce request frequency."
        elif "not found" in error_lower or "404" in error_lower:
            category = "Resource Not Found"
            suggestion = "A required resource was not found. Verify the job payload references valid resources."
        elif "syntax" in error_lower or "parse" in error_lower or "json" in error_lower:
            category = "Data Format Error"
            suggestion = "The job encountered invalid data format. Validate input data before processing."
        elif "disk" in error_lower or "storage" in error_lower or "space" in error_lower:
            category = "Storage Error"
            suggestion = "The job ran out of disk space. Free up storage or increase allocation."
        elif "deadlock" in error_lower:
            category = "Database Deadlock"
            suggestion = "A database deadlock was detected. Review transaction isolation and lock ordering."
        else:
            category = "Unknown Error"
            suggestion = "Review the full error traceback for debugging. Consider adding more specific error handling."

        return f"[{category}] {suggestion}\n\nOriginal error: {error_message[:500]}"
