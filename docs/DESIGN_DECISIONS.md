# Design Decisions

## 1. Retry Strategy

### What's Implemented

The system supports **three configurable retry strategies** via the `RetryPolicy` entity: `fixed`, `linear`, and `exponential`. Retry policies are reusable — one policy can be attached to multiple queues via `retry_policy_id`.

The retry delay calculation lives in `JobService._calculate_retry_delay()` (`src/jobs/service.py`, lines 602–636):

```python
if strategy == "fixed":
    delay = base_delay
elif strategy == "linear":
    delay = base_delay * attempt
elif strategy == "exponential":
    delay = base_delay * (multiplier ** (attempt - 1))
```

**Jitter** is applied to every strategy to prevent thundering herd:

```python
jitter = delay * jitter_pct * (random.random() * 2 - 1)
delay = max(base_delay, min(delay + jitter, max_delay))
```

The jitter adds ±`jitter_pct` of the delay (default ±20%), then clamps the result between `base_delay` and `max_delay`.

### Default Behavior

If no `RetryPolicy` is attached to a queue, the system falls back to hardcoded defaults:
- Strategy: `exponential`
- Base delay: 1000ms
- Max delay: 300,000ms (5 minutes)
- Multiplier: 2.0
- Jitter: 0.2 (±20%)

### Retry Flow

When a job fails (`fail_job` in `src/jobs/service.py`):

1. Lifecycle validates the `running → failed` transition
2. `retry_count` is incremented
3. If `retry_count < max_retries`:
   - Status is set to `scheduled` (not `queued`) with a calculated `scheduled_at` in the future
   - The Scheduler Engine promotes it to `queued` when `scheduled_at <= NOW()`
4. If `retry_count >= max_retries`:
   - Status is set to `dead`
   - A `DeadLetterQueueEntry` is created with the original payload, failure reason, and a pattern-matched failure summary

### Why Exponential Backoff (Default)

Exponential backoff is the default because most transient failures (network timeouts, rate limits, service restarts) resolve within seconds to minutes. Fixed delays risk overwhelming a recovering service, while exponential backoff provides increasing breathing room. Jitter prevents synchronized retries from multiple failed jobs creating a stampede.

---

## 2. Atomic Job Claiming

### The Mechanism: `FOR UPDATE SKIP LOCKED`

Job claiming uses a **single raw SQL query** that atomically selects and updates in one statement. This is the core of the system's concurrency safety. The full query is in `JobService.claim_jobs()` (`src/jobs/service.py`, lines 278–304):

```sql
WITH claimable AS (
    SELECT j.id
    FROM jobs j
    WHERE j.queue_id = :queue_id
      AND j.status = 'queued'
    ORDER BY j.priority DESC, j.created_at ASC
    LIMIT :limit
    FOR UPDATE OF j SKIP LOCKED
)
UPDATE jobs
SET status = 'claimed',
    claimed_at = NOW(),
    updated_at = NOW(),
    worker_id = :worker_id
WHERE id IN (SELECT id FROM claimable)
RETURNING id, queue_id, name, idempotency_key, type, status,
          payload, result, priority, max_retries, retry_count,
          scheduled_at, cron_expression, worker_id,
          created_at, updated_at, claimed_at, started_at, completed_at
```

### Why This Approach

1. **`FOR UPDATE`** places an exclusive row-level lock on selected rows, preventing any other transaction from reading or modifying them until the lock is released.

2. **`SKIP LOCKED`** is the key innovation — instead of waiting for locked rows (which would cause contention), workers simply skip over rows that another worker has already locked. This makes concurrent claiming **contention-free**.

3. **CTE + UPDATE in one statement** ensures the select and update happen atomically. There's no window between "I found a job" and "I claimed it" where another worker could steal it.

4. **Priority ordering** (`ORDER BY priority DESC, created_at ASC`) ensures high-priority jobs are claimed first, with FIFO ordering within the same priority level.

### Supporting Index

The query is backed by a composite index designed specifically for this hot path:

```python
Index("ix_job_claim_path", "queue_id", "status", "priority", "created_at")
```

This index covers all the WHERE, ORDER BY, and LIMIT clauses, enabling an efficient index scan rather than a sequential table scan.

### Concurrency Limit Enforcement

Before the atomic claim query, the service checks the queue's concurrency limit:

```python
running_count = await self.db.execute(
    select(func.count()).where(
        Job.queue_id == queue_id,
        Job.status.in_(["claimed", "running"]),
    )
)
current_running = running_count.scalar() or 0
available_slots = max(0, queue.concurrency_limit - current_running)
```

This is a soft limit — the count and the claim are not in the same lock, so under extreme concurrency there's a theoretical race. However, `SKIP LOCKED` ensures that even if two workers both see available slots, they won't claim the same job.

---

## 3. Idempotency

### What's Implemented

Idempotency is implemented at the **job creation level** via the `idempotency_key` field. The mechanism in `JobService.create()` (`src/jobs/service.py`, lines 83–93):

```python
if data.idempotency_key:
    existing = await self.db.execute(
        select(Job).where(
            Job.queue_id == queue_id,
            Job.idempotency_key == data.idempotency_key,
        )
    )
    existing_job = existing.scalar_one_or_none()
    if existing_job:
        # Idempotent: return existing job instead of creating duplicate
        return JobResponse.model_validate(existing_job)
```

**Key design choices:**
- Idempotency keys are **scoped per queue** (not globally unique). The database enforces this via `UniqueConstraint("idempotency_key", "queue_id", name="uq_job_idempotency_key_queue")`.
- If a duplicate key is found, the existing job is returned with a `201` status — the client sees success regardless of whether the job was already created.
- Idempotency keys are **optional** (`nullable=True`). Jobs without keys can be submitted multiple times without dedup.

### What's NOT Implemented

- **Idempotency for other operations** (completion, failure reporting, API mutations) is not implemented. If a worker's completion report is lost and retried, the lifecycle validation (`validate_transition`) will reject the duplicate transition (e.g., `completed → completed` is invalid), effectively preventing double-completion at the state machine level — though this wasn't designed as an explicit idempotency mechanism.
- **Idempotency key expiration** is not implemented. Keys persist indefinitely, which means you cannot reuse an idempotency key even after the original job completes.
- **Request-level idempotency** (e.g., `Idempotency-Key` header for arbitrary API calls) is not implemented.

---

## 4. Job Lifecycle State Machine

The lifecycle is enforced by a standalone state machine in `src/jobs/lifecycle.py` with an explicit transition map:

```
queued → {claimed, cancelled, scheduled}
scheduled → {queued, cancelled}
claimed → {running, queued}          # queued = release back (worker crash recovery)
running → {completed, failed}
failed → {queued, dead}              # queued = retry, dead = DLQ
completed → {}                       # terminal
dead → {queued}                      # manual DLQ retry only
cancelled → {}                       # terminal
```

Every status change calls `validate_transition()` which raises `InvalidStateTransitionError` (HTTP 409) for invalid transitions. This prevents data corruption from bugs or race conditions.

---

## 5. Dead Letter Queue

The DLQ is fully implemented with its own table (`dead_letter_queue`), service, and API endpoints.

When a job exhausts all retries, `fail_job()` creates a `DeadLetterQueueEntry` with:
- **Original payload** (preserved separately because jobs may be modified)
- **Failure reason** (the error message from the last attempt)
- **AI-style failure summary** — pattern-matched classification from `_generate_failure_summary()` that categorizes errors into types (Timeout, Connection, Memory, Rate Limit, etc.) with actionable suggestions
- **Total attempts** count
- **Traceback** from the final execution

Operators can **retry** (re-queues the job with reset retry count) or **resolve** (mark as acknowledged) via the DLQ API. Both actions record `resolved_at` and `resolved_by`.

---

## 6. Worker Heartbeats & Stale Detection

### Heartbeats

Workers send heartbeats every `WORKER_HEARTBEAT_INTERVAL` seconds (default 30). Each heartbeat:
- Updates `Worker.last_heartbeat_at`
- Sets status to `busy` or `idle` based on `active_jobs > 0`
- Creates a `WorkerHeartbeat` row with active job count, CPU usage, and memory usage

### Stale Worker Detection

The worker engine runs a `_stale_worker_check_loop` every 60 seconds. A worker is stale if `last_heartbeat_at < NOW() - WORKER_STALE_THRESHOLD` (default 90 seconds). Stale workers are:
1. Marked as `offline`
2. Their `claimed` and `running` jobs are re-queued via a bulk `UPDATE ... SET status = 'queued', worker_id = NULL`

---

## 7. Scheduled Job Promotion

Both the API-side `SchedulerEngine` (10-second interval) and the Worker-side `_scheduler_promotion_loop` (5-second interval) promote due scheduled jobs. Both use `FOR UPDATE SKIP LOCKED` to avoid conflicts:

```sql
WITH claimable AS (
    SELECT id FROM jobs
    WHERE status = 'scheduled'
      AND scheduled_at <= :now
    FOR UPDATE SKIP LOCKED
)
UPDATE jobs
SET status = 'queued',
    updated_at = :now
WHERE id IN (SELECT id FROM claimable)
RETURNING id, type
```

A partial index `ix_job_scheduled_due(scheduled_at) WHERE status = 'scheduled'` ensures this query only scans relevant rows.

---

## 8. Recurring (Cron) Jobs

Recurring jobs use `croniter` to calculate the next execution time. When a recurring job completes, `_schedule_next_recurring()` creates a **new** Job row (not recycling the current one) with:
- Same `name`, `payload`, `priority`, `max_retries`, `cron_expression`
- New `scheduled_at` based on `croniter.get_next()`
- Status `scheduled`

This means each execution of a recurring job is a separate row with its own execution history. The cron chain is implicit (via the `cron_expression` field) rather than tracked with a parent-child relationship.

---

## 9. Known Limitations

### Implemented But Incomplete
- **WebSocket events:** The `ConnectionManager` and broadcast infrastructure are implemented, but service-layer operations (job creation, completion, failure, etc.) do **not yet call `broadcast_event()`**. The wiring is missing.
- **Redis:** Provisioned in docker-compose and listed in requirements, but not used for anything at runtime. The WebSocket module comments note it's intended for multi-process pub/sub.
- **Rate limiting:** `rate_limit_per_second` is stored on queues and `RateLimitError` is defined, but rate limiting is **not enforced** during job claiming or API requests. The middleware for rate limiting is not implemented.
- **Concurrency limit enforcement:** The check before `claim_jobs` is a soft check (read-then-write race). Under extreme concurrency, slightly more than `concurrency_limit` jobs could be claimed.

### Not Implemented
- **Job handler registry:** Workers simulate job execution (`_run_job_handler` sleeps for a configurable duration). There's no mechanism to register actual handler functions by job name/type.
- **Job timeout enforcement:** No per-job timeout. A hanging job will only be recovered when the worker's heartbeat goes stale.
- **Distributed locking:** No use of Redis/advisory locks for coordinating schedulers or workers beyond `SKIP LOCKED`.
- **Job dependencies/DAGs:** No job chaining, parent-child relationships, or directed acyclic graph execution.
- **Batch failure atomicity:** In `batch_create`, individual job creation failures are caught and accumulated in `errors[]`, but the overall transaction still commits successfully created jobs. No all-or-nothing option.
- **Queue-level rate limiting enforcement:** The `rate_limit_per_second` column exists but is never checked during claiming.
- **Pagination on DLQ list_all:** Hardcoded `LIMIT 200` with no pagination parameters.
- **Worker authentication:** Worker endpoints (register, heartbeat, claim, complete, deregister) have **no auth** — any caller can impersonate a worker. In production, these would need API key or mutual TLS authentication.
- **Idempotency key expiration:** Keys never expire, preventing reuse.
- **Metrics caching:** Dashboard metrics queries are computed on every request with no caching. At scale, these aggregation queries would become expensive.
- **Multi-tenancy isolation:** All organizations share the same database and queues. There's no tenant-level isolation in the query layer.

### Things I'd Improve With More Time
1. **Wire WebSocket broadcasts** from service-layer operations for real-time dashboard updates
2. **Implement Redis pub/sub** for WebSocket broadcasting across multiple API instances
3. **Add worker authentication** (API keys or mutual TLS)
4. **Enforce rate limiting** using Redis token bucket (the column and error class already exist)
5. **Add job timeouts** with a configurable per-job `timeout_seconds` and a timeout-detection loop in the worker
6. **Implement a job handler registry** so workers can dispatch to actual handler functions
7. **Strengthen concurrency limit** enforcement with `SELECT ... FOR UPDATE` on the concurrency check
8. **Add DLQ pagination** and filtering (by queue, resolved status, date range)
9. **Cache dashboard metrics** in Redis with TTL-based invalidation
10. **Add OpenTelemetry tracing** for end-to-end distributed tracing (the request ID middleware is a starting point)
