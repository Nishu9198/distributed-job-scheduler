"""
Auth domain — API router.

Thin router pattern: routes only handle HTTP concerns (parsing, status codes).
All business logic is delegated to AuthService.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import (
    AuthResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from src.auth.service import AuthService
from src.core.database import get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a new user account and return authentication tokens."""
    service = AuthService(db)
    return await service.register(data)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Authenticate with email and password",
)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user credentials and return JWT tokens."""
    service = AuthService(db)
    return await service.login(data)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
)
async def refresh_token(
    data: RefreshTokenRequest, db: AsyncSession = Depends(get_db)
):
    """Exchange a valid refresh token for a new access token."""
    service = AuthService(db)
    return await service.refresh(data.refresh_token)
