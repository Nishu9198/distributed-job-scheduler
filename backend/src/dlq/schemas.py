"""
DLQ domain — Schemas.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DLQEntryResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    queue_id: uuid.UUID
    original_payload: dict
    failure_reason: str
    failure_summary: Optional[str]
    last_error_traceback: Optional[str]
    total_attempts: int
    moved_at: datetime
    resolved_at: Optional[datetime]
    resolved_by: Optional[uuid.UUID]

    model_config = {"from_attributes": True}


class DLQListResponse(BaseModel):
    items: list[DLQEntryResponse]
    total: int
    unresolved: int
