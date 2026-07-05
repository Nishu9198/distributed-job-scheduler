"""
Worker domain — Worker and WorkerHeartbeat models.

Design decisions:
- Workers self-register with hostname + PID for identification
- Status enum tracks lifecycle: idle → busy → draining (graceful shutdown) → offline
- Heartbeats are separate table for time-series data (could be partitioned at scale)
- Active worker partial index avoids scanning offline workers
- Workers store which queues they listen to as a TEXT array
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Worker(Base):
    """
    Represents a worker process that polls and executes jobs.

    Workers register themselves on startup and send periodic heartbeats.
    If a heartbeat is not received within the stale threshold, the worker
    is marked as offline and its claimed jobs are re-queued.
    """

    __tablename__ = "workers"
    __table_args__ = (
        # Only index active workers — offline workers are historical data
        Index(
            "ix_worker_active",
            "status",
            postgresql_where="status != 'offline'",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("idle", "busy", "draining", "offline", name="worker_status", create_constraint=True),
        nullable=False,
        default="idle",
    )
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    queues: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stopped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    heartbeats = relationship("WorkerHeartbeat", back_populates="worker", lazy="noload")
    jobs = relationship("Job", back_populates="worker", lazy="noload")

    def __repr__(self) -> str:
        return f"<Worker {self.name} status={self.status} host={self.hostname}>"


class WorkerHeartbeat(Base):
    """
    Time-series heartbeat data from workers.

    Captures system metrics at each heartbeat interval for monitoring
    and alerting. Uses BIGSERIAL for efficient sequential writes.
    """

    __tablename__ = "worker_heartbeats"
    __table_args__ = (
        Index("ix_heartbeat_worker_time", "worker_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    worker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workers.id", ondelete="CASCADE"),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    active_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cpu_usage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_usage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    worker = relationship("Worker", back_populates="heartbeats")

    def __repr__(self) -> str:
        return f"<WorkerHeartbeat worker={self.worker_id} jobs={self.active_jobs}>"
