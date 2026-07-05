"""
Structured exception hierarchy for the application.

All exceptions produce consistent JSON error responses with:
- error code (machine-readable)
- message (human-readable)
- details (optional structured data)
- request_id (for tracing)
"""

from typing import Any, Optional


class AppException(Exception):
    """Base exception for all application errors."""

    def __init__(
        self,
        status_code: int = 500,
        code: str = "INTERNAL_ERROR",
        message: str = "An unexpected error occurred",
        details: Optional[dict[str, Any]] = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


# ─── Authentication Errors ───────────────────────────────────
class AuthenticationError(AppException):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(status_code=401, code="AUTHENTICATION_REQUIRED", message=message)


class InvalidCredentialsError(AppException):
    def __init__(self):
        super().__init__(
            status_code=401,
            code="INVALID_CREDENTIALS",
            message="Invalid email or password",
        )


class TokenExpiredError(AppException):
    def __init__(self):
        super().__init__(
            status_code=401, code="TOKEN_EXPIRED", message="Token has expired"
        )


class InvalidTokenError(AppException):
    def __init__(self):
        super().__init__(
            status_code=401, code="INVALID_TOKEN", message="Invalid or malformed token"
        )


# ─── Authorization Errors ───────────────────────────────────
class ForbiddenError(AppException):
    def __init__(self, message: str = "You do not have permission to perform this action"):
        super().__init__(status_code=403, code="FORBIDDEN", message=message)


# ─── Resource Errors ────────────────────────────────────────
class NotFoundError(AppException):
    def __init__(self, resource: str, identifier: str = ""):
        detail_msg = f"{resource} not found"
        if identifier:
            detail_msg = f"{resource} with ID '{identifier}' not found"
        super().__init__(
            status_code=404,
            code=f"{resource.upper().replace(' ', '_')}_NOT_FOUND",
            message=detail_msg,
        )


class ConflictError(AppException):
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(status_code=409, code="CONFLICT", message=message)


class DuplicateError(AppException):
    def __init__(self, resource: str, field: str, value: str):
        super().__init__(
            status_code=409,
            code="DUPLICATE_RESOURCE",
            message=f"{resource} with {field} '{value}' already exists",
            details={"field": field, "value": value},
        )


# ─── Validation Errors ──────────────────────────────────────
class ValidationError(AppException):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            status_code=422, code="VALIDATION_ERROR", message=message, details=details
        )


# ─── Business Logic Errors ──────────────────────────────────
class InvalidStateTransitionError(AppException):
    def __init__(self, current_state: str, target_state: str, resource: str = "Job"):
        super().__init__(
            status_code=409,
            code="INVALID_STATE_TRANSITION",
            message=f"Cannot transition {resource} from '{current_state}' to '{target_state}'",
            details={"current_state": current_state, "target_state": target_state},
        )


class QueuePausedError(AppException):
    def __init__(self, queue_name: str):
        super().__init__(
            status_code=409,
            code="QUEUE_PAUSED",
            message=f"Queue '{queue_name}' is currently paused",
        )


class ConcurrencyLimitError(AppException):
    def __init__(self, queue_name: str, limit: int):
        super().__init__(
            status_code=429,
            code="CONCURRENCY_LIMIT_REACHED",
            message=f"Queue '{queue_name}' has reached its concurrency limit of {limit}",
        )


class RateLimitError(AppException):
    def __init__(self, retry_after: int = 60):
        super().__init__(
            status_code=429,
            code="RATE_LIMIT_EXCEEDED",
            message="Rate limit exceeded. Please try again later.",
            details={"retry_after_seconds": retry_after},
        )
