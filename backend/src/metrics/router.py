"""
Metrics domain — API router.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.metrics import (
    MetricsService,
    QueueMetrics,
    SystemMetrics,
    ThroughputResponse,
)

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get(
    "/dashboard",
    response_model=SystemMetrics,
    summary="Get dashboard metrics",
)
async def get_dashboard_metrics(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated system-wide metrics for the dashboard."""
    service = MetricsService(db)
    return await service.get_dashboard_metrics()


@router.get(
    "/throughput",
    response_model=ThroughputResponse,
    summary="Get throughput time series",
)
async def get_throughput(
    interval: str = Query("minute", pattern=r"^(minute|hour)$"),
    periods: int = Query(60, ge=1, le=168),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get throughput data points over time."""
    service = MetricsService(db)
    return await service.get_throughput(interval=interval, periods=periods)


@router.get(
    "/queues",
    response_model=list[QueueMetrics],
    summary="Get per-queue metrics",
)
async def get_queue_metrics(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get metrics for all queues."""
    service = MetricsService(db)
    return await service.get_queue_metrics()
