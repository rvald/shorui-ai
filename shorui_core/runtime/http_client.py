"""
Shared async HTTP client for service-to-service communication.

This module provides a pooled HTTP client that automatically injects
correlation headers and handles retries for transient failures.
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from .context import RunContext
from .errors import ErrorCode, RetryableError, ServiceError, TerminalError
from .retry import RetryPolicy


class ServiceHttpClient:
    """Shared HTTP client for service-to-service communication.

    Features:
    - Connection pooling via httpx.AsyncClient
    - Automatic header injection (X-Request-Id, X-Tenant-Id, X-Project-Id)
    - Retry on transient failures (429, 502, 503, 504)
    - Timeout handling
    - Structured error conversion

    Example:
        client = ServiceHttpClient("http://rag-service:8082")
        async with client:
            response = await client.get("/rag/search", context, params={"q": "test"})
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        retry_policy: RetryPolicy | None = None,
        max_connections: int = 100,
        max_keepalive: int = 20,
    ):
        """Initialize the HTTP client.

        Args:
            base_url: Base URL for all requests.
            timeout: Default timeout in seconds.
            retry_policy: Retry configuration. Uses default if None.
            max_connections: Maximum total connections in pool.
            max_keepalive: Maximum keepalive connections.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_policy = retry_policy or RetryPolicy()

        self._limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive,
            keepalive_expiry=30.0,
        )
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client.

        Returns:
            The shared httpx.AsyncClient instance.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=self._limits,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client and release connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "ServiceHttpClient":
        """Enter async context manager."""
        await self._get_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager."""
        await self.close()

    def _build_url(self, path: str) -> str:
        """Build full URL from path.

        Args:
            path: Request path (with or without leading slash).

        Returns:
            Full URL including base_url.
        """
        path = path.lstrip("/")
        return f"{self.base_url}/{path}"

    async def request(
        self,
        method: str,
        path: str,
        context: RunContext,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with automatic header injection and retry.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: Request path.
            context: RunContext for header injection and correlation.
            **kwargs: Additional arguments passed to httpx.

        Returns:
            The HTTP response.

        Raises:
            RetryableError: For transient failures after max retries.
            TerminalError: For permanent failures (4xx, etc.).
            ServiceError: For other errors.
        """
        client = await self._get_client()
        url = self._build_url(path)

        # Inject correlation headers
        headers = kwargs.pop("headers", {})
        headers.update(context.get_headers())

        last_exception: Exception | None = None

        for attempt in range(self.retry_policy.max_attempts):
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    **kwargs,
                )

                # Check for retryable status codes
                if self.retry_policy.should_retry_status(response.status_code):
                    if attempt + 1 < self.retry_policy.max_attempts:
                        delay = self.retry_policy.calculate_delay(attempt)
                        logger.info(
                            f"[{context.request_id}] Retry {attempt + 1}/{self.retry_policy.max_attempts} "
                            f"for {method} {path} (status={response.status_code}) in {delay:.2f}s"
                        )
                        import asyncio

                        await asyncio.sleep(delay)
                        continue

                # Check for errors
                if response.status_code >= 500:
                    raise RetryableError(
                        code=ErrorCode.SERVICE_UNAVAILABLE,
                        message_safe=f"Service returned {response.status_code}",
                        message_debug=response.text[:500] if response.text else None,
                    )

                if response.status_code == 401:
                    raise TerminalError(
                        code=ErrorCode.UNAUTHORIZED,
                        message_safe="Unauthorized",
                    )

                if response.status_code == 403:
                    raise TerminalError(
                        code=ErrorCode.FORBIDDEN,
                        message_safe="Forbidden",
                    )

                if response.status_code == 404:
                    raise TerminalError(
                        code=ErrorCode.NOT_FOUND,
                        message_safe="Resource not found",
                    )

                if response.status_code >= 400:
                    raise TerminalError(
                        code=ErrorCode.INVALID_INPUT,
                        message_safe=f"Request failed with status {response.status_code}",
                        message_debug=response.text[:500] if response.text else None,
                    )

                return response

            except httpx.TimeoutException as e:
                last_exception = e
                if attempt + 1 >= self.retry_policy.max_attempts:
                    raise RetryableError(
                        code=ErrorCode.TIMEOUT,
                        message_safe=f"Request timed out after {self.timeout}s",
                        cause=e,
                    )

                delay = self.retry_policy.calculate_delay(attempt)
                logger.info(
                    f"[{context.request_id}] Timeout, retry {attempt + 1}/{self.retry_policy.max_attempts} "
                    f"for {method} {path} in {delay:.2f}s"
                )
                import asyncio

                await asyncio.sleep(delay)

            except httpx.ConnectError as e:
                last_exception = e
                if attempt + 1 >= self.retry_policy.max_attempts:
                    raise RetryableError(
                        code=ErrorCode.CONNECTION_ERROR,
                        message_safe="Failed to connect to service",
                        cause=e,
                    )

                delay = self.retry_policy.calculate_delay(attempt)
                logger.info(
                    f"[{context.request_id}] Connection error, retry {attempt + 1}/{self.retry_policy.max_attempts} "
                    f"for {method} {path} in {delay:.2f}s"
                )
                import asyncio

                await asyncio.sleep(delay)

            except ServiceError:
                # Re-raise our own errors
                raise

            except Exception as e:
                logger.error(f"[{context.request_id}] Unexpected error: {e}")
                raise ServiceError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message_safe="Unexpected error during request",
                    message_debug=str(e),
                    cause=e,
                )

        # Should not reach here
        if last_exception:
            raise RetryableError(
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message_safe="Max retries exceeded",
                cause=last_exception,
            )
        raise RuntimeError("Retry loop exited unexpectedly")

    async def get(
        self,
        path: str,
        context: RunContext,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a GET request.

        Args:
            path: Request path.
            context: RunContext for correlation.
            **kwargs: Additional arguments (params, headers, etc.).

        Returns:
            The HTTP response.
        """
        return await self.request("GET", path, context, **kwargs)

    async def post(
        self,
        path: str,
        context: RunContext,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a POST request.

        Args:
            path: Request path.
            context: RunContext for correlation.
            **kwargs: Additional arguments (json, data, headers, etc.).

        Returns:
            The HTTP response.
        """
        return await self.request("POST", path, context, **kwargs)

    async def put(
        self,
        path: str,
        context: RunContext,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a PUT request.

        Args:
            path: Request path.
            context: RunContext for correlation.
            **kwargs: Additional arguments.

        Returns:
            The HTTP response.
        """
        return await self.request("PUT", path, context, **kwargs)

    async def delete(
        self,
        path: str,
        context: RunContext,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a DELETE request.

        Args:
            path: Request path.
            context: RunContext for correlation.
            **kwargs: Additional arguments.

        Returns:
            The HTTP response.
        """
        return await self.request("DELETE", path, context, **kwargs)
