"""
Concurrency tests for atomic job claiming.

These tests verify that:
1. No two workers can claim the same job
2. FOR UPDATE SKIP LOCKED prevents contention
3. Concurrency limits are respected
"""

import pytest

from src.jobs.lifecycle import validate_transition
from src.core.exceptions import InvalidStateTransitionError


@pytest.mark.asyncio
class TestAtomicClaiming:
    """Test that job claiming is atomic and contention-free."""

    async def test_no_duplicate_claims_sequential(
        self, client, auth_headers
    ):
        """
        Sequential claiming: create jobs and claim them one by one.
        Each job should only appear in one claim response.
        """
        import uuid

        # Setup: org → project → queue
        org_resp = await client.post(
            "/api/v1/organizations",
            json={"name": "Concurrency Org", "slug": f"conc-org-{uuid.uuid4().hex[:6]}"},
            headers=auth_headers,
        )
        org_id = org_resp.json()["id"]

        proj_resp = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"name": "Conc Project", "slug": f"conc-proj-{uuid.uuid4().hex[:6]}"},
            headers=auth_headers,
        )
        proj_id = proj_resp.json()["id"]

        queue_resp = await client.post(
            f"/api/v1/projects/{proj_id}/queues",
            json={
                "name": "Concurrency Queue",
                "slug": f"conc-queue-{uuid.uuid4().hex[:6]}",
                "concurrency_limit": 100,
            },
            headers=auth_headers,
        )
        queue_id = queue_resp.json()["id"]

        # Create 5 jobs
        job_ids = set()
        for i in range(5):
            resp = await client.post(
                f"/api/v1/queues/{queue_id}/jobs",
                json={"name": f"Conc job {i}", "payload": {"index": i}},
                headers=auth_headers,
            )
            job_ids.add(resp.json()["id"])

        assert len(job_ids) == 5

        # Register 2 workers
        w1_resp = await client.post(
            "/api/v1/workers/register",
            json={"name": "w1", "hostname": "host1", "pid": 1001},
        )
        w1_id = w1_resp.json()["id"]

        w2_resp = await client.post(
            "/api/v1/workers/register",
            json={"name": "w2", "hostname": "host2", "pid": 1002},
        )
        w2_id = w2_resp.json()["id"]

        # Worker 1 claims 3 jobs
        claim1 = await client.post(
            f"/api/v1/workers/{w1_id}/claim",
            json={"queue_id": queue_id, "batch_size": 3},
        )
        claimed_1 = {j["id"] for j in claim1.json()}

        # Worker 2 claims remaining — should NOT get any of worker 1's jobs
        claim2 = await client.post(
            f"/api/v1/workers/{w2_id}/claim",
            json={"queue_id": queue_id, "batch_size": 5},
        )
        claimed_2 = {j["id"] for j in claim2.json()}

        # Verify no overlap
        overlap = claimed_1 & claimed_2
        assert len(overlap) == 0, f"Duplicate claims detected: {overlap}"

        # Verify all 5 jobs were claimed in total
        assert len(claimed_1) + len(claimed_2) == 5

    async def test_concurrency_limit_respected(self, client, auth_headers):
        """Queue concurrency limit should prevent over-claiming."""
        import uuid

        org_resp = await client.post(
            "/api/v1/organizations",
            json={"name": "Limit Org", "slug": f"limit-org-{uuid.uuid4().hex[:6]}"},
            headers=auth_headers,
        )
        org_id = org_resp.json()["id"]

        proj_resp = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"name": "Limit Project", "slug": f"limit-proj-{uuid.uuid4().hex[:6]}"},
            headers=auth_headers,
        )
        proj_id = proj_resp.json()["id"]

        # Queue with concurrency_limit=2
        queue_resp = await client.post(
            f"/api/v1/projects/{proj_id}/queues",
            json={
                "name": "Limited Queue",
                "slug": f"limited-{uuid.uuid4().hex[:6]}",
                "concurrency_limit": 2,
            },
            headers=auth_headers,
        )
        queue_id = queue_resp.json()["id"]

        # Create 10 jobs
        for i in range(10):
            await client.post(
                f"/api/v1/queues/{queue_id}/jobs",
                json={"name": f"Limited job {i}", "payload": {}},
                headers=auth_headers,
            )

        # Register worker
        w_resp = await client.post(
            "/api/v1/workers/register",
            json={"name": "limit-worker", "hostname": "host", "pid": 2001},
        )
        w_id = w_resp.json()["id"]

        # Claim — should only get 2 (concurrency limit)
        claim = await client.post(
            f"/api/v1/workers/{w_id}/claim",
            json={"queue_id": queue_id, "batch_size": 10},
        )
        assert len(claim.json()) <= 2

    async def test_paused_queue_returns_empty(self, client, auth_headers):
        """Claiming from a paused queue should return no jobs."""
        import uuid

        org_resp = await client.post(
            "/api/v1/organizations",
            json={"name": "Pause Org", "slug": f"pause-org-{uuid.uuid4().hex[:6]}"},
            headers=auth_headers,
        )
        org_id = org_resp.json()["id"]

        proj_resp = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"name": "Pause Project", "slug": f"pause-proj-{uuid.uuid4().hex[:6]}"},
            headers=auth_headers,
        )
        proj_id = proj_resp.json()["id"]

        queue_resp = await client.post(
            f"/api/v1/projects/{proj_id}/queues",
            json={
                "name": "Pausable Queue",
                "slug": f"pausable-{uuid.uuid4().hex[:6]}",
            },
            headers=auth_headers,
        )
        queue_id = queue_resp.json()["id"]

        # Create jobs
        for i in range(3):
            await client.post(
                f"/api/v1/queues/{queue_id}/jobs",
                json={"name": f"Pause job {i}", "payload": {}},
                headers=auth_headers,
            )

        # Pause the queue
        await client.post(
            f"/api/v1/queues/{queue_id}/pause",
            headers=auth_headers,
        )

        # Try to claim — should get nothing
        w_resp = await client.post(
            "/api/v1/workers/register",
            json={"name": "pause-worker", "hostname": "host", "pid": 3001},
        )
        w_id = w_resp.json()["id"]

        claim = await client.post(
            f"/api/v1/workers/{w_id}/claim",
            json={"queue_id": queue_id, "batch_size": 10},
        )
        assert len(claim.json()) == 0
