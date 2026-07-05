"""
FastAPI dependencies for injection into route handlers.

Provides authenticated user context and database sessions.
"""

from typing import Optional

import jwt
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import get_db
from src.core.exceptions import (
    AuthenticationError,
    ForbiddenError,
    InvalidTokenError,
    TokenExpiredError,
)
from src.core.security import decode_token

settings = get_settings()


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Dependency that extracts and validates the JWT from the Authorization header.
    Returns the authenticated user ORM object.

    Raises:
        AuthenticationError: If no token is provided.
        TokenExpiredError: If the token has expired.
        InvalidTokenError: If the token is invalid.
    """
    if not authorization:
        raise AuthenticationError()

    # Support "Bearer <token>" format
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Invalid authorization header format. Use: Bearer <token>")

    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError:
        raise InvalidTokenError()

    if payload.get("type") != "access":
        raise InvalidTokenError()

    user_id = payload.get("sub")
    if not user_id:
        raise InvalidTokenError()

    # Import here to avoid circular imports
    from src.auth.models import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise InvalidTokenError()

    return user


async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Optional auth dependency — returns None if no token provided."""
    if not authorization:
        return None
    return await get_current_user(authorization, db)


def require_role(allowed_roles: list[str]):
    """
    Factory dependency that enforces role-based access control.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_role(["admin"]))])
    """

    async def role_checker(
        current_user=Depends(get_current_user),
    ):
        if current_user.role not in allowed_roles:
            raise ForbiddenError(
                f"This action requires one of the following roles: {', '.join(allowed_roles)}"
            )
        return current_user

    return role_checker
