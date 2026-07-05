"""
Worker engine — The standalone worker process.

This module runs as a separate process that:
1. Registers itself with the API
2. Polls queues for available jobs
3. Executes jobs concurrently using asyncio.Semaphore
4. Sends periodic heartbeats
5. Handles SIGTERM/SIGINT for graceful shutdown
6. Detects and recovers orphaned jobs from stale workers

Run with: python -m src.workers.engine
"""

import asyncio
import os
import platform
import signal
import sys
import time
import uuid
from datetime import datetime, timezone

import structlog

from src.core.config import get_settings
from src.core.database import async_session_factory
from src.jobs.service import JobService
from src.workers.schemas import HeartbeatRequest, RegisterWorkerRequest
from src.workers.service import WorkerService

logger = structlog.get_logger()
settings = get_settings()


class WorkerEngine:
    """
    Distributed worker engine that polls, claims, and executes jobs.
    
    Features:
    - Bounded concurrency via asyncio.Semaphore
    - Graceful shutdown on SIGTERM/SIGINT
    - Periodic heartbeats with system metrics
    - Stale worker detection and orphan job recovery
    """

    def __init__(self):
        self.worker_id: uuid.UUID | None = None
        self.concurrency = settings.WORKER_CONCURRENCY
        self.semaphore = asyncio.Semaphore(self.concurrency)
        self.active_jobs: int = 0
        self.shutdown_event = asyncio.Event()
        self.queue_names = settings.WORKER_QUEUES.split(",")
        self.worker_name = f"worker-{platform.node()}-{os.getpid()}"

    async def start(self):
        """Main entry point — register, then run polling + heartbeat loops."""
        logger.info(
            "worker_starting",
            name=self.worker_name,
            concurrency=self.concurrency,
            queues=self.queue_names,
        )

        # Register worker
        async with async_session_factory() as db:
            service = WorkerService(db)
            worker = await service.register(
                RegisterWorkerRequest(
                    name=self.worker_name,
                    hostname=platform.node(),
                    pid=os.getpid(),
                    concurrency=self.concurrency,
                    queues=self.queue_names,
                )
            )
            await db.commit()
            self.worker_id = worker.id

        logger.info("worker_registered", worker_id=str(self.worker_id))

        # Install signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown_signal)

        # Run concurrent tasks
        try:
            await asyncio.gather(
                self._poll_loop(),
                self._heartbeat_loop(),
                self._stale_worker_check_loop(),
                self._scheduler_promotion_loop(),
            )
        except asyncio.CancelledError:
            pass
        finally:
            await self._graceful_shutdown()

    def _handle_shutdown_signal(self):
        """Handle SIGTERM/SIGINT — signal graceful shutdown."""
        logger.info("shutdown_signal_received", worker_id=str(self.worker_id))
        self.shutdown_event.set()

    async def _poll_loop(self):
        """
        Main polling loop — claims and executes jobs.
        
        Respects concurrency limits via semaphore and stops
        when shutdown_event is set.
        """
        while not self.shutdown_event.is_set():
            try:
                # Check if we have capacity
                if self.active_jobs >= self.concurrency:
                    await asyncio.sleep(settings.WORKER_POLL_INTERVAL)
                    continue

                async with async_session_factory() as db:
                    job_service = JobService(db)

                    # Poll each queue the worker is subscribed to
                    for queue_name in self.queue_names:
                        if self.shutdown_event.is_set():
                            break

                        # Resolve queue by name (simplified — in production, cache queue IDs)
                        from sqlalchemy import select
                        from src.queues import Queue

                        result = await db.execute(
                            select(Queue).where(
                                Queue.slug == queue_name,
                                Queue.is_paused == False,
                            )
                        )
                        queue = result.scalar_one_or_none()
                        if not queue:
                            continue

                        # Claim available jobs
                        batch_size = min(
                            5, self.concurrency - self.active_jobs
                        )
                        if batch_size <= 0:
                            break

                        claimed = await job_service.claim_jobs(
                            queue.id, self.worker_id, batch_size
                        )
                        await db.commit()

                        # Execute claimed jobs concurrently
                        for job in claimed:
                            asyncio.create_task(self._execute_job(job))

            except Exception as e:
                logger.error("poll_error", error=str(e), error_type=type(e).__name__)

            # Wait before next poll
            try:
                await asyncio.wait_for(
                    self.shutdown_event.wait(),
                    timeout=settings.WORKER_POLL_INTERVAL,
                )
            except asyncio.TimeoutError:
                pass

    async def _execute_job(self, job):
        """
        Execute a single job within the concurrency semaphore.
        
        This method:
        1. Acquires the semaphore (blocks if at capacity)
        2. Updates job status to 'running'
        3. Simulates job execution (in production, would run actual job handler)
        4. Reports success or failure
        """
        async with self.semaphore:
            self.active_jobs += 1
            execution_id = None

            try:
                async with async_session_factory() as db:
                    job_service = JobService(db)

                    # Start execution
                    execution = await job_service.start_execution(
                        job.id, self.worker_id
                    )
                    await db.commit()
                    execution_id = execution.id

                logger.info(
                    "job_executing",
                    job_id=str(job.id),
                    attempt=execution.attempt_number,
                )

                # ── Execute the actual job ──
                # In a real system, this would dispatch to registered job handlers
                # based on the job name/type. Here we simulate execution.
                result = await self._run_job_handler(job)

                # Report success
                async with async_session_factory() as db:
                    job_service = JobService(db)
                    await job_service.complete_job(job.id, execution_id, result)
                    await db.commit()

                logger.info("job_completed", job_id=str(job.id))

            except Exception as e:
                import traceback

                tb = traceback.format_exc()
                logger.error(
                    "job_failed",
                    job_id=str(job.id),
                    error=str(e),
                )

                # Report failure
                if execution_id:
                    try:
                        async with async_session_factory() as db:
                            job_service = JobService(db)
                            await job_service.fail_job(
                                job.id, execution_id, str(e), tb
                            )
                            await db.commit()
                    except Exception as report_err:
                        logger.error(
                            "failed_to_report_failure",
                            job_id=str(job.id),
                            error=str(report_err),
                        )

            finally:
                self.active_jobs -= 1

    async def _run_job_handler(self, job) -> dict:
        """
        Execute the actual job logic.
        
        In production, this would look up a handler registry based on
        the job name and dispatch accordingly. For this implementation,
        it simulates work based on the job payload.
        """
        payload = job.payload or {}
        
        # Simulate job execution with configurable duration
        duration = payload.get("duration_seconds", 1)
        should_fail = payload.get("should_fail", False)
        fail_message = payload.get("fail_message", "Simulated failure")

        await asyncio.sleep(min(duration, 30))  # Cap at 30s for safety

        if should_fail:
            raise RuntimeError(fail_message)

        return {
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "worker": self.worker_name,
            "input_keys": list(payload.keys()),
        }

    async def _heartbeat_loop(self):
        """Send periodic heartbeats with system metrics."""
        while not self.shutdown_event.is_set():
            try:
                import psutil
                cpu = psutil.cpu_percent()
                mem = psutil.virtual_memory().percent
            except ImportError:
                cpu = None
                mem = None

            try:
                async with async_session_factory() as db:
                    service = WorkerService(db)
                    await service.heartbeat(
                        self.worker_id,
                        HeartbeatRequest(
                            active_jobs=self.active_jobs,
                            cpu_usage=cpu,
                            memory_usage=mem,
                        ),
                    )
                    await db.commit()
            except Exception as e:
                logger.error("heartbeat_error", error=str(e))

            try:
                await asyncio.wait_for(
                    self.shutdown_event.wait(),
                    timeout=settings.WORKER_HEARTBEAT_INTERVAL,
                )
            except asyncio.TimeoutError:
                pass

    async def _stale_worker_check_loop(self):
        """Periodically check for stale workers and recover their jobs."""
        while not self.shutdown_event.is_set():
            try:
                async with async_session_factory() as db:
                    service = WorkerService(db)
                    count = await service.detect_stale_workers()
                    await db.commit()
                    if count > 0:
                        logger.info("stale_workers_cleaned", count=count)
            except Exception as e:
                logger.error("stale_check_error", error=str(e))

            try:
                await asyncio.wait_for(
                    self.shutdown_event.wait(),
                    timeout=60,  # Check every 60 seconds
                )
            except asyncio.TimeoutError:
                pass

    async def _scheduler_promotion_loop(self):
        """
        Promote scheduled jobs that are due to 'queued' status.
        
        This handles both delayed jobs and recurring jobs whose
        scheduled_at time has passed.
        """
        while not self.shutdown_event.is_set():
            try:
                async with async_session_factory() as db:
                    from sqlalchemy import text

                    # Atomically promote due scheduled jobs
                    result = await db.execute(
                        text("""
                            UPDATE jobs
                            SET status = 'queued',
                                updated_at = NOW()
                            WHERE status = 'scheduled'
                              AND scheduled_at <= NOW()
                            RETURNING id
                        """)
                    )
                    promoted = result.fetchall()
                    await db.commit()

                    if promoted:
                        logger.info(
                            "scheduled_jobs_promoted",
                            count=len(promoted),
                            job_ids=[str(r.id) for r in promoted],
                        )
            except Exception as e:
                logger.error("scheduler_promotion_error", error=str(e))

            try:
                await asyncio.wait_for(
                    self.shutdown_event.wait(),
                    timeout=5,  # Check every 5 seconds
                )
            except asyncio.TimeoutError:
                pass

    async def _graceful_shutdown(self):
        """
        Graceful shutdown procedure:
        1. Stop accepting new jobs (draining mode)
        2. Wait for in-flight jobs to complete (with timeout)
        3. Deregister worker
        """
        logger.info(
            "graceful_shutdown_starting",
            worker_id=str(self.worker_id),
            active_jobs=self.active_jobs,
        )

        # Set draining status
        try:
            async with async_session_factory() as db:
                service = WorkerService(db)
                await service.set_draining(self.worker_id)
                await db.commit()
        except Exception:
            pass

        # Wait for in-flight jobs (max 30 seconds)
        for _ in range(30):
            if self.active_jobs == 0:
                break
            logger.info(
                "waiting_for_jobs",
                active=self.active_jobs,
            )
            await asyncio.sleep(1)

        # Deregister
        try:
            async with async_session_factory() as db:
                service = WorkerService(db)
                await service.deregister(self.worker_id)
                await db.commit()
        except Exception as e:
            logger.error("deregister_error", error=str(e))

        logger.info("worker_shutdown_complete", worker_id=str(self.worker_id))


async def main():
    """Entry point for the worker process."""
    engine = WorkerEngine()
    await engine.start()


if __name__ == "__main__":
    asyncio.run(main())
