"""
Tests for job and queue API endpoints.

Covers: queue CRUD, job CRUD, batch creation, filtering, pagination.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _setup_org_project(client: AsyncClient, headers: dict) -> tuple[str, str]:
    """Helper: create org and project, return their IDs."""
    org_resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Test Org", "slug": f"test-org-{uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    org_id = org_resp.json()["id"]

    proj_resp = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"name": "Test Project", "slug": f"test-proj-{uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    proj_id = proj_resp.json()["id"]
    return org_id, proj_id


@pytest.mark.asyncio
class TestQueueEndpoints:
    """Test queue CRUD operations."""

    async def test_create_queue(self, client: AsyncClient, auth_headers: dict):
        _, proj_id = await _setup_org_project(client, auth_headers)
        slug = f"test-queue-{uuid.uuid4().hex[:6]}"

        response = await client.post(
            f"/api/v1/projects/{proj_id}/queues",
            json={
                "name": "Test Queue",
                "slug": slug,
                "priority": 8,
                "concurrency_limit": 15,
                "max_retries": 5,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Queue"
        assert data["priority"] == 8
        assert data["concurrency_limit"] == 15
        assert data["is_paused"] is False

    async def test_list_queues(self, client: AsyncClient, auth_headers: dict):
        _, proj_id = await _setup_org_project(client, auth_headers)

        # Create two queues
        for i in range(2):
            await client.post(
                f"/api/v1/projects/{proj_id}/queues",
                json={"name": f"Queue {i}", "slug": f"queue-{i}-{uuid.uuid4().hex[:6]}"},
                headers=auth_headers,
            )

        response = await client.get(
            f"/api/v1/projects/{proj_id}/queues",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert len(response.json()) >= 2

    async def test_pause_resume_queue(self, client: AsyncClient, auth_headers: dict):
        _, proj_id = await _setup_org_project(client, auth_headers)
        slug = f"pausable-{uuid.uuid4().hex[:6]}"

        create_resp = await client.post(
            f"/api/v1/projects/{proj_id}/queues",
            json={"name": "Pausable Queue", "slug": slug},
            headers=auth_headers,
        )
        queue_id = create_resp.json()["id"]

        # Pause
        pause_resp = await client.post(
            f"/api/v1/queues/{queue_id}/pause",
            headers=auth_headers,
        )
        assert pause_resp.status_code == 200
        assert pause_resp.json()["is_paused"] is True

        # Resume
        resume_resp = await client.post(
            f"/api/v1/queues/{queue_id}/resume",
            headers=auth_headers,
        )
        assert resume_resp.status_code == 200
        assert resume_resp.json()["is_paused"] is False


@pytest.mark.asyncio
class TestJobEndpoints:
    """Test job CRUD operations."""

    async def _create_queue(self, client, auth_headers) -> str:
        _, proj_id = await _setup_org_project(client, auth_headers)
        slug = f"job-queue-{uuid.uuid4().hex[:6]}"
        resp = await client.post(
            f"/api/v1/projects/{proj_id}/queues",
            json={"name": "Job Queue", "slug": slug},
            headers=auth_headers,
        )
        return resp.json()["id"]

    async def test_create_immediate_job(self, client: AsyncClient, auth_headers: dict):
        queue_id = await self._create_queue(client, auth_headers)

        response = await client.post(
            f"/api/v1/queues/{queue_id}/jobs",
            json={
                "name": "Send email",
                "type": "immediate",
                "payload": {"to": "user@example.com", "template": "welcome"},
                "priority": 8,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "queued"
        assert data["type"] == "immediate"
        assert data["priority"] == 8

    async def test_create_scheduled_job(self, client: AsyncClient, auth_headers: dict):
        queue_id = await self._create_queue(client, auth_headers)

        response = await client.post(
            f"/api/v1/queues/{queue_id}/jobs",
            json={
                "name": "Generate report",
                "type": "scheduled",
                "payload": {"report_type": "monthly"},
                "scheduled_at": "2030-01-01T00:00:00Z",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["status"] == "scheduled"

    async def test_create_recurring_job(self, client: AsyncClient, auth_headers: dict):
        queue_id = await self._create_queue(client, auth_headers)

        response = await client.post(
            f"/api/v1/queues/{queue_id}/jobs",
            json={
                "name": "Nightly cleanup",
                "type": "recurring",
                "payload": {"tables": ["sessions"]},
                "cron_expression": "0 2 * * *",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["type"] == "recurring"
        assert response.json()["cron_expression"] == "0 2 * * *"

    async def test_batch_create_jobs(self, client: AsyncClient, auth_headers: dict):
        queue_id = await self._create_queue(client, auth_headers)

        jobs = [
            {"name": f"Batch job {i}", "payload": {"index": i}}
            for i in range(10)
        ]
        response = await client.post(
            f"/api/v1/queues/{queue_id}/jobs/batch",
            json={"jobs": jobs},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["created"] == 10
        assert data["failed"] == 0

    async def test_list_jobs_with_pagination(self, client: AsyncClient, auth_headers: dict):
        queue_id = await self._create_queue(client, auth_headers)

        # Create 15 jobs
        for i in range(15):
            await client.post(
                f"/api/v1/queues/{queue_id}/jobs",
                json={"name": f"Job {i}", "payload": {}},
                headers=auth_headers,
            )

        # Page 1
        resp1 = await client.get(
            f"/api/v1/queues/{queue_id}/jobs?page=1&page_size=10",
            headers=auth_headers,
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert len(data1["items"]) == 10
        assert data1["total"] == 15
        assert data1["total_pages"] == 2

        # Page 2
        resp2 = await client.get(
            f"/api/v1/queues/{queue_id}/jobs?page=2&page_size=10",
            headers=auth_headers,
        )
        assert len(resp2.json()["items"]) == 5

    async def test_idempotency_key(self, client: AsyncClient, auth_headers: dict):
        queue_id = await self._create_queue(client, auth_headers)

        payload = {
            "name": "Idempotent job",
            "payload": {},
            "idempotency_key": "unique-key-123",
        }

        resp1 = await client.post(
            f"/api/v1/queues/{queue_id}/jobs",
            json=payload,
            headers=auth_headers,
        )
        resp2 = await client.post(
            f"/api/v1/queues/{queue_id}/jobs",
            json=payload,
            headers=auth_headers,
        )

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        # Should return the same job (idempotent)
        assert resp1.json()["id"] == resp2.json()["id"]

    async def test_cancel_job(self, client: AsyncClient, auth_headers: dict):
        queue_id = await self._create_queue(client, auth_headers)

        create_resp = await client.post(
            f"/api/v1/queues/{queue_id}/jobs",
            json={"name": "Cancellable", "payload": {}},
            headers=auth_headers,
        )
        job_id = create_resp.json()["id"]

        cancel_resp = await client.post(
            f"/api/v1/jobs/{job_id}/cancel",
            headers=auth_headers,
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"
