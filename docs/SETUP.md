# Setup Guide

## Prerequisites

- **Docker** and **Docker Compose** (v2+)
- **Python 3.12+** (only if running outside Docker)
- **Node.js 20+** and **npm** (only if running frontend outside Docker)
- **PostgreSQL 16** and **Redis 7** (only if not using Docker)

---

## Quick Start (Docker — Recommended)

This is the fastest way to get everything running.

### 1. Clone and Configure Environment

```bash
cp .env.example .env
# Edit .env if you want to change defaults (optional for development)
```

### 2. Start All Services

```bash
# Start all services (Postgres, Redis, API, Worker, Frontend)
make up-build

# Or without Make:
docker compose up -d --build
```

This starts 5 containers:

| Container | Port | Purpose |
|-----------|------|---------|
| `djs-postgres` | 5432 | PostgreSQL 16 database |
| `djs-redis` | 6379 | Redis 7 |
| `djs-api` | 8000 | FastAPI backend (with hot reload) |
| `djs-worker` | — | Worker process (polls and executes jobs) |
| `djs-frontend` | 5173 | React dashboard (Vite dev server) |

### 3. Run Database Migrations

```bash
make migrate

# Or without Make:
cd backend && alembic upgrade head
```

### 4. Seed Sample Data (Optional)

```bash
make seed

# Or without Make:
cd backend && python -m src.seed
```

### 5. Verify

- **API docs:** http://localhost:8000/docs
- **Dashboard:** http://localhost:5173
- **Health check:** http://localhost:8000/health

---

## Manual Setup (Without Docker)

### Backend

#### 1. Set Up PostgreSQL and Redis

Ensure PostgreSQL 16 and Redis 7 are running locally. Create the database:

```bash
createdb distributed_job_scheduler
```

#### 2. Configure Environment

```bash
cp .env.example .env
# Edit DATABASE_URL and REDIS_URL if your hosts/ports/credentials differ
```

#### 3. Install Python Dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

#### 4. Run Migrations

```bash
cd backend
alembic upgrade head
```

#### 5. Start the API Server

```bash
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 6. Start a Worker (Separate Terminal)

```bash
cd backend
python -m src.workers.engine
```

You can start multiple workers. Each worker:
- Self-registers with the API database
- Polls queues specified by `WORKER_QUEUES` env var (comma-separated slugs, default: `default`)
- Sends heartbeats every `WORKER_HEARTBEAT_INTERVAL` seconds (default: 30)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server starts at http://localhost:5173.

---

## Environment Variables

All variables have sensible defaults for development. Override via `.env` file or environment.

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `djs_user` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `djs_secret` | PostgreSQL password |
| `POSTGRES_DB` | `distributed_job_scheduler` | Database name |
| `DATABASE_URL` | `postgresql+asyncpg://djs_user:djs_secret@localhost:5432/distributed_job_scheduler` | Async SQLAlchemy connection string |
| `DATABASE_URL_SYNC` | `postgresql://djs_user:djs_secret@localhost:5432/distributed_job_scheduler` | Sync connection string (used by Alembic) |

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | `super-secret-key-change-in-production` | **Must change in production** |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |

### Worker

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKER_CONCURRENCY` | `10` | Max concurrent jobs per worker |
| `WORKER_QUEUES` | `default` | Comma-separated queue slugs to poll |
| `WORKER_POLL_INTERVAL` | `1.0` | Seconds between poll cycles |
| `WORKER_HEARTBEAT_INTERVAL` | `30` | Seconds between heartbeats |

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | Environment name |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Useful Make Targets

```
make help              # Show all available targets
make up                # Start all services
make up-build          # Rebuild and start all services
make down              # Stop all services
make logs              # Tail logs for all services
make logs-api          # Tail API logs only
make logs-worker       # Tail worker logs only
make test              # Run backend tests
make test-cov          # Run tests with coverage report
make migrate           # Run database migrations
make migrate-create    # Create new migration (usage: make migrate-create msg="description")
make seed              # Seed database with sample data
make format            # Format code (black + isort)
make lint              # Lint code (ruff)
make shell             # Open bash in API container
make db-shell          # Open psql shell
make redis-cli         # Open Redis CLI
```

---

## Running Tests

```bash
# Run all tests
make test

# Or directly:
cd backend && python -m pytest tests/ -v --tb=short

# With coverage:
make test-cov

# Or directly:
cd backend && python -m pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html
```

Tests use an **in-memory SQLite** database (via `aiosqlite`) — no PostgreSQL or Redis needed for testing.

---

## Project Structure

```
├── docker-compose.yml          # All services
├── .env.example                # Environment template
├── Makefile                    # Dev shortcuts
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/                # Migration scripts
│   ├── pytest.ini
│   ├── src/
│   │   ├── main.py             # FastAPI app factory
│   │   ├── seed.py             # Sample data seeder
│   │   ├── core/               # Config, DB, auth, middleware, exceptions
│   │   ├── auth/               # User registration, login, JWT
│   │   ├── organizations/      # Org CRUD, membership
│   │   ├── projects/           # Project CRUD
│   │   ├── queues/             # Queue CRUD, retry policies
│   │   ├── jobs/               # Job CRUD, lifecycle, claiming, retries
│   │   ├── workers/            # Worker registration, heartbeats, engine
│   │   ├── dlq/                # Dead letter queue
│   │   ├── scheduler/          # Scheduled job promotion engine
│   │   ├── metrics/            # Dashboard aggregation
│   │   └── websocket/          # Live updates (ConnectionManager)
│   └── tests/
│       ├── __init__.py         # Test fixtures (DB setup, auth helpers)
│       ├── conftest.py
│       ├── test_auth.py
│       ├── test_jobs.py
│       ├── test_concurrency.py
│       ├── test_job_lifecycle.py
│       └── test_workers.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    └── src/                    # React + TypeScript dashboard
```
