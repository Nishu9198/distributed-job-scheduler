"""
Distributed Job Scheduler — FastAPI Application Factory.

This is the main entry point for the API server. It:
1. Creates the FastAPI app with metadata for OpenAPI docs
2. Registers all middleware (request ID, logging, CORS)
3. Mounts all domain routers under /api/v1
4. Registers global exception handlers
5. Provides health check and root endpoints
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.middleware import (
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    register_exception_handlers,
)
from src.scheduler.engine import SchedulerEngine

settings = get_settings()
logger = structlog.get_logger()
scheduler_engine = SchedulerEngine(poll_interval=10.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown hooks."""
    logger.info(
        "application_starting",
        environment=settings.ENVIRONMENT,
        version=settings.APP_VERSION,
    )
    await scheduler_engine.start()
    yield
    await scheduler_engine.stop()
    logger.info("application_shutting_down")


def create_app() -> FastAPI:
    """Application factory — creates and configures the FastAPI app."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "A production-grade distributed job scheduling platform capable of "
            "reliably executing asynchronous background jobs across multiple workers. "
            "Features atomic job claiming, configurable retry strategies, real-time "
            "monitoring, and a Dead Letter Queue with AI-generated failure summaries."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ─── Middleware (order matters: last added = first executed) ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # ─── Exception Handlers ──────────────────────────────────
    register_exception_handlers(app)

    # ─── Import and Register Routers ─────────────────────────
    from src.auth.router import router as auth_router
    from src.dlq.router import router as dlq_router
    from src.jobs.router import router as jobs_router
    from src.metrics.router import router as metrics_router
    from src.organizations.router import router as orgs_router
    from src.projects.router import router as projects_router
    from src.queues.router import router as queues_router
    from src.websocket import router as ws_router
    from src.workers.router import router as workers_router

    prefix = settings.API_V1_PREFIX

    app.include_router(auth_router, prefix=prefix)
    app.include_router(orgs_router, prefix=prefix)
    app.include_router(projects_router, prefix=prefix)
    app.include_router(queues_router, prefix=prefix)
    app.include_router(jobs_router, prefix=prefix)
    app.include_router(workers_router, prefix=prefix)
    app.include_router(dlq_router, prefix=prefix)
    app.include_router(metrics_router, prefix=prefix)
    app.include_router(ws_router)  # WebSocket at root

    # ─── Health & Root Endpoints ─────────────────────────────
    @app.get("/", tags=["System"])
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "running",
            "docs": "/docs",
        }

    @app.get("/health", tags=["System"])
    async def health_check():
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }

    return app


# Create the app instance (used by uvicorn)
app = create_app()
