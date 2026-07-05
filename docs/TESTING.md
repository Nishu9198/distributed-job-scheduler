# Testing

## Test Infrastructure

- **Framework:** pytest 8.3.4 with `pytest-asyncio` 0.25.0 (`asyncio_mode = auto`)
- **HTTP Client:** `httpx.AsyncClient` with `ASGITransport` (tests call the FastAPI app directly, no server needed)
- **Database:** SQLite in-memory via `aiosqlite` — tables are created before each test and dropped after
- **Coverage:** `pytest-cov` 6.0.0 available
- **Config:** `backend/pytest.ini`

### Test Fixtures (defined in `tests/__init__.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `event_loop` | session | Creates a single event loop for the test session |
| `setup_database` | function, autouse | Creates all tables before each test, drops after |
| `db_session` | function | Provides an `AsyncSession` connected to the in-memory SQLite DB |
| `client` | function | `httpx.AsyncClient` with test DB override via `dependency_overrides[get_db]` |
| `auth_headers` | function | Creates a test user (admin role) and returns `{"Authorization": "Bearer <token>"}` |
| `test_user` | function | Creates and returns a test `User` ORM object |

---

## Test Files

### `test_auth.py` — Authentication (168 lines, 8 tests)

Tests the full authentication flow through the REST API.

| Test Class | Test | What It Covers |
|------------|------|----------------|
| `TestAuthRegistration` | `test_register_success` | Valid registration returns user + tokens (201) |
| | `test_register_duplicate_email` | Duplicate email returns 409 `DUPLICATE_RESOURCE` |
| | `test_register_weak_password` | Missing uppercase in password returns 422 |
| | `test_register_short_password` | Password under 8 chars returns 422 |
| `TestAuthLogin` | `test_login_success` | Valid credentials return tokens (200) |
| | `test_login_invalid_password` | Wrong password returns 401 `INVALID_CREDENTIALS` |
| | `test_login_nonexistent_user` | Non-existent email returns 401 |
| `TestAuthTokenRefresh` | `test_refresh_success` | Valid refresh token returns new access token |
| | `test_refresh_invalid_token` | Invalid refresh token returns 401 |
| `TestProtectedEndpoints` | `test_unauthenticated_request` | No token → 401 `AUTHENTICATION_REQUIRED` |
| | `test_invalid_token` | Invalid JWT → 401 |

---

### `test_jobs.py` — Job & Queue CRUD (257 lines, 9 tests)

Tests queue and job API endpoints including batch creation, pagination, idempotency, and cancellation.

| Test Class | Test | What It Covers |
|------------|------|----------------|
| `TestQueueEndpoints` | `test_create_queue` | Queue creation with priority, concurrency_limit, max_retries |
| | `test_list_queues` | Listing queues in a project |
| | `test_pause_resume_queue` | Pause sets `is_paused=true`, resume sets it back to `false` |
| `TestJobEndpoints` | `test_create_immediate_job` | Creates an immediate job with status `queued` |
| | `test_create_scheduled_job` | Creates a scheduled job with status `scheduled` |
| | `test_create_recurring_job` | Creates a recurring job with `cron_expression` |
| | `test_batch_create_jobs` | Batch creates 10 jobs, verifies `created=10, failed=0` |
| | `test_list_jobs_with_pagination` | Creates 15 jobs, verifies page 1 has 10 items, page 2 has 5, `total_pages=2` |
| | `test_idempotency_key` | Submitting same `idempotency_key` twice returns the same job ID |
| | `test_cancel_job` | Cancelling a queued job sets status to `cancelled` |

Helper: `_setup_org_project()` creates the org → project chain needed before creating queues.

---

### `test_concurrency.py` — Atomic Job Claiming (207 lines, 3 tests)

Tests the critical concurrency guarantees of the job claiming system.

| Test Class | Test | What It Covers |
|------------|------|----------------|
| `TestAtomicClaiming` | `test_no_duplicate_claims_sequential` | Creates 5 jobs, has 2 workers claim sequentially. Verifies: (a) no overlap between claimed sets, (b) all 5 jobs claimed in total. |
| | `test_concurrency_limit_respected` | Queue with `concurrency_limit=2`, 10 jobs. Claims should return ≤2 jobs. |
| | `test_paused_queue_returns_empty` | Paused queue returns 0 jobs on claim. |

**Note:** These tests verify sequential claiming behavior through the HTTP API. True concurrent claiming (multiple simultaneous requests) is not tested because the in-memory SQLite backend doesn't support `FOR UPDATE SKIP LOCKED`. The PostgreSQL-specific claiming behavior would need integration tests against a real Postgres instance.

---

### `test_job_lifecycle.py` — State Machine (85 lines, 5 tests)

Unit tests for the lifecycle state machine — no HTTP, no database. Pure function tests.

| Test Class | Test | What It Covers |
|------------|------|----------------|
| `TestJobLifecycle` | `test_valid_transitions` | 12 valid transitions (queued→claimed, running→completed, failed→dead, etc.) don't raise |
| | `test_invalid_transitions` | 7 invalid transitions (completed→running, cancelled→queued, queued→running, etc.) raise `InvalidStateTransitionError` |
| | `test_can_transition` | `can_transition()` returns bool without raising |
| | `test_terminal_states` | `completed` and `cancelled` are terminal; `dead` is not (can be retried) |
| | `test_active_states` | `claimed` and `running` are active |
| | `test_retriable_states` | `failed` and `dead` are retriable |

---

### `test_workers.py` — Worker Operations (108 lines, 5 tests)

Tests worker registration, heartbeats, deregistration, and listing.

| Test Class | Test | What It Covers |
|------------|------|----------------|
| `TestWorkerEndpoints` | `test_register_worker` | Registration returns 201 with status `idle`, correct name and concurrency |
| | `test_worker_heartbeat` | Heartbeat with `active_jobs=3` sets status to `busy` |
| | `test_worker_heartbeat_idle` | Heartbeat with `active_jobs=0` sets status to `idle` |
| | `test_deregister_worker` | Deregistration sets status to `offline` |
| | `test_list_workers` | Lists registered workers (≥3 after registering 3) |

---

## Coverage Assessment

### What IS Covered

| Area | Coverage |
|------|----------|
| Auth flow (register, login, refresh, validation) | ✅ Solid |
| Queue CRUD (create, list, pause, resume) | ✅ Solid |
| Job CRUD (create all types, batch, pagination, idempotency, cancel) | ✅ Solid |
| Job lifecycle state machine (all valid/invalid transitions) | ✅ Solid |
| Worker operations (register, heartbeat, deregister, list) | ✅ Solid |
| Sequential job claiming (no duplicates, concurrency limits) | ✅ Good |
| Paused queue blocking | ✅ Good |

### What is NOT Covered

| Area | Status |
|------|--------|
| Organization CRUD | ❌ No direct tests (exercised indirectly as setup for queue/job tests) |
| Organization membership and RBAC | ❌ Not tested |
| Project CRUD | ❌ No direct tests (exercised indirectly) |
| Retry policy CRUD | ❌ Not tested |
| Job retry (manual retry of failed/dead jobs) | ❌ Not tested via API |
| Job failure → retry → DLQ flow (end-to-end) | ❌ Not tested |
| Dead Letter Queue endpoints (list, retry, resolve) | ❌ Not tested |
| Worker claiming + completion flow (end-to-end) | ❌ Not tested via API |
| Stale worker detection and orphan recovery | ❌ Not tested |
| Metrics/dashboard endpoints | ❌ Not tested |
| WebSocket connection and events | ❌ Not tested |
| Scheduler engine (scheduled job promotion) | ❌ Not tested |
| Worker engine (poll loop, execution, graceful shutdown) | ❌ Not tested |
| Concurrent claiming under real Postgres (`FOR UPDATE SKIP LOCKED`) | ❌ No integration test |
| Rate limiting | ❌ Not implemented, not tested |
| Error response format consistency | Partially — some error codes are asserted |
| Edge cases (empty queues, very large batches, invalid UUIDs) | Partially |

### Estimated Code Coverage

Based on the test surface area, estimated line coverage is roughly:
- `src/auth/` — ~80-90%
- `src/jobs/lifecycle.py` — ~100%
- `src/jobs/service.py` — ~30-40% (create, list, cancel tested; claim, fail, retry logic not tested via API)
- `src/queues/service.py` — ~40-50% (CRUD tested, stats partially)
- `src/workers/service.py` — ~30-40% (register, heartbeat, deregister tested; stale detection not tested)
- `src/workers/engine.py` — 0% (standalone process, not invoked in tests)
- `src/dlq/` — 0%
- `src/metrics/` — 0%
- `src/scheduler/` — 0%
- `src/websocket/` — 0%
- `src/organizations/` — ~20% (covered indirectly)
- `src/projects/` — ~20% (covered indirectly)
- `src/core/` — ~50-60% (auth dependencies exercised, middleware/exceptions partially)

Run `make test-cov` to get exact coverage numbers.
