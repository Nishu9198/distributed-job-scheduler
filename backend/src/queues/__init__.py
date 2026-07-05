"""
Queue domain — Queue and RetryPolicy models.

Design decisions:
- Retry policies are separate entities (reusable across queues)
- Queue has is_paused flag for pause/resume functionality
- Concurrency limit enforced at claiming time, not at DB level
- rate_limit_per_second for token-bucket rate limiting
- Priority 1-10 allows queue-level priority ordering
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class RetryPolicy(Base):
    """
    Configurable retry strategy.

    Strategies:
    - fixed: Wait base_delay_ms between each retry
    - linear: Wait base_delay_ms * attempt_number
    - exponential: Wait base_delay_ms * (multiplier ^ (attempt - 1))

    Jitter is added (±jitter%) to prevent thundering herd on retries.
    """

    __tablename__ = "retry_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    strategy: Mapped[str] = mapped_column(
        Enum("fixed", "linear", "exponential", name="retry_strategy", create_constraint=True),
        nullable=False,
        default="exponential",
    )
    base_delay_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    max_delay_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=300000)  # 5 min
    multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    jitter: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)  # ±20%
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    queues = relationship("Queue", back_populates="retry_policy")

    def __repr__(self) -> str:
        return f"<RetryPolicy {self.name} strategy={self.strategy}>"


class Queue(Base):
    """
    Job queue with configurable priority, concurrency, retry, and rate limiting.

    The queue is the primary unit of work organization. Jobs are enqueued into
    a queue and workers poll specific queues for jobs to process.
    """

    __tablename__ = "queues"
    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_queue_project_slug"),
        Index("ix_queue_active_priority", "is_paused", "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)

    # Queue configuration
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)  # 1-10
    concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_policy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("retry_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rate_limit_per_second: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    project = relationship("Project", back_populates="queues")
    retry_policy = relationship("RetryPolicy", back_populates="queues", lazy="selectin")
    jobs = relationship("Job", back_populates="queue", lazy="noload")
    dlq_entries = relationship("DeadLetterQueueEntry", back_populates="queue", lazy="noload")

    def __repr__(self) -> str:
        return f"<Queue {self.slug} priority={self.priority} paused={self.is_paused}>"
