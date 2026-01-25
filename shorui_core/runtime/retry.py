"""
Retry policy configuration and decorator.

This module provides configurable retry behavior with exponential backoff
and jitter for resilient service operations.
"""

from __future__ import annotations

import asyncio
import functools
import random
from typing import Any, Callable, TypeVar

from loguru import logger
from pydantic import BaseModel

from .errors import RetryableError, ServiceError

T = TypeVar("T")


class RetryPolicy(BaseModel):
    """Configuration for retry behavior.

    Implements exponential backoff with optional jitter. The delay for
    attempt N is: min(base_delay * (exponential_base ** N) + jitter, max_delay)

    Attributes:
        max_attempts: Maximum number of attempts (including initial).
        base_delay: Initial delay in seconds between retries.
        max_delay: Maximum delay in seconds (caps backoff).
        exponential_base: Base for exponential backoff calculation.
        jitter: Whether to add random jitter to delays.
        retry_on_status: HTTP status codes that trigger retry.
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on_status: tuple[int, ...] = (429, 502, 503, 504)

    model_config = {"frozen": True}

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number.

        Args:
            attempt: The attempt number (0-indexed).

        Returns:
            Delay in seconds before the next retry.
        """
        delay = self.base_delay * (self.exponential_base**attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            # Add up to 25% jitter
            jitter_amount = delay * 0.25 * random.random()
            delay += jitter_amount

        return delay

    def should_retry_status(self, status_code: int) -> bool:
        """Check if a status code should trigger a retry.

        Args:
            status_code: HTTP status code to check.

        Returns:
            True if the status code is in retry_on_status.
        """
        return status_code in self.retry_on_status


# Default policy for general use
DEFAULT_RETRY_POLICY = RetryPolicy()


def with_retry(
    policy: RetryPolicy | None = None,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for retrying async functions.

    Retries the decorated function according to the provided policy when
    a RetryableError is raised.

    Args:
        policy: Retry policy to use. Defaults to DEFAULT_RETRY_POLICY.
        on_retry: Optional callback called before each retry with
                  (attempt, exception, delay).

    Returns:
        Decorated function with retry behavior.

    Example:
        @with_retry(RetryPolicy(max_attempts=5))
        async def fetch_data(url: str) -> dict:
            ...
    """
    retry_policy = policy or DEFAULT_RETRY_POLICY

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None

            for attempt in range(retry_policy.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except RetryableError as e:
                    last_exception = e
                    if attempt + 1 >= retry_policy.max_attempts:
                        logger.warning(
                            f"[{e.debug_id}] Max retries ({retry_policy.max_attempts}) "
                            f"exceeded for {func.__name__}: {e.message_safe}"
                        )
                        raise

                    delay = retry_policy.calculate_delay(attempt)
                    logger.info(
                        f"[{e.debug_id}] Retry {attempt + 1}/{retry_policy.max_attempts} "
                        f"for {func.__name__} in {delay:.2f}s: {e.message_safe}"
                    )

                    if on_retry:
                        on_retry(attempt, e, delay)

                    await asyncio.sleep(delay)
                except ServiceError:
                    # Non-retryable ServiceError, re-raise immediately
                    raise
                except Exception as e:
                    # Unexpected exception, wrap and re-raise
                    logger.error(f"Unexpected error in {func.__name__}: {e}")
                    raise

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError(f"Retry loop exited unexpectedly in {func.__name__}")

        return wrapper  # type: ignore

    return decorator


def sync_with_retry(
    policy: RetryPolicy | None = None,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for retrying synchronous functions.

    Similar to with_retry but for sync functions. Uses time.sleep.

    Args:
        policy: Retry policy to use. Defaults to DEFAULT_RETRY_POLICY.
        on_retry: Optional callback called before each retry.

    Returns:
        Decorated function with retry behavior.
    """
    import time

    retry_policy = policy or DEFAULT_RETRY_POLICY

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None

            for attempt in range(retry_policy.max_attempts):
                try:
                    return func(*args, **kwargs)
                except RetryableError as e:
                    last_exception = e
                    if attempt + 1 >= retry_policy.max_attempts:
                        logger.warning(
                            f"[{e.debug_id}] Max retries ({retry_policy.max_attempts}) "
                            f"exceeded for {func.__name__}: {e.message_safe}"
                        )
                        raise

                    delay = retry_policy.calculate_delay(attempt)
                    logger.info(
                        f"[{e.debug_id}] Retry {attempt + 1}/{retry_policy.max_attempts} "
                        f"for {func.__name__} in {delay:.2f}s: {e.message_safe}"
                    )

                    if on_retry:
                        on_retry(attempt, e, delay)

                    time.sleep(delay)
                except ServiceError:
                    raise
                except Exception as e:
                    logger.error(f"Unexpected error in {func.__name__}: {e}")
                    raise

            if last_exception:
                raise last_exception
            raise RuntimeError(f"Retry loop exited unexpectedly in {func.__name__}")

        return wrapper  # type: ignore

    return decorator
