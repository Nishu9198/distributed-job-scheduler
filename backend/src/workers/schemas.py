"""
Worker domain — Schemas.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─── Request Schemas ─────────────────────────────────────────
class RegisterWorkerRequest(BaseModel):
    name: str = Field(..., max_length=255)
    hostname: str = Field(..., max_length=255)
    pid: int
    concurrency: int = Field(default=10, ge=1, le=100)
    queues: list[str] = Field(default_factory=lambda: ["default"])


class HeartbeatRequest(BaseModel):
    active_jobs: int = 0
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None


class ClaimJobsRequest(BaseModel):
    queue_id: uuid.UUID
    batch_size: int = Field(default=1, ge=1, le=50)


class CompleteJobRequest(BaseModel):
    job_id: uuid.UUID
    execution_id: uuid.UUID
    success: bool
    result: Optional[dict] = None
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None


# ─── Response Schemas ────────────────────────────────────────
class WorkerResponse(BaseModel):
    id: uuid.UUID
    name: str
    hostname: str
    pid: int
    status: str
    concurrency: int
    queues: Optional[list[str]]
    started_at: datetime
    last_heartbeat_at: Optional[datetime]
    stopped_at: Optional[datetime]

    model_config = {"from_attributes": True}


class WorkerDetailResponse(WorkerResponse):
    active_job_count: int = 0
    total_processed: int = 0


class WorkerHeartbeatResponse(BaseModel):
    id: int
    worker_id: uuid.UUID
    timestamp: datetime
    active_jobs: int
    cpu_usage: Optional[float]
    memory_usage: Optional[float]

    model_config = {"from_attributes": True}
