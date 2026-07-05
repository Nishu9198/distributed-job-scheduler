"""
Organization domain — Service layer.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DuplicateError, ForbiddenError, NotFoundError
from src.organizations import OrgMember, Organization
from src.organizations.schemas import (
    AddMemberRequest,
    CreateOrganizationRequest,
    OrganizationDetailResponse,
    OrganizationResponse,
    OrgMemberResponse,
    UpdateOrganizationRequest,
)


class OrganizationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self, data: CreateOrganizationRequest, user_id: uuid.UUID
    ) -> OrganizationResponse:
        """Create an organization and add the creator as owner."""
        # Check slug uniqueness
        result = await self.db.execute(
            select(Organization).where(Organization.slug == data.slug)
        )
        if result.scalar_one_or_none():
            raise DuplicateError("Organization", "slug", data.slug)

        org = Organization(
            name=data.name,
            slug=data.slug,
            description=data.description,
        )
        self.db.add(org)
        await self.db.flush()

        # Add creator as owner
        member = OrgMember(
            organization_id=org.id,
            user_id=user_id,
            role="owner",
        )
        self.db.add(member)
        await self.db.flush()

        return OrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            description=org.description,
            created_at=org.created_at,
            updated_at=org.updated_at,
            member_count=1,
        )

    async def list_for_user(self, user_id: uuid.UUID) -> list[OrganizationResponse]:
        """List all organizations the user is a member of."""
        result = await self.db.execute(
            select(Organization)
            .join(OrgMember, OrgMember.organization_id == Organization.id)
            .where(OrgMember.user_id == user_id)
            .order_by(Organization.created_at.desc())
        )
        orgs = result.scalars().all()

        responses = []
        for org in orgs:
            count_result = await self.db.execute(
                select(func.count()).select_from(OrgMember).where(
                    OrgMember.organization_id == org.id
                )
            )
            count = count_result.scalar()
            responses.append(
                OrganizationResponse(
                    id=org.id,
                    name=org.name,
                    slug=org.slug,
                    description=org.description,
                    created_at=org.created_at,
                    updated_at=org.updated_at,
                    member_count=count or 0,
                )
            )
        return responses

    async def get_by_id(self, org_id: uuid.UUID) -> OrganizationDetailResponse:
        """Get organization details with members."""
        result = await self.db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = result.scalar_one_or_none()
        if not org:
            raise NotFoundError("Organization", str(org_id))

        members_result = await self.db.execute(
            select(OrgMember).where(OrgMember.organization_id == org_id)
        )
        members = members_result.scalars().all()

        return OrganizationDetailResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            description=org.description,
            created_at=org.created_at,
            updated_at=org.updated_at,
            member_count=len(members),
            members=[OrgMemberResponse.model_validate(m) for m in members],
        )

    async def update(
        self, org_id: uuid.UUID, data: UpdateOrganizationRequest, user_id: uuid.UUID
    ) -> OrganizationResponse:
        """Update organization details."""
        await self._check_permission(org_id, user_id, ["owner", "admin"])

        result = await self.db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = result.scalar_one_or_none()
        if not org:
            raise NotFoundError("Organization", str(org_id))

        if data.name is not None:
            org.name = data.name
        if data.description is not None:
            org.description = data.description

        await self.db.flush()

        return OrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            description=org.description,
            created_at=org.created_at,
            updated_at=org.updated_at,
            member_count=len(org.members),
        )

    async def add_member(
        self, org_id: uuid.UUID, data: AddMemberRequest, user_id: uuid.UUID
    ) -> OrgMemberResponse:
        """Add a member to the organization."""
        await self._check_permission(org_id, user_id, ["owner", "admin"])

        # Check if already a member
        result = await self.db.execute(
            select(OrgMember).where(
                OrgMember.organization_id == org_id,
                OrgMember.user_id == data.user_id,
            )
        )
        if result.scalar_one_or_none():
            raise DuplicateError("OrgMember", "user_id", str(data.user_id))

        member = OrgMember(
            organization_id=org_id,
            user_id=data.user_id,
            role=data.role,
        )
        self.db.add(member)
        await self.db.flush()

        return OrgMemberResponse.model_validate(member)

    async def _check_permission(
        self, org_id: uuid.UUID, user_id: uuid.UUID, allowed_roles: list[str]
    ) -> OrgMember:
        """Verify user has required role in the organization."""
        result = await self.db.execute(
            select(OrgMember).where(
                OrgMember.organization_id == org_id,
                OrgMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise ForbiddenError("You are not a member of this organization")
        if member.role not in allowed_roles:
            raise ForbiddenError(
                f"This action requires one of: {', '.join(allowed_roles)}"
            )
        return member
