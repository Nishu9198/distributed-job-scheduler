"""
Metrics domain — Dashboard aggregation service and router.

Provides aggregated metrics for the dashboard including:
- System-wide job counts by status
- Throughput over time (jobs/minute, jobs/hour)
- Per-queue performance metrics
- Worker utilization
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.dlq import DeadLetterQueueEntry
from src.jobs import Job, JobExecution
from src.queues import Queue
from src.workers import Worker


# ─── Schemas ─────────────────────────────────────────────────
class SystemMetrics(BaseModel):
    total_jobs: int
    total_queues: int
    total_workers: int
    active_workers: int
    jobs_by_status: dict[str, int]
    dlq_unresolved: int
    throughput_per_minute: float
    throughput_per_hour: float
    avg_execution_ms: Optional[float]
    success_rate: float


class ThroughputPoint(BaseModel):
    timestamp: str
    completed: int
    failed: int


class ThroughputResponse(BaseModel):
    interval: str
    points: list[ThroughputPoint]


class QueueMetrics(BaseModel):
    queue_id: uuid.UUID
    queue_name: str
    queued: int
    running: int
    completed: int
    failed: int
    dead: int
    avg_duration_ms: Optional[float]
    throughput_per_minute: float
    is_paused: bool


# ─── Service ─────────────────────────────────────────────────
class MetricsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_metrics(self) -> SystemMetrics:
        """Aggregate system-wide metrics for the dashboard."""
        now = datetime.now(timezone.utc)

        # Job counts by status
        status_result = await self.db.execute(
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
            )
        )
        row = status_result.one()

        # Queue count
        queue_count = await self.db.execute(select(func.count()).select_from(Queue))
        total_queues = queue_count.scalar() or 0

        # Worker counts
        worker_result = await self.db.execute(
            select(
                func.count().label("total"),
                func.count().filter(Worker.status.in_(["idle", "busy"])).label("active"),
            )
        )
        worker_row = worker_result.one()

        # DLQ unresolved
        dlq_count = await self.db.execute(
            select(func.count()).where(DeadLetterQueueEntry.resolved_at.is_(None))
        )
        dlq_unresolved = dlq_count.scalar() or 0

        # Throughput (last minute)
        one_min_ago = now - timedelta(minutes=1)
        tpm_result = await self.db.execute(
            select(func.count()).where(
                Job.status == "completed",
                Job.completed_at >= one_min_ago,
            )
        )
        tpm = tpm_result.scalar() or 0

        # Throughput (last hour)
        one_hour_ago = now - timedelta(hours=1)
        tph_result = await self.db.execute(
            select(func.count()).where(
                Job.status == "completed",
                Job.completed_at >= one_hour_ago,
            )
        )
        tph = tph_result.scalar() or 0

        # Average execution time
        avg_result = await self.db.execute(
            select(func.avg(JobExecution.duration_ms)).where(
                JobExecution.status == "completed",
            )
        )
        avg_ms = avg_result.scalar()

        # Success rate
        completed = row.completed or 0
        failed = row.failed or 0
        dead = row.dead or 0
        total_finished = completed + failed + dead
        success_rate = (completed / total_finished * 100) if total_finished > 0 else 100.0

        return SystemMetrics(
            total_jobs=row.total,
            total_queues=total_queues,
            total_workers=worker_row.total,
            active_workers=worker_row.active,
            jobs_by_status={
                "queued": row.queued,
                "scheduled": row.scheduled,
                "claimed": row.claimed,
                "running": row.running,
                "completed": row.completed,
                "failed": row.failed,
                "dead": row.dead,
                "cancelled": row.cancelled,
            },
            dlq_unresolved=dlq_unresolved,
            throughput_per_minute=float(tpm),
            throughput_per_hour=float(tph),
            avg_execution_ms=float(avg_ms) if avg_ms else None,
            success_rate=round(success_rate, 2),
        )

    async def get_throughput(
        self, interval: str = "minute", periods: int = 60
    ) -> ThroughputResponse:
        """Get throughput time series data."""
        now = datetime.now(timezone.utc)

        if interval == "minute":
            delta = timedelta(minutes=1)
        elif interval == "hour":
            delta = timedelta(hours=1)
        else:
            delta = timedelta(minutes=1)

        points = []
        for i in range(periods - 1, -1, -1):
            start = now - delta * (i + 1)
            end = now - delta * i

            completed_count = await self.db.execute(
                select(func.count()).where(
                    Job.status == "completed",
                    Job.completed_at >= start,
                    Job.completed_at < end,
                )
            )
            failed_count = await self.db.execute(
                select(func.count()).where(
                    Job.status.in_(["failed", "dead"]),
                    Job.updated_at >= start,
                    Job.updated_at < end,
                )
            )

            points.append(
                ThroughputPoint(
                    timestamp=start.isoformat(),
                    completed=completed_count.scalar() or 0,
                    failed=failed_count.scalar() or 0,
                )
            )

        return ThroughputResponse(interval=interval, points=points)

    async def get_queue_metrics(self) -> list[QueueMetrics]:
        """Get per-queue metrics summary."""
        result = await self.db.execute(
            select(Queue).order_by(Queue.priority.desc())
        )
        queues = result.scalars().all()
        now = datetime.now(timezone.utc)
        one_min_ago = now - timedelta(minutes=1)

        metrics = []
        for q in queues:
            counts = await self.db.execute(
                select(
                    func.count().filter(Job.status == "queued").label("queued"),
                    func.count().filter(Job.status == "running").label("running"),
                    func.count().filter(Job.status == "completed").label("completed"),
                    func.count().filter(Job.status == "failed").label("failed"),
                    func.count().filter(Job.status == "dead").label("dead"),
                ).where(Job.queue_id == q.id)
            )
            row = counts.one()

            avg_result = await self.db.execute(
                select(func.avg(JobExecution.duration_ms))
                .join(Job, JobExecution.job_id == Job.id)
                .where(Job.queue_id == q.id, JobExecution.status == "completed")
            )
            avg_ms = avg_result.scalar()

            tpm_result = await self.db.execute(
                select(func.count()).where(
                    Job.queue_id == q.id,
                    Job.status == "completed",
                    Job.completed_at >= one_min_ago,
                )
            )
            tpm = tpm_result.scalar() or 0

            metrics.append(
                QueueMetrics(
                    queue_id=q.id,
                    queue_name=q.name,
                    queued=row.queued,
                    running=row.running,
                    completed=row.completed,
                    failed=row.failed,
                    dead=row.dead,
                    avg_duration_ms=float(avg_ms) if avg_ms else None,
                    throughput_per_minute=float(tpm),
                    is_paused=q.is_paused,
                )
            )

        return metrics
