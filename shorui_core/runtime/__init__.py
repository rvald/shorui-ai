"""
Service runtime layer for shorui-ai.

This package provides shared infrastructure for reliability and observability:
- RunContext: Request-scoped context with correlation IDs
- ServiceError: Standardized errors with retry semantics
- ServiceHttpClient: Pooled async HTTP client with automatic headers
- RetryPolicy: Configurable retry behavior
"""

from .context import RunContext
from .errors import ServiceError, RetryableError, TerminalError
from .http_client import ServiceHttpClient
from .retry import RetryPolicy, with_retry

__all__ = [
    "RunContext",
    "ServiceError",
    "RetryableError",
    "TerminalError",
    "ServiceHttpClient",
    "RetryPolicy",
    "with_retry",
]
