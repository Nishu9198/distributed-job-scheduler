"""
Worker domain — API router.

Provides endpoints for worker registration, heartbeats, job claiming,
and worker monitoring.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.jobs.schemas import JobResponse
from src.jobs.service import JobService
from src.workers.schemas import (
    ClaimJobsRequest,
    CompleteJobRequest,
    HeartbeatRequest,
    RegisterWorkerRequest,
    WorkerDetailResponse,
    WorkerResponse,
)
from src.workers.service import WorkerService

router = APIRouter(prefix="/workers", tags=["Workers"])


@router.post(
    "/register",
    response_model=WorkerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new worker",
)
async def register_worker(
    data: RegisterWorkerRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a worker process (called on worker startup)."""
    service = WorkerService(db)
    return await service.register(data)


@router.post(
    "/{worker_id}/heartbeat",
    response_model=WorkerResponse,
    summary="Send worker heartbeat",
)
async def worker_heartbeat(
    worker_id: uuid.UUID,
    data: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send periodic heartbeat with system metrics."""
    service = WorkerService(db)
    return await service.heartbeat(worker_id, data)


@router.post(
    "/{worker_id}/claim",
    response_model=list[JobResponse],
    summary="Atomically claim jobs",
)
async def claim_jobs(
    worker_id: uuid.UUID,
    data: ClaimJobsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Atomically claim available jobs from a queue.
    
    Uses PostgreSQL FOR UPDATE SKIP LOCKED for contention-free
    job claiming across multiple workers.
    """
    service = JobService(db)
    return await service.claim_jobs(data.queue_id, worker_id, data.batch_size)


@router.post(
    "/{worker_id}/complete",
    response_model=JobResponse,
    summary="Report job completion",
)
async def complete_job(
    worker_id: uuid.UUID,
    data: CompleteJobRequest,
    db: AsyncSession = Depends(get_db),
):
    """Report job completion (success or failure)."""
    service = JobService(db)
    if data.success:
        return await service.complete_job(
            data.job_id, data.execution_id, data.result
        )
    else:
        return await service.fail_job(
            data.job_id,
            data.execution_id,
            data.error_message or "Unknown error",
            data.error_traceback,
        )


@router.post(
    "/{worker_id}/deregister",
    response_model=WorkerResponse,
    summary="Deregister worker",
)
async def deregister_worker(
    worker_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Gracefully deregister a worker (releases claimed jobs)."""
    service = WorkerService(db)
    return await service.deregister(worker_id)


@router.get(
    "",
    response_model=list[WorkerDetailResponse],
    summary="List all workers",
)
async def list_workers(
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all workers with their active job counts."""
    service = WorkerService(db)
    return await service.list_workers(status_filter)


@router.get(
    "/{worker_id}",
    response_model=WorkerDetailResponse,
    summary="Get worker details",
)
async def get_worker(
    worker_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed worker information."""
    service = WorkerService(db)
    return await service.get_by_id(worker_id)
