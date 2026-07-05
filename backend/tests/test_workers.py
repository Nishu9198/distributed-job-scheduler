"""
Tests for worker endpoints and operations.
"""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestWorkerEndpoints:
    """Test worker registration and management."""

    async def test_register_worker(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/workers/register",
            json={
                "name": "test-worker-1",
                "hostname": "localhost",
                "pid": 12345,
                "concurrency": 5,
                "queues": ["default", "emails"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-worker-1"
        assert data["status"] == "idle"
        assert data["concurrency"] == 5

    async def test_worker_heartbeat(self, client: AsyncClient):
        # Register
        reg_resp = await client.post(
            "/api/v1/workers/register",
            json={
                "name": "hb-worker",
                "hostname": "localhost",
                "pid": 12346,
            },
        )
        worker_id = reg_resp.json()["id"]

        # Heartbeat
        hb_resp = await client.post(
            f"/api/v1/workers/{worker_id}/heartbeat",
            json={
                "active_jobs": 3,
                "cpu_usage": 45.2,
                "memory_usage": 60.1,
            },
        )
        assert hb_resp.status_code == 200
        assert hb_resp.json()["status"] == "busy"

    async def test_worker_heartbeat_idle(self, client: AsyncClient):
        reg_resp = await client.post(
            "/api/v1/workers/register",
            json={
                "name": "idle-worker",
                "hostname": "localhost",
                "pid": 12347,
            },
        )
        worker_id = reg_resp.json()["id"]

        hb_resp = await client.post(
            f"/api/v1/workers/{worker_id}/heartbeat",
            json={"active_jobs": 0},
        )
        assert hb_resp.json()["status"] == "idle"

    async def test_deregister_worker(self, client: AsyncClient):
        reg_resp = await client.post(
            "/api/v1/workers/register",
            json={
                "name": "temp-worker",
                "hostname": "localhost",
                "pid": 12348,
            },
        )
        worker_id = reg_resp.json()["id"]

        dereg_resp = await client.post(
            f"/api/v1/workers/{worker_id}/deregister",
        )
        assert dereg_resp.status_code == 200
        assert dereg_resp.json()["status"] == "offline"

    async def test_list_workers(self, client: AsyncClient, auth_headers: dict):
        # Register a few workers
        for i in range(3):
            await client.post(
                "/api/v1/workers/register",
                json={
                    "name": f"list-worker-{i}",
                    "hostname": "localhost",
                    "pid": 20000 + i,
                },
            )

        response = await client.get(
            "/api/v1/workers",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert len(response.json()) >= 3
