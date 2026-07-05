"""
Tests for authentication endpoints.

Covers: registration, login, token refresh, validation errors.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAuthRegistration:
    """Test user registration flow."""

    async def test_register_success(self, client: AsyncClient):
        """Valid registration should return user + tokens."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "new@example.com",
                "password": "StrongPass1!",
                "full_name": "New User",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["user"]["email"] == "new@example.com"
        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]
        assert data["tokens"]["token_type"] == "bearer"

    async def test_register_duplicate_email(self, client: AsyncClient):
        """Duplicate email should return 409."""
        payload = {
            "email": "dup@example.com",
            "password": "StrongPass1!",
            "full_name": "User One",
        }
        await client.post("/api/v1/auth/register", json=payload)
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "DUPLICATE_RESOURCE"

    async def test_register_weak_password(self, client: AsyncClient):
        """Password without uppercase should fail validation."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "weak@example.com",
                "password": "nouppercasehere1",
                "full_name": "Weak Password User",
            },
        )
        assert response.status_code == 422

    async def test_register_short_password(self, client: AsyncClient):
        """Password under 8 chars should fail validation."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "short@example.com",
                "password": "Ab1!",
                "full_name": "Short Password",
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestAuthLogin:
    """Test login flow."""

    async def test_login_success(self, client: AsyncClient):
        """Valid credentials should return tokens."""
        # Register first
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "login@example.com",
                "password": "LoginPass1!",
                "full_name": "Login User",
            },
        )
        # Login
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "LoginPass1!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data["tokens"]

    async def test_login_invalid_password(self, client: AsyncClient):
        """Wrong password should return 401."""
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "wrongpw@example.com",
                "password": "CorrectPass1!",
                "full_name": "Wrong PW User",
            },
        )
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrongpw@example.com", "password": "WrongPassword1!"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Non-existent email should return 401."""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "DoesNotMatter1!"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAuthTokenRefresh:
    """Test token refresh flow."""

    async def test_refresh_success(self, client: AsyncClient):
        """Valid refresh token should return new access token."""
        reg_response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "refresh@example.com",
                "password": "RefreshPass1!",
                "full_name": "Refresh User",
            },
        )
        refresh_token = reg_response.json()["tokens"]["refresh_token"]

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    async def test_refresh_invalid_token(self, client: AsyncClient):
        """Invalid refresh token should return 401."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.token.here"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestProtectedEndpoints:
    """Test that protected endpoints require authentication."""

    async def test_unauthenticated_request(self, client: AsyncClient):
        """Request without token should return 401."""
        response = await client.get("/api/v1/organizations")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    async def test_invalid_token(self, client: AsyncClient):
        """Request with invalid token should return 401."""
        response = await client.get(
            "/api/v1/organizations",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert response.status_code == 401
