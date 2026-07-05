"""
Organization domain — Pydantic schemas.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─── Request Schemas ─────────────────────────────────────────
class CreateOrganizationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    description: str = Field(default="", max_length=1000)


class UpdateOrganizationRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class AddMemberRequest(BaseModel):
    user_id: uuid.UUID
    role: str = Field(default="member", pattern=r"^(owner|admin|member)$")


# ─── Response Schemas ────────────────────────────────────────
class OrgMemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str
    created_at: datetime
    updated_at: datetime
    member_count: int = 0

    model_config = {"from_attributes": True}


class OrganizationDetailResponse(OrganizationResponse):
    members: list[OrgMemberResponse] = []
