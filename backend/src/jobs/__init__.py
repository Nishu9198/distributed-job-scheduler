"""
Job domain — Job, JobExecution, and JobLog models.

Design decisions:
- Job status uses a strict enum matching the lifecycle: Queued → Scheduled → Claimed → Running → Completed/Failed/Dead
- JSONB for payload and result: Flexible schema without migrations per job type
- Idempotency key is unique per queue (not globally) — allows same key in different queues
- The HOT PATH index (queue_id, status, priority, created_at) covers the atomic claim query
- Partial index on scheduled_at for efficient scheduled job promotion
- JobExecution tracks each attempt separately (1 job = N executions on retry)
- JobLog provides append-only execution output for debugging
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


# ─── Job Status Enum ─────────────────────────────────────────
JOB_STATUS_ENUM = Enum(
    "queued",
    "scheduled",
    "claimed",
    "running",
    "completed",
    "failed",
    "dead",
    "cancelled",
    name="job_status",
    create_constraint=True,
)

JOB_TYPE_ENUM = Enum(
    "immediate",
    "delayed",
    "scheduled",
    "recurring",
    name="job_type",
    create_constraint=True,
)


class Job(Base):
    """
    Core job entity representing a unit of work.

    Jobs flow through the lifecycle:
    queued → claimed → running → completed
                    ↘ failed → (retry) → queued
                              ↘ (max retries) → dead (DLQ)
    """

    __tablename__ = "jobs"
    __table_args__ = (
        # THE HOT PATH INDEX — covers the atomic claim query:
        # SELECT ... WHERE queue_id = ? AND status = 'queued'
        # ORDER BY priority DESC, created_at ASC
        # FOR UPDATE SKIP LOCKED
        Index("ix_job_claim_path", "queue_id", "status", "priority", "created_at"),
        # Partial index for scheduled job promotion — only index rows that matter
        Index(
            "ix_job_scheduled_due",
            "scheduled_at",
            postgresql_where="status = 'scheduled'",
        ),
        # Idempotency: unique key per queue (allows same key across different queues)
        UniqueConstraint(
            "idempotency_key",
            "queue_id",
            name="uq_job_idempotency_key_queue",
        ),
        # For listing jobs by queue with status filter
        Index("ix_job_queue_status", "queue_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queues.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Job identification
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="untitled")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Job type and status
    type: Mapped[str] = mapped_column(JOB_TYPE_ENUM, nullable=False, default="immediate")
    status: Mapped[str] = mapped_column(JOB_STATUS_ENUM, nullable=False, default="queued")

    # Payload and result (JSONB for flexibility)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Priority and retry
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Scheduling
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cron_expression: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Timestamps for lifecycle tracking
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Worker assignment
    worker_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workers.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    queue = relationship("Queue", back_populates="jobs")
    worker = relationship("Worker", back_populates="jobs", lazy="selectin")
    executions = relationship(
        "JobExecution", back_populates="job", lazy="selectin", order_by="JobExecution.attempt_number"
    )
    logs = relationship("JobLog", back_populates="job", lazy="noload")

    def __repr__(self) -> str:
        return f"<Job {self.id} type={self.type} status={self.status}>"


class JobExecution(Base):
    """
    Records each execution attempt of a job.

    One job may have multiple executions (one per retry attempt).
    This provides full audit trail of every attempt including timing,
    errors, and which worker processed it.
    """

    __tablename__ = "job_executions"
    __table_args__ = (
        Index("ix_execution_job_attempt", "job_id", "attempt_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    worker_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workers.id", ondelete="SET NULL"),
        nullable=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        Enum("running", "completed", "failed", name="execution_status", create_constraint=True),
        nullable=False,
        default="running",
    )

    # Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    job = relationship("Job", back_populates="executions")
    worker = relationship("Worker", lazy="selectin")
    logs = relationship("JobLog", back_populates="execution", lazy="noload")

    def __repr__(self) -> str:
        return f"<JobExecution job={self.job_id} attempt={self.attempt_number} status={self.status}>"


class JobLog(Base):
    """
    Append-only log entries for job execution output.

    Designed for high-throughput writes — uses BIGSERIAL for efficient
    sequential insertion and indexing by job + time.
    """

    __tablename__ = "job_logs"
    __table_args__ = (
        Index("ix_job_log_job_created", "job_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    level: Mapped[str] = mapped_column(
        Enum("debug", "info", "warning", "error", name="log_level", create_constraint=True),
        nullable=False,
        default="info",
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    job = relationship("Job", back_populates="logs")
    execution = relationship("JobExecution", back_populates="logs")

    def __repr__(self) -> str:
        return f"<JobLog job={self.job_id} level={self.level}>"
