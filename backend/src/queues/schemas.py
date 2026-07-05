"""
Queue domain — Pydantic schemas.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─── Retry Policy Schemas ────────────────────────────────────
class CreateRetryPolicyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    strategy: str = Field(default="exponential", pattern=r"^(fixed|linear|exponential)$")
    base_delay_ms: int = Field(default=1000, ge=100, le=3600000)
    max_delay_ms: int = Field(default=300000, ge=1000, le=86400000)
    multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    jitter: float = Field(default=0.2, ge=0.0, le=1.0)


class RetryPolicyResponse(BaseModel):
    id: uuid.UUID
    name: str
    strategy: str
    base_delay_ms: int
    max_delay_ms: int
    multiplier: float
    jitter: float
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Queue Schemas ───────────────────────────────────────────
class CreateQueueRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    description: str = Field(default="", max_length=1000)
    priority: int = Field(default=5, ge=1, le=10)
    concurrency_limit: int = Field(default=10, ge=1, le=1000)
    max_retries: int = Field(default=3, ge=0, le=50)
    retry_policy_id: Optional[uuid.UUID] = None
    rate_limit_per_second: Optional[int] = Field(default=None, ge=1, le=10000)


class UpdateQueueRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    priority: Optional[int] = Field(None, ge=1, le=10)
    concurrency_limit: Optional[int] = Field(None, ge=1, le=1000)
    max_retries: Optional[int] = Field(None, ge=0, le=50)
    retry_policy_id: Optional[uuid.UUID] = None
    rate_limit_per_second: Optional[int] = Field(None, ge=1, le=10000)


class QueueResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    slug: str
    description: str
    priority: int
    concurrency_limit: int
    max_retries: int
    retry_policy_id: Optional[uuid.UUID]
    is_paused: bool
    rate_limit_per_second: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QueueStatsResponse(BaseModel):
    queue_id: uuid.UUID
    queue_name: str
    total_jobs: int
    queued: int
    scheduled: int
    claimed: int
    running: int
    completed: int
    failed: int
    dead: int
    cancelled: int
    avg_duration_ms: Optional[float]
    throughput_per_minute: float
    is_paused: bool


class QueueDetailResponse(QueueResponse):
    stats: Optional[QueueStatsResponse] = None
    retry_policy: Optional[RetryPolicyResponse] = None
