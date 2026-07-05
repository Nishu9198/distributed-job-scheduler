"""
Worker domain — Service layer.

Handles worker registration, heartbeats, stale worker detection,
and orphaned job recovery.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import NotFoundError
from src.jobs import Job
from src.workers import Worker, WorkerHeartbeat
from src.workers.schemas import (
    HeartbeatRequest,
    RegisterWorkerRequest,
    WorkerDetailResponse,
    WorkerResponse,
)

logger = structlog.get_logger()
settings = get_settings()


class WorkerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: RegisterWorkerRequest) -> WorkerResponse:
        """Register a new worker process."""
        worker = Worker(
            name=data.name,
            hostname=data.hostname,
            pid=data.pid,
            concurrency=data.concurrency,
            queues=data.queues,
            status="idle",
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        self.db.add(worker)
        await self.db.flush()

        logger.info(
            "worker_registered",
            worker_id=str(worker.id),
            name=data.name,
            hostname=data.hostname,
            queues=data.queues,
        )
        return WorkerResponse.model_validate(worker)

    async def heartbeat(
        self, worker_id: uuid.UUID, data: HeartbeatRequest
    ) -> WorkerResponse:
        """
        Process a heartbeat from a worker.
        
        Updates the worker's last_heartbeat_at and status,
        and records system metrics.
        """
        result = await self.db.execute(
            select(Worker).where(Worker.id == worker_id)
        )
        worker = result.scalar_one_or_none()
        if not worker:
            raise NotFoundError("Worker", str(worker_id))

        now = datetime.now(timezone.utc)
        worker.last_heartbeat_at = now
        worker.status = "busy" if data.active_jobs > 0 else "idle"

        # Record heartbeat metrics
        hb = WorkerHeartbeat(
            worker_id=worker_id,
            timestamp=now,
            active_jobs=data.active_jobs,
            cpu_usage=data.cpu_usage,
            memory_usage=data.memory_usage,
        )
        self.db.add(hb)
        await self.db.flush()

        return WorkerResponse.model_validate(worker)

    async def deregister(self, worker_id: uuid.UUID) -> WorkerResponse:
        """Mark a worker as offline (graceful shutdown)."""
        result = await self.db.execute(
            select(Worker).where(Worker.id == worker_id)
        )
        worker = result.scalar_one_or_none()
        if not worker:
            raise NotFoundError("Worker", str(worker_id))

        now = datetime.now(timezone.utc)
        worker.status = "offline"
        worker.stopped_at = now

        # Release any claimed jobs back to queued
        await self.db.execute(
            update(Job)
            .where(Job.worker_id == worker_id, Job.status.in_(["claimed"]))
            .values(status="queued", worker_id=None, claimed_at=None, updated_at=now)
        )

        await self.db.flush()
        logger.info("worker_deregistered", worker_id=str(worker_id))
        return WorkerResponse.model_validate(worker)

    async def set_draining(self, worker_id: uuid.UUID) -> WorkerResponse:
        """Set worker to draining — stop claiming, finish in-flight."""
        result = await self.db.execute(
            select(Worker).where(Worker.id == worker_id)
        )
        worker = result.scalar_one_or_none()
        if not worker:
            raise NotFoundError("Worker", str(worker_id))

        worker.status = "draining"
        await self.db.flush()
        logger.info("worker_draining", worker_id=str(worker_id))
        return WorkerResponse.model_validate(worker)

    async def list_workers(
        self, status_filter: Optional[str] = None
    ) -> list[WorkerDetailResponse]:
        """List all workers with active job counts."""
        query = select(Worker).order_by(Worker.started_at.desc())
        if status_filter:
            query = query.where(Worker.status == status_filter)

        result = await self.db.execute(query)
        workers = result.scalars().all()

        responses = []
        for w in workers:
            # Count active jobs
            active_count = await self.db.execute(
                select(func.count()).where(
                    Job.worker_id == w.id,
                    Job.status.in_(["claimed", "running"]),
                )
            )
            active = active_count.scalar() or 0

            # Count total processed
            total_count = await self.db.execute(
                select(func.count()).where(
                    Job.worker_id == w.id,
                    Job.status.in_(["completed", "failed", "dead"]),
                )
            )
            total = total_count.scalar() or 0

            responses.append(
                WorkerDetailResponse(
                    **WorkerResponse.model_validate(w).model_dump(),
                    active_job_count=active,
                    total_processed=total,
                )
            )
        return responses

    async def get_by_id(self, worker_id: uuid.UUID) -> WorkerDetailResponse:
        """Get detailed worker info."""
        result = await self.db.execute(
            select(Worker).where(Worker.id == worker_id)
        )
        worker = result.scalar_one_or_none()
        if not worker:
            raise NotFoundError("Worker", str(worker_id))

        active_count = await self.db.execute(
            select(func.count()).where(
                Job.worker_id == worker_id,
                Job.status.in_(["claimed", "running"]),
            )
        )
        active = active_count.scalar() or 0

        total_count = await self.db.execute(
            select(func.count()).where(
                Job.worker_id == worker_id,
                Job.status.in_(["completed", "failed", "dead"]),
            )
        )
        total = total_count.scalar() or 0

        return WorkerDetailResponse(
            **WorkerResponse.model_validate(worker).model_dump(),
            active_job_count=active,
            total_processed=total,
        )

    async def detect_stale_workers(self) -> int:
        """
        Detect and handle stale workers.
        
        A worker is stale if its last heartbeat was more than
        WORKER_STALE_THRESHOLD seconds ago. Stale workers are
        marked offline and their claimed jobs are re-queued.
        
        Returns the number of stale workers detected.
        """
        threshold = datetime.now(timezone.utc) - timedelta(
            seconds=settings.WORKER_STALE_THRESHOLD
        )

        # Find stale workers
        result = await self.db.execute(
            select(Worker).where(
                Worker.status.in_(["idle", "busy"]),
                Worker.last_heartbeat_at < threshold,
            )
        )
        stale_workers = result.scalars().all()

        now = datetime.now(timezone.utc)
        for worker in stale_workers:
            worker.status = "offline"
            worker.stopped_at = now

            # Re-queue orphaned jobs from this worker
            orphaned = await self.db.execute(
                update(Job)
                .where(
                    Job.worker_id == worker.id,
                    Job.status.in_(["claimed", "running"]),
                )
                .values(
                    status="queued",
                    worker_id=None,
                    claimed_at=None,
                    started_at=None,
                    updated_at=now,
                )
                .returning(Job.id)
            )
            orphaned_ids = [str(r.id) for r in orphaned.fetchall()]

            if orphaned_ids:
                logger.warning(
                    "orphaned_jobs_recovered",
                    worker_id=str(worker.id),
                    job_ids=orphaned_ids,
                    count=len(orphaned_ids),
                )

        if stale_workers:
            await self.db.flush()
            logger.warning(
                "stale_workers_detected",
                count=len(stale_workers),
                worker_ids=[str(w.id) for w in stale_workers],
            )

        return len(stale_workers)
