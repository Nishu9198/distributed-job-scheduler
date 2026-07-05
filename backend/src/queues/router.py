"""
Queue domain — API router.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.queues.schemas import (
    CreateQueueRequest,
    CreateRetryPolicyRequest,
    QueueDetailResponse,
    QueueResponse,
    QueueStatsResponse,
    RetryPolicyResponse,
    UpdateQueueRequest,
)
from src.queues.service import QueueService

router = APIRouter(tags=["Queues"])


# ─── Queue Endpoints ────────────────────────────────────────
@router.post(
    "/projects/{project_id}/queues",
    response_model=QueueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new queue",
)
async def create_queue(
    project_id: uuid.UUID,
    data: CreateQueueRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    return await service.create(project_id, data)


@router.get(
    "/projects/{project_id}/queues",
    response_model=list[QueueResponse],
    summary="List queues in project",
)
async def list_queues(
    project_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    return await service.list_by_project(project_id)


@router.get(
    "/queues/{queue_id}",
    response_model=QueueDetailResponse,
    summary="Get queue details with stats",
)
async def get_queue(
    queue_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    return await service.get_by_id(queue_id)


@router.patch(
    "/queues/{queue_id}",
    response_model=QueueResponse,
    summary="Update queue configuration",
)
async def update_queue(
    queue_id: uuid.UUID,
    data: UpdateQueueRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    return await service.update(queue_id, data)


@router.delete(
    "/queues/{queue_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete queue",
)
async def delete_queue(
    queue_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    await service.delete(queue_id)


@router.post(
    "/queues/{queue_id}/pause",
    response_model=QueueResponse,
    summary="Pause queue",
)
async def pause_queue(
    queue_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    return await service.pause(queue_id)


@router.post(
    "/queues/{queue_id}/resume",
    response_model=QueueResponse,
    summary="Resume paused queue",
)
async def resume_queue(
    queue_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    return await service.resume(queue_id)


@router.get(
    "/queues/{queue_id}/stats",
    response_model=QueueStatsResponse,
    summary="Get real-time queue statistics",
)
async def get_queue_stats(
    queue_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    return await service.get_stats(queue_id)


# ─── Retry Policy Endpoints ─────────────────────────────────
@router.post(
    "/retry-policies",
    response_model=RetryPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a retry policy",
)
async def create_retry_policy(
    data: CreateRetryPolicyRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    return await service.create_retry_policy(data)


@router.get(
    "/retry-policies",
    response_model=list[RetryPolicyResponse],
    summary="List all retry policies",
)
async def list_retry_policies(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    return await service.list_retry_policies()
