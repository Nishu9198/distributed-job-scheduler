# API Documentation

All endpoints are prefixed with `/api/v1` unless otherwise noted. Responses use a consistent error envelope:

```json
{
  "error": {
    "code": "MACHINE_READABLE_CODE",
    "message": "Human-readable message",
    "details": {},
    "request_id": "uuid"
  }
}
```

---

## System

### `GET /`

Root endpoint. No auth required.

**Response** `200 OK`
```json
{
  "name": "Distributed Job Scheduler",
  "version": "1.0.0",
  "status": "running",
  "docs": "/docs"
}
```

### `GET /health`

Health check. No auth required.

**Response** `200 OK`
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "development"
}
```

---

## Authentication

### `POST /api/v1/auth/register`

Register a new user account. **No auth required.**

**Request Body**
```json
{
  "email": "user@example.com",
  "password": "StrongPass1!",
  "full_name": "John Doe"
}
```

| Field | Type | Constraints |
|-------|------|-------------|
| `email` | string | Valid email (EmailStr) |
| `password` | string | 8–128 chars, ≥1 uppercase, ≥1 digit |
| `full_name` | string | 1–255 chars |

**Response** `201 Created`
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "full_name": "John Doe",
    "role": "member",
    "is_active": true,
    "created_at": "2026-01-01T00:00:00Z"
  },
  "tokens": {
    "access_token": "jwt...",
    "refresh_token": "jwt...",
    "token_type": "bearer",
    "expires_in": 1800
  }
}
```

**Errors:** `409 DUPLICATE_RESOURCE` (email taken), `422` (validation)

---

### `POST /api/v1/auth/login`

Authenticate with email and password. **No auth required.**

**Request Body**
```json
{
  "email": "user@example.com",
  "password": "StrongPass1!"
}
```

**Response** `200 OK` — Same shape as register response.

**Errors:** `401 INVALID_CREDENTIALS`

---

### `POST /api/v1/auth/refresh`

Exchange a refresh token for a new access token. **No auth required.**

**Request Body**
```json
{
  "refresh_token": "jwt..."
}
```

**Response** `200 OK`
```json
{
  "access_token": "jwt...",
  "refresh_token": "jwt...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Errors:** `401 TOKEN_EXPIRED`, `401 INVALID_TOKEN`

---

## Organizations

All organization endpoints require `Authorization: Bearer <token>`.

### `POST /api/v1/organizations`

Create a new organization. The creator becomes the owner.

**Request Body**
```json
{
  "name": "My Org",
  "slug": "my-org",
  "description": "Optional description"
}
```

| Field | Type | Constraints |
|-------|------|-------------|
| `name` | string | 1–255 chars |
| `slug` | string | 1–255 chars, pattern `^[a-z0-9-]+$` |
| `description` | string | 0–1000 chars, default `""` |

**Response** `201 Created`
```json
{
  "id": "uuid",
  "name": "My Org",
  "slug": "my-org",
  "description": "",
  "created_at": "...",
  "updated_at": "...",
  "member_count": 1
}
```

**Errors:** `401`, `409 DUPLICATE_RESOURCE` (slug taken)

---

### `GET /api/v1/organizations`

List organizations the current user belongs to.

**Response** `200 OK` — Array of `OrganizationResponse`.

---

### `GET /api/v1/organizations/{org_id}`

Get organization details with member list.

**Response** `200 OK`
```json
{
  "id": "uuid",
  "name": "My Org",
  "slug": "my-org",
  "description": "",
  "created_at": "...",
  "updated_at": "...",
  "member_count": 2,
  "members": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "role": "owner",
      "joined_at": "..."
    }
  ]
}
```

**Errors:** `401`, `404 ORGANIZATION_NOT_FOUND`

---

### `PATCH /api/v1/organizations/{org_id}`

Update organization. Requires `owner` or `admin` role in the org.

**Request Body** (all fields optional)
```json
{
  "name": "New Name",
  "description": "Updated description"
}
```

**Response** `200 OK` — `OrganizationResponse`.

**Errors:** `401`, `403 FORBIDDEN`, `404`

---

### `POST /api/v1/organizations/{org_id}/members`

Add a member to the organization. Requires `owner` or `admin` role.

**Request Body**
```json
{
  "user_id": "uuid",
  "role": "member"
}
```

| Field | Type | Constraints |
|-------|------|-------------|
| `user_id` | UUID | Required |
| `role` | string | `owner`, `admin`, or `member` (default `member`) |

**Response** `201 Created`
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "role": "member",
  "joined_at": "..."
}
```

**Errors:** `401`, `403`, `409 DUPLICATE_RESOURCE` (already a member)

---

## Projects

All project endpoints require auth. Projects are scoped under organizations.

### `POST /api/v1/organizations/{org_id}/projects`

**Request Body**
```json
{
  "name": "My Project",
  "slug": "my-project",
  "description": ""
}
```

**Response** `201 Created`
```json
{
  "id": "uuid",
  "organization_id": "uuid",
  "name": "My Project",
  "slug": "my-project",
  "description": "",
  "created_at": "...",
  "updated_at": "...",
  "queue_count": 0
}
```

**Errors:** `401`, `409 DUPLICATE_RESOURCE` (slug within org)

---

### `GET /api/v1/organizations/{org_id}/projects`

List all projects in an organization.

**Response** `200 OK` — Array of `ProjectResponse`.

---

### `GET /api/v1/organizations/{org_id}/projects/{project_id}`

**Response** `200 OK` — `ProjectResponse`.

**Errors:** `401`, `404`

---

### `PATCH /api/v1/organizations/{org_id}/projects/{project_id}`

**Request Body** (optional fields)
```json
{
  "name": "Updated Name",
  "description": "Updated desc"
}
```

**Response** `200 OK` — `ProjectResponse`.

---

### `DELETE /api/v1/organizations/{org_id}/projects/{project_id}`

Deletes the project and cascades to all queues, jobs, executions, and logs.

**Response** `204 No Content`

**Errors:** `401`, `404`

---

## Queues

### `POST /api/v1/projects/{project_id}/queues`

Create a queue within a project. Requires auth.

**Request Body**
```json
{
  "name": "Email Queue",
  "slug": "email-queue",
  "description": "",
  "priority": 8,
  "concurrency_limit": 15,
  "max_retries": 5,
  "retry_policy_id": "uuid-or-null",
  "rate_limit_per_second": 100
}
```

| Field | Type | Default | Constraints |
|-------|------|---------|-------------|
| `name` | string | — | 1–255 chars |
| `slug` | string | — | 1–255 chars, `^[a-z0-9-]+$` |
| `description` | string | `""` | 0–1000 chars |
| `priority` | int | `5` | 1–10 |
| `concurrency_limit` | int | `10` | 1–1000 |
| `max_retries` | int | `3` | 0–50 |
| `retry_policy_id` | UUID | `null` | Optional FK |
| `rate_limit_per_second` | int | `null` | 1–10000 |

**Response** `201 Created` — `QueueResponse`.

**Errors:** `401`, `409 DUPLICATE_RESOURCE` (slug within project)

---

### `GET /api/v1/projects/{project_id}/queues`

List queues in a project, ordered by priority DESC then created_at.

**Response** `200 OK` — Array of `QueueResponse`.

---

### `GET /api/v1/queues/{queue_id}`

Get queue details with real-time stats and retry policy.

**Response** `200 OK`
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "name": "Email Queue",
  "slug": "email-queue",
  "...": "...",
  "stats": {
    "queue_id": "uuid",
    "queue_name": "Email Queue",
    "total_jobs": 150,
    "queued": 10,
    "scheduled": 5,
    "claimed": 2,
    "running": 3,
    "completed": 120,
    "failed": 8,
    "dead": 2,
    "cancelled": 0,
    "avg_duration_ms": 1234.5,
    "throughput_per_minute": 12.0,
    "is_paused": false
  },
  "retry_policy": {
    "id": "uuid",
    "name": "Default Exponential",
    "strategy": "exponential",
    "base_delay_ms": 1000,
    "max_delay_ms": 300000,
    "multiplier": 2.0,
    "jitter": 0.2,
    "created_at": "..."
  }
}
```

---

### `PATCH /api/v1/queues/{queue_id}`

Update queue configuration. Requires auth.

**Request Body** (all fields optional)
```json
{
  "name": "New Name",
  "priority": 9,
  "concurrency_limit": 20,
  "max_retries": 10,
  "retry_policy_id": "uuid",
  "rate_limit_per_second": 50
}
```

**Response** `200 OK` — `QueueResponse`.

---

### `DELETE /api/v1/queues/{queue_id}`

Delete queue (cascades to all jobs).

**Response** `204 No Content`

---

### `POST /api/v1/queues/{queue_id}/pause`

Pause a queue — workers stop claiming new jobs from it.

**Response** `200 OK` — `QueueResponse` with `is_paused: true`.

---

### `POST /api/v1/queues/{queue_id}/resume`

Resume a paused queue.

**Response** `200 OK` — `QueueResponse` with `is_paused: false`.

---

### `GET /api/v1/queues/{queue_id}/stats`

Get real-time queue statistics (job counts by status, avg duration, throughput).

**Response** `200 OK` — `QueueStatsResponse`.

---

## Retry Policies

### `POST /api/v1/retry-policies`

Create a reusable retry policy. Requires auth.

**Request Body**
```json
{
  "name": "Aggressive Exponential",
  "strategy": "exponential",
  "base_delay_ms": 500,
  "max_delay_ms": 60000,
  "multiplier": 3.0,
  "jitter": 0.3
}
```

| Field | Type | Default | Constraints |
|-------|------|---------|-------------|
| `name` | string | — | 1–255 chars |
| `strategy` | string | `exponential` | `fixed`, `linear`, or `exponential` |
| `base_delay_ms` | int | `1000` | 100–3,600,000 |
| `max_delay_ms` | int | `300000` | 1,000–86,400,000 |
| `multiplier` | float | `2.0` | 1.0–10.0 |
| `jitter` | float | `0.2` | 0.0–1.0 |

**Response** `201 Created` — `RetryPolicyResponse`.

---

### `GET /api/v1/retry-policies`

List all retry policies. Requires auth.

**Response** `200 OK` — Array of `RetryPolicyResponse`.

---

## Jobs

### `POST /api/v1/queues/{queue_id}/jobs`

Create a job (immediate, delayed, scheduled, or recurring). Requires auth.

**Request Body**
```json
{
  "name": "Send welcome email",
  "type": "immediate",
  "payload": {"to": "user@example.com", "template": "welcome"},
  "priority": 8,
  "max_retries": 5,
  "idempotency_key": "email-welcome-user123",
  "scheduled_at": "2026-01-01T00:00:00Z",
  "cron_expression": "0 2 * * *"
}
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `name` | string | `"untitled"` | Max 255 chars |
| `type` | string | `"immediate"` | `immediate`, `delayed`, `scheduled`, `recurring` |
| `payload` | object | `{}` | Arbitrary JSON |
| `priority` | int | `5` | 1–10 |
| `max_retries` | int | `null` | Inherits from queue if null |
| `idempotency_key` | string | `null` | Max 255 chars, unique per queue |
| `scheduled_at` | datetime | `null` | **Required** for `delayed`/`scheduled` |
| `cron_expression` | string | `null` | **Required** for `recurring`, max 100 chars |

**Idempotency:** If `idempotency_key` is provided and a job with the same key already exists in this queue, the existing job is returned (no duplicate created). Response is still `201`.

**Response** `201 Created` — `JobResponse`.

**Errors:** `401`, `404 QUEUE_NOT_FOUND`, `422 VALIDATION_ERROR` (missing scheduled_at/cron_expression for relevant types)

---

### `POST /api/v1/queues/{queue_id}/jobs/batch`

Create up to 1000 jobs in a single batch. Requires auth.

**Request Body**
```json
{
  "jobs": [
    {"name": "Job 1", "payload": {"key": "val"}},
    {"name": "Job 2", "payload": {"key": "val"}}
  ]
}
```

| Field | Type | Constraints |
|-------|------|-------------|
| `jobs` | array of `CreateJobRequest` | 1–1000 items |

**Response** `201 Created`
```json
{
  "created": 10,
  "failed": 0,
  "jobs": [...],
  "errors": []
}
```

---

### `GET /api/v1/queues/{queue_id}/jobs`

List jobs with pagination and filtering. Requires auth.

**Query Parameters**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `status` | string | — | Filter by job status |
| `type` | string | — | Filter by job type |
| `page` | int | `1` | ≥ 1 |
| `page_size` | int | `50` | 1–100 |

**Response** `200 OK`
```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "page_size": 50,
  "total_pages": 3
}
```

---

### `GET /api/v1/jobs/{job_id}`

Get job details including execution history. Requires auth.

**Response** `200 OK`
```json
{
  "id": "uuid",
  "queue_id": "uuid",
  "name": "Send email",
  "status": "completed",
  "...": "...",
  "executions": [
    {
      "id": "uuid",
      "job_id": "uuid",
      "worker_id": "uuid",
      "attempt_number": 1,
      "status": "failed",
      "started_at": "...",
      "completed_at": "...",
      "duration_ms": 1523,
      "error_message": "Connection timeout",
      "error_traceback": "..."
    },
    {
      "id": "uuid",
      "attempt_number": 2,
      "status": "completed",
      "duration_ms": 823,
      "error_message": null
    }
  ]
}
```

**Errors:** `401`, `404`

---

### `GET /api/v1/jobs/{job_id}/logs`

Get paginated execution logs for a job. Requires auth.

**Query Parameters**

| Param | Type | Default | Constraints |
|-------|------|---------|-------------|
| `page` | int | `1` | ≥ 1 |
| `page_size` | int | `100` | 1–500 |

**Response** `200 OK`
```json
[
  {
    "id": 1,
    "level": "info",
    "message": "Job completed successfully (attempt 1)",
    "metadata": null,
    "created_at": "2026-01-01T00:00:00Z"
  }
]
```

---

### `POST /api/v1/jobs/{job_id}/retry`

Manually retry a failed or dead job. Requires auth.

**Request Body** (optional)
```json
{
  "reset_retry_count": false
}
```

**Response** `200 OK` — `JobResponse` with `status: "queued"`.

**Errors:** `401`, `404`, `409 CONFLICT` (job not in `failed` or `dead` status)

---

### `POST /api/v1/jobs/{job_id}/cancel`

Cancel a queued or scheduled job. Requires auth.

**Response** `200 OK` — `JobResponse` with `status: "cancelled"`.

**Errors:** `401`, `404`, `409 INVALID_STATE_TRANSITION` (can only cancel `queued` or `scheduled` jobs)

---

## Workers

### `POST /api/v1/workers/register`

Register a worker process. **No user auth required** (called by worker processes).

**Request Body**
```json
{
  "name": "worker-host1-12345",
  "hostname": "host1",
  "pid": 12345,
  "concurrency": 10,
  "queues": ["default", "emails"]
}
```

**Response** `201 Created` — `WorkerResponse`.

---

### `POST /api/v1/workers/{worker_id}/heartbeat`

Send periodic heartbeat with system metrics. **No user auth required.**

**Request Body**
```json
{
  "active_jobs": 3,
  "cpu_usage": 45.2,
  "memory_usage": 60.1
}
```

**Response** `200 OK` — `WorkerResponse` (status updates to `busy` or `idle` based on `active_jobs`).

---

### `POST /api/v1/workers/{worker_id}/claim`

Atomically claim jobs from a queue. **No user auth required.**

**Request Body**
```json
{
  "queue_id": "uuid",
  "batch_size": 5
}
```

| Field | Type | Default | Constraints |
|-------|------|---------|-------------|
| `queue_id` | UUID | — | Required |
| `batch_size` | int | `1` | 1–50 |

**Response** `200 OK` — Array of `JobResponse` (may be empty if queue is paused, empty, or at concurrency limit).

---

### `POST /api/v1/workers/{worker_id}/complete`

Report job completion (success or failure). **No user auth required.**

**Request Body**
```json
{
  "job_id": "uuid",
  "execution_id": "uuid",
  "success": true,
  "result": {"processed": true},
  "error_message": null,
  "error_traceback": null
}
```

**Response** `200 OK` — `JobResponse`.

---

### `POST /api/v1/workers/{worker_id}/deregister`

Gracefully deregister a worker. Releases claimed jobs back to queued. **No user auth required.**

**Response** `200 OK` — `WorkerResponse` with `status: "offline"`.

---

### `GET /api/v1/workers`

List all workers with active job counts. **Requires auth.**

**Query Parameters**

| Param | Type | Notes |
|-------|------|-------|
| `status` | string | Filter by worker status |

**Response** `200 OK`
```json
[
  {
    "id": "uuid",
    "name": "worker-host1-12345",
    "hostname": "host1",
    "pid": 12345,
    "status": "busy",
    "concurrency": 10,
    "queues": ["default"],
    "started_at": "...",
    "last_heartbeat_at": "...",
    "stopped_at": null,
    "active_job_count": 3,
    "total_processed": 150
  }
]
```

---

### `GET /api/v1/workers/{worker_id}`

Get detailed worker information. **Requires auth.**

**Response** `200 OK` — `WorkerDetailResponse`.

---

## Dead Letter Queue

All DLQ endpoints require auth.

### `GET /api/v1/dlq`

List all DLQ entries across all queues (max 200, ordered by moved_at DESC).

**Response** `200 OK`
```json
{
  "items": [
    {
      "id": "uuid",
      "job_id": "uuid",
      "queue_id": "uuid",
      "original_payload": {"key": "value"},
      "failure_reason": "Connection timeout",
      "failure_summary": "[Timeout Error] The job exceeded its execution time limit...",
      "last_error_traceback": "...",
      "total_attempts": 3,
      "moved_at": "...",
      "resolved_at": null,
      "resolved_by": null
    }
  ],
  "total": 5,
  "unresolved": 3
}
```

---

### `GET /api/v1/queues/{queue_id}/dlq`

List DLQ entries for a specific queue.

**Response** `200 OK` — `DLQListResponse`.

---

### `POST /api/v1/dlq/{dlq_id}/retry`

Re-queue a dead job from the DLQ. Resets retry count and all lifecycle timestamps.

**Response** `200 OK` — `DLQEntryResponse` with `resolved_at` set.

**Errors:** `401`, `404`, `409 CONFLICT` (already resolved)

---

### `POST /api/v1/dlq/{dlq_id}/resolve`

Mark a DLQ entry as resolved without retrying (acknowledge and dismiss).

**Response** `200 OK` — `DLQEntryResponse` with `resolved_at` set.

**Errors:** `401`, `404`, `409 CONFLICT` (already resolved)

---

## Metrics

All metrics endpoints require auth.

### `GET /api/v1/metrics/dashboard`

Aggregated system-wide metrics.

**Response** `200 OK`
```json
{
  "total_jobs": 1500,
  "total_queues": 12,
  "total_workers": 5,
  "active_workers": 3,
  "jobs_by_status": {
    "queued": 45,
    "scheduled": 12,
    "claimed": 3,
    "running": 8,
    "completed": 1200,
    "failed": 150,
    "dead": 25,
    "cancelled": 57
  },
  "dlq_unresolved": 10,
  "throughput_per_minute": 15.0,
  "throughput_per_hour": 450.0,
  "avg_execution_ms": 1234.5,
  "success_rate": 87.27
}
```

---

### `GET /api/v1/metrics/throughput`

Throughput time series data.

**Query Parameters**

| Param | Type | Default | Constraints |
|-------|------|---------|-------------|
| `interval` | string | `"minute"` | `minute` or `hour` |
| `periods` | int | `60` | 1–168 |

**Response** `200 OK`
```json
{
  "interval": "minute",
  "points": [
    {"timestamp": "2026-01-01T00:00:00Z", "completed": 5, "failed": 1},
    {"timestamp": "2026-01-01T00:01:00Z", "completed": 8, "failed": 0}
  ]
}
```

---

### `GET /api/v1/metrics/queues`

Per-queue performance metrics.

**Response** `200 OK` — Array of `QueueMetrics`.

---

## WebSocket

### `WS /ws`

Live dashboard updates. **No auth required for connection.**

**Events broadcast to clients:**

| Event | Description |
|-------|-------------|
| `job:created` | New job created |
| `job:claimed` | Job claimed by worker |
| `job:completed` | Job completed |
| `job:failed` | Job failed |
| `worker:heartbeat` | Worker heartbeat received |
| `worker:offline` | Worker went offline |
| `queue:paused` | Queue paused |
| `queue:resumed` | Queue resumed |
| `metrics:update` | Dashboard metrics refresh |

**Client → Server messages:**
```json
{"type": "ping", "timestamp": 1234567890}
```

**Server → Client messages:**
```json
{"event": "job:completed", "data": {...}}
```

Note: WebSocket event broadcasting is defined in the ConnectionManager but events are **not yet wired** from service-layer operations. The infrastructure is in place for future integration.

---

## Common Error Codes

| HTTP Status | Code | Description |
|-------------|------|-------------|
| 401 | `AUTHENTICATION_REQUIRED` | No token provided |
| 401 | `INVALID_CREDENTIALS` | Wrong email/password |
| 401 | `TOKEN_EXPIRED` | JWT token expired |
| 401 | `INVALID_TOKEN` | Malformed or invalid JWT |
| 403 | `FORBIDDEN` | Insufficient role/permissions |
| 404 | `{RESOURCE}_NOT_FOUND` | Resource not found (e.g., `QUEUE_NOT_FOUND`) |
| 409 | `DUPLICATE_RESOURCE` | Unique constraint violation |
| 409 | `CONFLICT` | Generic conflict (e.g., DLQ already resolved) |
| 409 | `INVALID_STATE_TRANSITION` | Invalid job lifecycle transition |
| 409 | `QUEUE_PAUSED` | Queue is paused |
| 422 | `VALIDATION_ERROR` | Request body validation failure |
| 429 | `CONCURRENCY_LIMIT_REACHED` | Queue at concurrency capacity |
| 429 | `RATE_LIMIT_EXCEEDED` | Too many requests |
| 500 | `INTERNAL_ERROR` | Unhandled server error |
