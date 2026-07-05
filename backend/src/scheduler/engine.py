"""
Scheduler Engine — Polls for scheduled jobs and moves them to 'queued'.

Runs as an asyncio background task during the FastAPI app lifecycle.
Handles delayed jobs and recurring (cron) jobs.
"""

import asyncio
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_factory
from src.jobs.models import Job
from src.jobs.service import JobService

logger = structlog.get_logger()


class SchedulerEngine:
    def __init__(self, poll_interval: float = 10.0):
        self.poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the scheduler background loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("scheduler_started", interval=self.poll_interval)

    async def stop(self):
        """Stop the scheduler gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("scheduler_stopped")

    async def _run_loop(self):
        while self._running:
            try:
                await self._process_scheduled_jobs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scheduler_error", error=str(e))

            if self._running:
                await asyncio.sleep(self.poll_interval)

    async def _process_scheduled_jobs(self):
        """
        Find jobs where status='scheduled' and scheduled_at <= NOW().
        Update them to 'queued'.
        """
        async with async_session_factory() as session:
            try:
                now = datetime.now(timezone.utc)
                
                # We use FOR UPDATE SKIP LOCKED to ensure multiple schedulers (if deployed)
                # don't conflict, although typically you only run one scheduler.
                # Update status to 'queued' and reset scheduled_at? Actually we keep scheduled_at for record.
                
                query = text("""
                    WITH claimable AS (
                        SELECT id FROM jobs
                        WHERE status = 'scheduled'
                          AND scheduled_at <= :now
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE jobs
                    SET status = 'queued',
                        updated_at = :now
                    WHERE id IN (SELECT id FROM claimable)
                    RETURNING id, type
                """)
                
                result = await session.execute(query, {"now": now})
                rows = result.fetchall()
                
                if rows:
                    logger.info("scheduled_jobs_enqueued", count=len(rows))
                    
                    # Log individually for tracing
                    for row in rows:
                        logger.debug("job_enqueued_from_schedule", job_id=str(row.id), type=row.type)

                await session.commit()
            except Exception:
                await session.rollback()
                raise
