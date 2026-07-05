"""
DLQ domain — Service layer.
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError
from src.dlq import DeadLetterQueueEntry
from src.dlq.schemas import DLQEntryResponse, DLQListResponse
from src.jobs import Job
from src.jobs.lifecycle import validate_transition

logger = structlog.get_logger()


class DLQService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_queue(self, queue_id: uuid.UUID) -> DLQListResponse:
        """List all DLQ entries for a queue."""
        result = await self.db.execute(
            select(DeadLetterQueueEntry)
            .where(DeadLetterQueueEntry.queue_id == queue_id)
            .order_by(DeadLetterQueueEntry.moved_at.desc())
        )
        entries = result.scalars().all()

        unresolved_count = await self.db.execute(
            select(func.count()).where(
                DeadLetterQueueEntry.queue_id == queue_id,
                DeadLetterQueueEntry.resolved_at.is_(None),
            )
        )
        unresolved = unresolved_count.scalar() or 0

        return DLQListResponse(
            items=[DLQEntryResponse.model_validate(e) for e in entries],
            total=len(entries),
            unresolved=unresolved,
        )

    async def list_all(self) -> DLQListResponse:
        """List all DLQ entries across all queues."""
        result = await self.db.execute(
            select(DeadLetterQueueEntry)
            .order_by(DeadLetterQueueEntry.moved_at.desc())
            .limit(200)
        )
        entries = result.scalars().all()

        unresolved_count = await self.db.execute(
            select(func.count()).where(
                DeadLetterQueueEntry.resolved_at.is_(None),
            )
        )
        unresolved = unresolved_count.scalar() or 0

        return DLQListResponse(
            items=[DLQEntryResponse.model_validate(e) for e in entries],
            total=len(entries),
            unresolved=unresolved,
        )

    async def retry_entry(
        self, dlq_id: uuid.UUID, user_id: uuid.UUID
    ) -> DLQEntryResponse:
        """Retry a dead job from the DLQ."""
        result = await self.db.execute(
            select(DeadLetterQueueEntry).where(DeadLetterQueueEntry.id == dlq_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise NotFoundError("DLQ Entry", str(dlq_id))

        if entry.resolved_at is not None:
            raise ConflictError("This DLQ entry has already been resolved")

        # Re-queue the job
        job_result = await self.db.execute(
            select(Job).where(Job.id == entry.job_id)
        )
        job = job_result.scalar_one_or_none()
        if not job:
            raise NotFoundError("Job", str(entry.job_id))

        now = datetime.now(timezone.utc)
        job.status = "queued"
        job.retry_count = 0
        job.worker_id = None
        job.claimed_at = None
        job.started_at = None
        job.completed_at = None
        job.result = None
        job.updated_at = now

        entry.resolved_at = now
        entry.resolved_by = user_id

        await self.db.flush()
        logger.info("dlq_entry_retried", dlq_id=str(dlq_id), job_id=str(entry.job_id))
        return DLQEntryResponse.model_validate(entry)

    async def resolve_entry(
        self, dlq_id: uuid.UUID, user_id: uuid.UUID
    ) -> DLQEntryResponse:
        """Mark a DLQ entry as resolved without retrying."""
        result = await self.db.execute(
            select(DeadLetterQueueEntry).where(DeadLetterQueueEntry.id == dlq_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise NotFoundError("DLQ Entry", str(dlq_id))

        if entry.resolved_at is not None:
            raise ConflictError("This DLQ entry has already been resolved")

        entry.resolved_at = datetime.now(timezone.utc)
        entry.resolved_by = user_id

        await self.db.flush()
        logger.info("dlq_entry_resolved", dlq_id=str(dlq_id))
        return DLQEntryResponse.model_validate(entry)
