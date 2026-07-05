"""
Job domain — Pydantic schemas.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Request Schemas ─────────────────────────────────────────
class CreateJobRequest(BaseModel):
    name: str = Field(default="untitled", max_length=255)
    type: str = Field(default="immediate", pattern=r"^(immediate|delayed|scheduled|recurring)$")
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=1, le=10)
    max_retries: Optional[int] = None  # Inherits from queue if None
    idempotency_key: Optional[str] = Field(None, max_length=255)
    scheduled_at: Optional[datetime] = None  # Required for delayed/scheduled
    cron_expression: Optional[str] = Field(None, max_length=100)  # Required for recurring


class BatchCreateJobRequest(BaseModel):
    jobs: list[CreateJobRequest] = Field(..., min_length=1, max_length=1000)


class RetryJobRequest(BaseModel):
    reset_retry_count: bool = Field(default=False)


# ─── Response Schemas ────────────────────────────────────────
class JobExecutionResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: Optional[uuid.UUID]
    attempt_number: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    error_message: Optional[str]
    error_traceback: Optional[str]

    model_config = {"from_attributes": True}


class JobLogResponse(BaseModel):
    id: int
    job_id: uuid.UUID
    execution_id: Optional[uuid.UUID]
    level: str
    message: str
    metadata_: Optional[dict] = Field(None, alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    id: uuid.UUID
    queue_id: uuid.UUID
    name: str
    idempotency_key: Optional[str]
    type: str
    status: str
    payload: dict
    result: Optional[dict]
    priority: int
    max_retries: int
    retry_count: int
    scheduled_at: Optional[datetime]
    cron_expression: Optional[str]
    worker_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime
    claimed_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class JobDetailResponse(JobResponse):
    executions: list[JobExecutionResponse] = []


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class BatchJobResponse(BaseModel):
    created: int
    failed: int
    jobs: list[JobResponse]
    errors: list[dict] = []
