"""
Job domain — API router.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.jobs.schemas import (
    BatchCreateJobRequest,
    BatchJobResponse,
    CreateJobRequest,
    JobDetailResponse,
    JobListResponse,
    JobResponse,
    RetryJobRequest,
)
from src.jobs.service import JobService

router = APIRouter(tags=["Jobs"])


@router.post(
    "/queues/{queue_id}/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a job",
)
async def create_job(
    queue_id: uuid.UUID,
    data: CreateJobRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new job (immediate, delayed, scheduled, or recurring)."""
    service = JobService(db)
    return await service.create(queue_id, data)


@router.post(
    "/queues/{queue_id}/jobs/batch",
    response_model=BatchJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Batch create jobs",
)
async def batch_create_jobs(
    queue_id: uuid.UUID,
    data: BatchCreateJobRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create up to 1000 jobs in a single batch operation."""
    service = JobService(db)
    return await service.batch_create(queue_id, data)


@router.get(
    "/queues/{queue_id}/jobs",
    response_model=JobListResponse,
    summary="List jobs in queue",
)
async def list_jobs(
    queue_id: uuid.UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    type_filter: Optional[str] = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List jobs with pagination and filtering by status/type."""
    service = JobService(db)
    return await service.list_by_queue(
        queue_id, status=status_filter, type=type_filter, page=page, page_size=page_size
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobDetailResponse,
    summary="Get job details",
)
async def get_job(
    job_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full job details including execution history."""
    service = JobService(db)
    return await service.get_by_id(job_id)


@router.get(
    "/jobs/{job_id}/logs",
    summary="Get job execution logs",
)
async def get_job_logs(
    job_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated execution logs for a job."""
    service = JobService(db)
    return await service.get_logs(job_id, page=page, page_size=page_size)


@router.post(
    "/jobs/{job_id}/retry",
    response_model=JobResponse,
    summary="Retry a failed/dead job",
)
async def retry_job(
    job_id: uuid.UUID,
    data: RetryJobRequest = RetryJobRequest(),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually retry a failed or dead job."""
    service = JobService(db)
    return await service.retry_job(job_id, reset_count=data.reset_retry_count)


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=JobResponse,
    summary="Cancel a pending job",
)
async def cancel_job(
    job_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a queued or scheduled job."""
    service = JobService(db)
    return await service.cancel_job(job_id)
