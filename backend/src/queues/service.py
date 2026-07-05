"""
Queue domain — Service layer.

Handles queue CRUD, pause/resume, and real-time statistics computation.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DuplicateError, NotFoundError, QueuePausedError
from src.jobs import Job, JobExecution
from src.queues import Queue, RetryPolicy
from src.queues.schemas import (
    CreateQueueRequest,
    CreateRetryPolicyRequest,
    QueueDetailResponse,
    QueueResponse,
    QueueStatsResponse,
    RetryPolicyResponse,
    UpdateQueueRequest,
)


class QueueService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Queue CRUD ──────────────────────────────────────────
    async def create(
        self, project_id: uuid.UUID, data: CreateQueueRequest
    ) -> QueueResponse:
        """Create a new queue within a project."""
        result = await self.db.execute(
            select(Queue).where(
                Queue.project_id == project_id,
                Queue.slug == data.slug,
            )
        )
        if result.scalar_one_or_none():
            raise DuplicateError("Queue", "slug", data.slug)

        queue = Queue(
            project_id=project_id,
            name=data.name,
            slug=data.slug,
            description=data.description,
            priority=data.priority,
            concurrency_limit=data.concurrency_limit,
            max_retries=data.max_retries,
            retry_policy_id=data.retry_policy_id,
            rate_limit_per_second=data.rate_limit_per_second,
        )
        self.db.add(queue)
        await self.db.flush()
        return QueueResponse.model_validate(queue)

    async def list_by_project(self, project_id: uuid.UUID) -> list[QueueResponse]:
        """List all queues in a project."""
        result = await self.db.execute(
            select(Queue)
            .where(Queue.project_id == project_id)
            .order_by(Queue.priority.desc(), Queue.created_at)
        )
        queues = result.scalars().all()
        return [QueueResponse.model_validate(q) for q in queues]

    async def get_by_id(self, queue_id: uuid.UUID) -> QueueDetailResponse:
        """Get queue with stats and retry policy."""
        result = await self.db.execute(
            select(Queue).where(Queue.id == queue_id)
        )
        queue = result.scalar_one_or_none()
        if not queue:
            raise NotFoundError("Queue", str(queue_id))

        stats = await self.get_stats(queue_id)
        retry_policy = None
        if queue.retry_policy:
            retry_policy = RetryPolicyResponse.model_validate(queue.retry_policy)

        return QueueDetailResponse(
            **QueueResponse.model_validate(queue).model_dump(),
            stats=stats,
            retry_policy=retry_policy,
        )

    async def update(
        self, queue_id: uuid.UUID, data: UpdateQueueRequest
    ) -> QueueResponse:
        """Update queue configuration."""
        result = await self.db.execute(
            select(Queue).where(Queue.id == queue_id)
        )
        queue = result.scalar_one_or_none()
        if not queue:
            raise NotFoundError("Queue", str(queue_id))

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(queue, field, value)

        await self.db.flush()
        return QueueResponse.model_validate(queue)

    async def delete(self, queue_id: uuid.UUID) -> None:
        """Delete a queue (cascades to all jobs)."""
        result = await self.db.execute(
            select(Queue).where(Queue.id == queue_id)
        )
        queue = result.scalar_one_or_none()
        if not queue:
            raise NotFoundError("Queue", str(queue_id))
        await self.db.delete(queue)
        await self.db.flush()

    # ─── Pause / Resume ─────────────────────────────────────
    async def pause(self, queue_id: uuid.UUID) -> QueueResponse:
        """Pause a queue — workers will stop claiming new jobs."""
        result = await self.db.execute(
            select(Queue).where(Queue.id == queue_id)
        )
        queue = result.scalar_one_or_none()
        if not queue:
            raise NotFoundError("Queue", str(queue_id))
        queue.is_paused = True
        await self.db.flush()
        return QueueResponse.model_validate(queue)

    async def resume(self, queue_id: uuid.UUID) -> QueueResponse:
        """Resume a paused queue."""
        result = await self.db.execute(
            select(Queue).where(Queue.id == queue_id)
        )
        queue = result.scalar_one_or_none()
        if not queue:
            raise NotFoundError("Queue", str(queue_id))
        queue.is_paused = False
        await self.db.flush()
        return QueueResponse.model_validate(queue)

    # ─── Statistics ──────────────────────────────────────────
    async def get_stats(self, queue_id: uuid.UUID) -> QueueStatsResponse:
        """Compute real-time queue statistics."""
        result = await self.db.execute(
            select(Queue).where(Queue.id == queue_id)
        )
        queue = result.scalar_one_or_none()
        if not queue:
            raise NotFoundError("Queue", str(queue_id))

        # Count jobs by status using conditional aggregation (single query)
        status_counts = await self.db.execute(
            select(
                func.count().label("total"),
                func.count().filter(Job.status == "queued").label("queued"),
                func.count().filter(Job.status == "scheduled").label("scheduled"),
                func.count().filter(Job.status == "claimed").label("claimed"),
                func.count().filter(Job.status == "running").label("running"),
                func.count().filter(Job.status == "completed").label("completed"),
                func.count().filter(Job.status == "failed").label("failed"),
                func.count().filter(Job.status == "dead").label("dead"),
                func.count().filter(Job.status == "cancelled").label("cancelled"),
            ).where(Job.queue_id == queue_id)
        )
        row = status_counts.one()

        # Average execution duration (last 100 completed executions)
        avg_result = await self.db.execute(
            select(func.avg(JobExecution.duration_ms))
            .join(Job, JobExecution.job_id == Job.id)
            .where(
                Job.queue_id == queue_id,
                JobExecution.status == "completed",
            )
            .limit(100)
        )
        avg_duration = avg_result.scalar()

        # Throughput: completed jobs in last minute
        one_min_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
        throughput_result = await self.db.execute(
            select(func.count())
            .where(
                Job.queue_id == queue_id,
                Job.status == "completed",
                Job.completed_at >= one_min_ago,
            )
        )
        throughput = throughput_result.scalar() or 0

        return QueueStatsResponse(
            queue_id=queue_id,
            queue_name=queue.name,
            total_jobs=row.total,
            queued=row.queued,
            scheduled=row.scheduled,
            claimed=row.claimed,
            running=row.running,
            completed=row.completed,
            failed=row.failed,
            dead=row.dead,
            cancelled=row.cancelled,
            avg_duration_ms=float(avg_duration) if avg_duration else None,
            throughput_per_minute=float(throughput),
            is_paused=queue.is_paused,
        )

    # ─── Retry Policy ───────────────────────────────────────
    async def create_retry_policy(
        self, data: CreateRetryPolicyRequest
    ) -> RetryPolicyResponse:
        """Create a reusable retry policy."""
        policy = RetryPolicy(
            name=data.name,
            strategy=data.strategy,
            base_delay_ms=data.base_delay_ms,
            max_delay_ms=data.max_delay_ms,
            multiplier=data.multiplier,
            jitter=data.jitter,
        )
        self.db.add(policy)
        await self.db.flush()
        return RetryPolicyResponse.model_validate(policy)

    async def list_retry_policies(self) -> list[RetryPolicyResponse]:
        """List all retry policies."""
        result = await self.db.execute(
            select(RetryPolicy).order_by(RetryPolicy.created_at)
        )
        policies = result.scalars().all()
        return [RetryPolicyResponse.model_validate(p) for p in policies]
