"""
Organization domain — API router.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.organizations.schemas import (
    AddMemberRequest,
    CreateOrganizationRequest,
    OrganizationDetailResponse,
    OrganizationResponse,
    OrgMemberResponse,
    UpdateOrganizationRequest,
)
from src.organizations.service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new organization",
)
async def create_organization(
    data: CreateOrganizationRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = OrganizationService(db)
    return await service.create(data, current_user.id)


@router.get(
    "",
    response_model=list[OrganizationResponse],
    summary="List user's organizations",
)
async def list_organizations(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = OrganizationService(db)
    return await service.list_for_user(current_user.id)


@router.get(
    "/{org_id}",
    response_model=OrganizationDetailResponse,
    summary="Get organization details",
)
async def get_organization(
    org_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = OrganizationService(db)
    return await service.get_by_id(org_id)


@router.patch(
    "/{org_id}",
    response_model=OrganizationResponse,
    summary="Update organization",
)
async def update_organization(
    org_id: uuid.UUID,
    data: UpdateOrganizationRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = OrganizationService(db)
    return await service.update(org_id, data, current_user.id)


@router.post(
    "/{org_id}/members",
    response_model=OrgMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add member to organization",
)
async def add_member(
    org_id: uuid.UUID,
    data: AddMemberRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = OrganizationService(db)
    return await service.add_member(org_id, data, current_user.id)
