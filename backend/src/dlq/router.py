"""
DLQ domain — API router.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.dlq.schemas import DLQEntryResponse, DLQListResponse
from src.dlq.service import DLQService

router = APIRouter(tags=["Dead Letter Queue"])


@router.get(
    "/dlq",
    response_model=DLQListResponse,
    summary="List all DLQ entries",
)
async def list_all_dlq(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all dead letter queue entries across all queues."""
    service = DLQService(db)
    return await service.list_all()


@router.get(
    "/queues/{queue_id}/dlq",
    response_model=DLQListResponse,
    summary="List DLQ entries for queue",
)
async def list_queue_dlq(
    queue_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List dead letter queue entries for a specific queue."""
    service = DLQService(db)
    return await service.list_by_queue(queue_id)


@router.post(
    "/dlq/{dlq_id}/retry",
    response_model=DLQEntryResponse,
    summary="Retry a dead job",
)
async def retry_dlq_entry(
    dlq_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retry a dead job by moving it back to the queue."""
    service = DLQService(db)
    return await service.retry_entry(dlq_id, current_user.id)


@router.post(
    "/dlq/{dlq_id}/resolve",
    response_model=DLQEntryResponse,
    summary="Resolve a DLQ entry",
)
async def resolve_dlq_entry(
    dlq_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a DLQ entry as resolved without retrying."""
    service = DLQService(db)
    return await service.resolve_entry(dlq_id, current_user.id)
