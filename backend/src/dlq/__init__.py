"""
Dead Letter Queue domain — DeadLetterQueueEntry model.

Design decisions:
- DLQ entries store the original payload separately (jobs may be modified on retry)
- failure_summary is AI-generated from error patterns for quick triage
- resolved_by tracks who manually resolved/retried the failed job
- moved_at vs resolved_at allows tracking DLQ residence time
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class DeadLetterQueueEntry(Base):
    """
    Permanent storage for jobs that exhausted all retry attempts.

    DLQ entries preserve the original job state and provide
    AI-generated failure summaries for quick triage by operators.
    """

    __tablename__ = "dead_letter_queue"
    __table_args__ = (
        Index("ix_dlq_queue_moved", "queue_id", "moved_at"),
        Index("ix_dlq_unresolved", "resolved_at", postgresql_where="resolved_at IS NULL"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queues.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Preserved original state
    original_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    failure_reason: Mapped[str] = mapped_column(Text, nullable=False)
    failure_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # AI-generated
    last_error_traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps
    moved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    job = relationship("Job", lazy="selectin")
    queue = relationship("Queue", back_populates="dlq_entries")
    resolver = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<DLQEntry job={self.job_id} resolved={self.resolved_at is not None}>"
