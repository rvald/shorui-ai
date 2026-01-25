"""Unit tests for agent HTTP clients."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.react_agent.infrastructure.clients import (
    ComplianceClient,
    IngestionClient,
    RAGClient,
)
from shorui_core.runtime import RunContext


@pytest.fixture
def context():
    """Create a test RunContext."""
    return RunContext(
        request_id="test-req-123",
        tenant_id="test-tenant",
        project_id="test-project",
    )


class TestRAGClient:
    """Tests for RAGClient."""

    @pytest.mark.asyncio
    async def test_query_calls_http_post(self, context):
        """Should call HTTP POST with correct parameters."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"answer": "The answer is 42", "sources": []}

        with patch.object(RAGClient, "__init__", lambda x, **k: None):
            client = RAGClient()
            client._http = MagicMock()
            client._http.post = AsyncMock(return_value=mock_response)
            client._http.base_url = "http://test"

            result = await client.query("question", "proj1", context=context)

            assert result["answer"] == "The answer is 42"
            client._http.post.assert_called_once()
            call_args = client._http.post.call_args
            assert call_args[0][0] == "/query"
            assert call_args[0][1] == context

    @pytest.mark.asyncio
    async def test_search_calls_http_get(self, context):
        """Should call HTTP GET with correct parameters."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}

        with patch.object(RAGClient, "__init__", lambda x, **k: None):
            client = RAGClient()
            client._http = MagicMock()
            client._http.get = AsyncMock(return_value=mock_response)

            result = await client.search("test query", "proj1", context=context)

            assert result == {"results": []}
            client._http.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_default_context_when_none_provided(self):
        """Should create default context when none is provided."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}

        with patch.object(RAGClient, "__init__", lambda x, **k: None):
            client = RAGClient()
            client._http = MagicMock()
            client._http.get = AsyncMock(return_value=mock_response)

            await client.search("query", "proj1")  # No context

            # Verify a context was passed (default)
            call_args = client._http.get.call_args
            passed_context = call_args[0][1]
            assert passed_context.tenant_id == "default"


class TestComplianceClient:
    """Tests for ComplianceClient."""

    @pytest.mark.asyncio
    async def test_get_transcript_job_status(self, context):
        """Should call correct endpoint."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "completed"}

        with patch.object(ComplianceClient, "__init__", lambda x, **k: None):
            client = ComplianceClient()
            client._http = MagicMock()
            client._http.get = AsyncMock(return_value=mock_response)
            client._http.base_url = "http://test"

            result = await client.get_transcript_job_status("job123", context=context)

            assert result["status"] == "completed"
            client._http.get.assert_called_once()
            call_args = client._http.get.call_args
            assert "/clinical-transcripts/job/job123" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_query_audit_log(self, context):
        """Should query audit log with params."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"events": []}

        with patch.object(ComplianceClient, "__init__", lambda x, **k: None):
            client = ComplianceClient()
            client._http = MagicMock()
            client._http.get = AsyncMock(return_value=mock_response)

            result = await client.query_audit_log(
                event_type="PHI_DETECTED", limit=50, context=context
            )

            assert result == {"events": []}
            call_kwargs = client._http.get.call_args.kwargs
            assert call_kwargs["params"]["event_type"] == "PHI_DETECTED"
            assert call_kwargs["params"]["limit"] == 50


class TestIngestionClient:
    """Tests for IngestionClient."""

    @pytest.mark.asyncio
    async def test_check_status(self, context):
        """Should call correct status endpoint."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "completed", "progress": 100}

        with patch.object(IngestionClient, "__init__", lambda x, **k: None):
            client = IngestionClient()
            client._http = MagicMock()
            client._http.get = AsyncMock(return_value=mock_response)

            result = await client.check_status("job123", context=context)

            assert result["status"] == "completed"
            call_args = client._http.get.call_args
            assert "/documents/job123/status" in call_args[0][0]


class TestContextPropagation:
    """Tests for context propagation across clients."""

    @pytest.mark.asyncio
    async def test_context_passed_to_http_client(self, context):
        """Context should be passed to underlying HTTP client."""
        mock_response = MagicMock()
        mock_response.json.return_value = {}

        with patch.object(RAGClient, "__init__", lambda x, **k: None):
            client = RAGClient()
            client._http = MagicMock()
            client._http.get = AsyncMock(return_value=mock_response)

            await client.search("query", "proj", context=context)

            # Verify the exact context was passed
            passed_context = client._http.get.call_args[0][1]
            assert passed_context.request_id == "test-req-123"
            assert passed_context.tenant_id == "test-tenant"
