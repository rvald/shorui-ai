"""Unit tests for ServiceHttpClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from shorui_core.runtime.context import RunContext
from shorui_core.runtime.errors import (
    ErrorCode,
    RetryableError,
    ServiceError,
    TerminalError,
)
from shorui_core.runtime.http_client import ServiceHttpClient
from shorui_core.runtime.retry import RetryPolicy


@pytest.fixture
def context():
    """Create a test RunContext."""
    return RunContext(
        request_id="test-req-123",
        tenant_id="test-tenant",
        project_id="test-project",
    )


@pytest.fixture
def client():
    """Create a test ServiceHttpClient."""
    return ServiceHttpClient(
        base_url="http://test-service:8080",
        timeout=5.0,
        retry_policy=RetryPolicy(max_attempts=2, base_delay=0.01),
    )


class TestServiceHttpClientInit:
    """Tests for client initialization."""

    def test_strips_trailing_slash(self):
        """Should strip trailing slash from base_url."""
        client = ServiceHttpClient(base_url="http://example.com/")
        assert client.base_url == "http://example.com"

    def test_stores_configuration(self):
        """Should store timeout and retry policy."""
        policy = RetryPolicy(max_attempts=5)
        client = ServiceHttpClient(
            base_url="http://test.com",
            timeout=10.0,
            retry_policy=policy,
        )

        assert client.timeout == 10.0
        assert client.retry_policy == policy


class TestBuildUrl:
    """Tests for URL building."""

    def test_builds_url_with_leading_slash(self):
        """Should handle path with leading slash."""
        client = ServiceHttpClient(base_url="http://test.com")
        url = client._build_url("/api/endpoint")
        assert url == "http://test.com/api/endpoint"

    def test_builds_url_without_leading_slash(self):
        """Should handle path without leading slash."""
        client = ServiceHttpClient(base_url="http://test.com")
        url = client._build_url("api/endpoint")
        assert url == "http://test.com/api/endpoint"


class TestHeaderInjection:
    """Tests for automatic header injection."""

    @pytest.mark.asyncio
    async def test_injects_correlation_headers(self, client, context):
        """Should inject X-Request-Id, X-Tenant-Id, X-Project-Id headers."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            await client.get("/test", context)

            # Verify headers were passed
            call_kwargs = mock_http_client.request.call_args.kwargs
            headers = call_kwargs["headers"]

            assert headers["X-Request-Id"] == "test-req-123"
            assert headers["X-Tenant-Id"] == "test-tenant"
            assert headers["X-Project-Id"] == "test-project"

    @pytest.mark.asyncio
    async def test_merges_custom_headers(self, client, context):
        """Should merge custom headers with correlation headers."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            await client.get("/test", context, headers={"Custom-Header": "value"})

            call_kwargs = mock_http_client.request.call_args.kwargs
            headers = call_kwargs["headers"]

            assert headers["X-Request-Id"] == "test-req-123"
            assert headers["Custom-Header"] == "value"


class TestErrorHandling:
    """Tests for error response handling."""

    @pytest.mark.asyncio
    async def test_raises_terminal_error_on_401(self, client, context):
        """Should raise TerminalError for 401 Unauthorized."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            with pytest.raises(TerminalError) as exc_info:
                await client.get("/protected", context)

            assert exc_info.value.code == ErrorCode.UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_raises_terminal_error_on_403(self, client, context):
        """Should raise TerminalError for 403 Forbidden."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 403

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            with pytest.raises(TerminalError) as exc_info:
                await client.get("/forbidden", context)

            assert exc_info.value.code == ErrorCode.FORBIDDEN

    @pytest.mark.asyncio
    async def test_raises_terminal_error_on_404(self, client, context):
        """Should raise TerminalError for 404 Not Found."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            with pytest.raises(TerminalError) as exc_info:
                await client.get("/missing", context)

            assert exc_info.value.code == ErrorCode.NOT_FOUND

    @pytest.mark.asyncio
    async def test_raises_retryable_error_on_500(self, client, context):
        """Should raise RetryableError for 500 after retries exhausted."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            with pytest.raises(RetryableError) as exc_info:
                await client.get("/error", context)

            assert exc_info.value.code == ErrorCode.SERVICE_UNAVAILABLE


class TestRetryBehavior:
    """Tests for retry on transient failures."""

    @pytest.mark.asyncio
    async def test_retries_on_503(self, client, context):
        """Should retry on 503 Service Unavailable."""
        # First call returns 503, second returns 200
        mock_503 = MagicMock(spec=httpx.Response)
        mock_503.status_code = 503

        mock_200 = MagicMock(spec=httpx.Response)
        mock_200.status_code = 200

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(side_effect=[mock_503, mock_200])
            mock_get_client.return_value = mock_http_client

            response = await client.get("/flaky", context)

            assert response.status_code == 200
            assert mock_http_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_timeout(self, client, context):
        """Should retry on timeout."""
        mock_200 = MagicMock(spec=httpx.Response)
        mock_200.status_code = 200

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(
                side_effect=[httpx.TimeoutException("timeout"), mock_200]
            )
            mock_get_client.return_value = mock_http_client

            response = await client.get("/slow", context)

            assert response.status_code == 200
            assert mock_http_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self, client, context):
        """Should retry on connection error."""
        mock_200 = MagicMock(spec=httpx.Response)
        mock_200.status_code = 200

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(
                side_effect=[httpx.ConnectError("connection refused"), mock_200]
            )
            mock_get_client.return_value = mock_http_client

            response = await client.get("/unavailable", context)

            assert response.status_code == 200
            assert mock_http_client.request.call_count == 2


class TestConvenienceMethods:
    """Tests for HTTP method shortcuts."""

    @pytest.mark.asyncio
    async def test_post_method(self, client, context):
        """Should make POST request."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            response = await client.post("/create", context, json={"key": "value"})

            assert response.status_code == 201
            call_args = mock_http_client.request.call_args
            assert call_args.kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_put_method(self, client, context):
        """Should make PUT request."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            response = await client.put("/update", context, json={"key": "value"})

            assert response.status_code == 200
            call_args = mock_http_client.request.call_args
            assert call_args.kwargs["method"] == "PUT"

    @pytest.mark.asyncio
    async def test_delete_method(self, client, context):
        """Should make DELETE request."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 204

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            response = await client.delete("/remove", context)

            assert response.status_code == 204
            call_args = mock_http_client.request.call_args
            assert call_args.kwargs["method"] == "DELETE"


class TestContextManager:
    """Tests for async context manager usage."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Should work as async context manager."""
        async with ServiceHttpClient(base_url="http://test.com") as client:
            assert client._client is not None

        # Client should be closed after exiting
        assert client._client is None
