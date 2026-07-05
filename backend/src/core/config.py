"""
Core configuration module.

Uses pydantic-settings to load environment variables with type validation
and sensible defaults for development.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ─── Application ─────────────────────────────────────────
    APP_NAME: str = "Distributed Job Scheduler"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # ─── Database ────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://djs_user:djs_secret@localhost:5432/distributed_job_scheduler"
    DATABASE_URL_SYNC: str = "postgresql://djs_user:djs_secret@localhost:5432/distributed_job_scheduler"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    # ─── Redis ───────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ─── Authentication ──────────────────────────────────────
    JWT_SECRET_KEY: str = "super-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ─── Worker ──────────────────────────────────────────────
    WORKER_CONCURRENCY: int = 10
    WORKER_QUEUES: str = "default"
    WORKER_POLL_INTERVAL: float = 1.0
    WORKER_HEARTBEAT_INTERVAL: int = 30
    WORKER_STALE_THRESHOLD: int = 90

    # ─── Rate Limiting ───────────────────────────────────────
    RATE_LIMIT_ENABLED: bool = True
    DEFAULT_RATE_LIMIT: int = 100


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance (singleton per process)."""
    return Settings()
