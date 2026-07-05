"""
Project domain — Service layer.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DuplicateError, NotFoundError
from src.organizations import OrgMember
from src.projects import Project
from src.projects.schemas import (
    CreateProjectRequest,
    ProjectResponse,
    UpdateProjectRequest,
)
from src.queues import Queue


class ProjectService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self, org_id: uuid.UUID, data: CreateProjectRequest
    ) -> ProjectResponse:
        """Create a project within an organization."""
        # Check slug uniqueness within org
        result = await self.db.execute(
            select(Project).where(
                Project.organization_id == org_id,
                Project.slug == data.slug,
            )
        )
        if result.scalar_one_or_none():
            raise DuplicateError("Project", "slug", data.slug)

        project = Project(
            organization_id=org_id,
            name=data.name,
            slug=data.slug,
            description=data.description,
        )
        self.db.add(project)
        await self.db.flush()

        return ProjectResponse(
            id=project.id,
            organization_id=project.organization_id,
            name=project.name,
            slug=project.slug,
            description=project.description,
            created_at=project.created_at,
            updated_at=project.updated_at,
            queue_count=0,
        )

    async def list_by_org(self, org_id: uuid.UUID) -> list[ProjectResponse]:
        """List all projects in an organization."""
        result = await self.db.execute(
            select(Project)
            .where(Project.organization_id == org_id)
            .order_by(Project.created_at.desc())
        )
        projects = result.scalars().all()

        responses = []
        for p in projects:
            count_result = await self.db.execute(
                select(func.count()).select_from(Queue).where(Queue.project_id == p.id)
            )
            count = count_result.scalar()
            responses.append(
                ProjectResponse(
                    id=p.id,
                    organization_id=p.organization_id,
                    name=p.name,
                    slug=p.slug,
                    description=p.description,
                    created_at=p.created_at,
                    updated_at=p.updated_at,
                    queue_count=count or 0,
                )
            )
        return responses

    async def get_by_id(self, project_id: uuid.UUID) -> ProjectResponse:
        """Get project details."""
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise NotFoundError("Project", str(project_id))

        count_result = await self.db.execute(
            select(func.count()).select_from(Queue).where(Queue.project_id == project.id)
        )
        count = count_result.scalar()

        return ProjectResponse(
            id=project.id,
            organization_id=project.organization_id,
            name=project.name,
            slug=project.slug,
            description=project.description,
            created_at=project.created_at,
            updated_at=project.updated_at,
            queue_count=count or 0,
        )

    async def update(
        self, project_id: uuid.UUID, data: UpdateProjectRequest
    ) -> ProjectResponse:
        """Update project details."""
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise NotFoundError("Project", str(project_id))

        if data.name is not None:
            project.name = data.name
        if data.description is not None:
            project.description = data.description

        await self.db.flush()
        return await self.get_by_id(project_id)

    async def delete(self, project_id: uuid.UUID) -> None:
        """Delete a project and all its queues (cascading)."""
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise NotFoundError("Project", str(project_id))

        await self.db.delete(project)
        await self.db.flush()
