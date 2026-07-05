# Distributed Job Scheduler

A production-grade distributed job scheduling platform capable of reliably executing asynchronous background jobs across multiple workers. It features contention-free atomic job claiming, robust state machine lifecycle enforcement, configurable retry strategies with backoff, a Dead Letter Queue, and a real-time React dashboard.

## Tech Stack

- **Backend:** FastAPI (Python 3.12+), SQLAlchemy 2.0 (async), Alembic, PyJWT
- **Database:** PostgreSQL 16 (via asyncpg)
- **Frontend:** React 19, Vite, Recharts, TailwindCSS / Vanilla CSS
- **Infrastructure:** Docker, Docker Compose, Redis 7 (currently provisioned for config/future pub-sub)

## Quick Start

The fastest way to get everything running locally is via Docker:

```bash
# 1. Configure environment
cp .env.example .env

# 2. Start all services (Postgres, Redis, API, Worker, Frontend)
make up-build
# Or: docker compose up -d --build

# 3. Run database migrations
make migrate
# Or: cd backend && alembic upgrade head

# 4. Seed sample data (optional)
make seed
# Or: cd backend && python -m src.seed
```
- **API docs:** http://localhost:8000/docs
- **Dashboard:** http://localhost:5173

## Key Features

- **Atomic Job Claiming:** Workers safely pull jobs concurrently using PostgreSQL's `FOR UPDATE SKIP LOCKED`, entirely avoiding DB contention.
- **Strict Job Lifecycle:** enforced via a state machine (queued → claimed → running → completed/failed).
- **Configurable Retry Policies:** Includes fixed, linear, and exponential backoff strategies with random jitter to prevent stampedes.
- **Dead Letter Queue (DLQ):** Captures exhausted jobs while preserving original payloads, including traceback captures and pattern-based failure summaries.
- **Standalone Worker Engine:** Runs in a separate process, using `asyncio.Semaphore` for bounded concurrency, sending regular heartbeats, and handling SIGTERM for graceful draining.
- **Stale Worker Recovery:** Automatically detects crashed/offline workers and re-queues their orphaned jobs.
- **Recurring & Scheduled Jobs:** Supports delayed execution and cron-based repeating jobs.
- **Idempotent Creation:** Prevents accidental double-submission of identical jobs within the same queue using unique idempotency keys.

## Documentation

Extensive documentation is available in the [`docs`](docs) directory:

- [**Architecture**](docs/ARCHITECTURE.md) - System architecture and job flow diagrams, design trade-offs.
- [**ER Diagram**](docs/ER_DIAGRAM.md) - Full database schema, constraints, indexes, and cascading logic.
- [**API Documentation**](docs/API_DOCUMENTATION.md) - Comprehensive REST endpoint references.
- [**Design Decisions**](docs/DESIGN_DECISIONS.md) - Deep dive into atomic claiming, retries, and architectural choices.
- [**Setup Guide**](docs/SETUP.md) - Detailed manual and Docker setup instructions.
- [**Testing**](docs/TESTING.md) - Overview of the test suite and coverage.

## Project Structure

```text
.
├── backend/            # FastAPI application, SQLAlchemy models, background engines
├── docs/               # Architecture, ER diagrams, and project documentation
├── frontend/           # React dashboard (Vite)
├── docker-compose.yml  # Multi-container orchestration
└── Makefile            # Dev shortcuts for testing, building, and seeding
```

## Known Limitations

- **Worker Authentication:** Worker endpoints (`/register`, `/heartbeat`, `/claim`) currently lack authentication; in production, these require API keys or mutual TLS.
- **WebSocket Wiring:** While the WebSocket `ConnectionManager` exists, service-layer operations (job creation, completion) do not yet broadcast events to it.
- **Rate Limiting:** Queue-level rate limiting (`rate_limit_per_second`) is defined in the schema but not currently enforced during claiming.
- **Idempotency Key Expiration:** Idempotency keys never expire, meaning you cannot reuse a key even after the original job has fully completed.
