"""
Standardized error model with retry semantics.

This module defines a hierarchy of service errors that classify whether
an error is retryable, allowing callers to make intelligent retry decisions.
"""

from __future__ import annotations

import uuid
from typing import Any


class ServiceError(Exception):
    """Standardized service error with retry classification.

    ServiceError carries structured information about failures:
    - code: Machine-readable error code (e.g., "STORAGE_UNAVAILABLE")
    - message_safe: Human-readable message safe for logs/users
    - message_debug: Detailed debug info (not logged in production)
    - retryable: Whether the operation can be retried
    - cause: The underlying exception, if any
    - debug_id: Unique ID for support correlation

    Attributes:
        code: Error code for programmatic handling.
        message_safe: Safe message for logging and user display.
        message_debug: Optional detailed message for debugging.
        retryable: Whether this error can be retried.
        cause: Optional underlying exception.
        debug_id: Unique identifier for support tickets.
    """

    def __init__(
        self,
        code: str,
        message_safe: str,
        message_debug: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
        debug_id: str | None = None,
    ):
        """Initialize a ServiceError.

        Args:
            code: Machine-readable error code.
            message_safe: Human-readable message safe for logs.
            message_debug: Optional detailed debug message.
            retryable: Whether the operation can be retried.
            cause: Optional underlying exception.
            debug_id: Optional correlation ID (auto-generated if None).
        """
        super().__init__(message_safe)
        self.code = code
        self.message_safe = message_safe
        self.message_debug = message_debug
        self.retryable = retryable
        self.cause = cause
        self.debug_id = debug_id or str(uuid.uuid4())[:8]

    def __str__(self) -> str:
        """Return string representation."""
        return f"[{self.code}] {self.message_safe}"

    def __repr__(self) -> str:
        """Return detailed representation."""
        return (
            f"ServiceError(code={self.code!r}, "
            f"message_safe={self.message_safe!r}, "
            f"retryable={self.retryable}, "
            f"debug_id={self.debug_id!r})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses.

        Returns:
            Dictionary with error details (excludes debug info).
        """
        return {
            "code": self.code,
            "message": self.message_safe,
            "debug_id": self.debug_id,
        }


class RetryableError(ServiceError):
    """Error that indicates the operation can be retried.

    Use this for transient failures like:
    - Network timeouts
    - Rate limiting (429)
    - Temporary service unavailability (503)
    """

    def __init__(
        self,
        code: str,
        message_safe: str,
        message_debug: str | None = None,
        cause: Exception | None = None,
        debug_id: str | None = None,
    ):
        """Initialize a RetryableError.

        Args:
            code: Machine-readable error code.
            message_safe: Human-readable message safe for logs.
            message_debug: Optional detailed debug message.
            cause: Optional underlying exception.
            debug_id: Optional correlation ID.
        """
        super().__init__(
            code=code,
            message_safe=message_safe,
            message_debug=message_debug,
            retryable=True,
            cause=cause,
            debug_id=debug_id,
        )


class TerminalError(ServiceError):
    """Error that indicates the operation should not be retried.

    Use this for permanent failures like:
    - Invalid input (400)
    - Authorization failures (401, 403)
    - Resource not found (404)
    - Business rule violations
    """

    def __init__(
        self,
        code: str,
        message_safe: str,
        message_debug: str | None = None,
        cause: Exception | None = None,
        debug_id: str | None = None,
    ):
        """Initialize a TerminalError.

        Args:
            code: Machine-readable error code.
            message_safe: Human-readable message safe for logs.
            message_debug: Optional detailed debug message.
            cause: Optional underlying exception.
            debug_id: Optional correlation ID.
        """
        super().__init__(
            code=code,
            message_safe=message_safe,
            message_debug=message_debug,
            retryable=False,
            cause=cause,
            debug_id=debug_id,
        )


# Common error codes
class ErrorCode:
    """Standard error codes for common failure scenarios."""

    # Network/connectivity
    TIMEOUT = "TIMEOUT"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

    # Storage
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    STORAGE_READ_ERROR = "STORAGE_READ_ERROR"
    STORAGE_WRITE_ERROR = "STORAGE_WRITE_ERROR"

    # Authentication/Authorization
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"

    # Validation
    INVALID_INPUT = "INVALID_INPUT"
    NOT_FOUND = "NOT_FOUND"

    # Rate limiting
    RATE_LIMITED = "RATE_LIMITED"

    # Internal
    INTERNAL_ERROR = "INTERNAL_ERROR"
