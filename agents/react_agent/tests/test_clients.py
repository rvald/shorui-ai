
import pytest
from unittest.mock import Mock, patch, AsyncMock, mock_open
from agents.react_agent.infrastructure.clients.ingestion import IngestionClient, AsyncIngestionClient
from agents.react_agent.infrastructure.clients.compliance import ComplianceClient, AsyncComplianceClient
from agents.react_agent.infrastructure.clients.rag import RAGClient, AsyncRAGClient

# Ingestion Client Tests

def test_ingestion_client_upload_document():
    with patch("httpx.Client") as mock_client_cls:
        mock_instance = mock_client_cls.return_value.__enter__.return_value
        mock_response = Mock()
        mock_response.json.return_value = {"job_id": "123", "message": "Uploaded"}
        mock_response.raise_for_status.return_value = None
        mock_instance.post.return_value = mock_response

        client = IngestionClient(base_url="http://test")
        # Create a dummy file for the test
        with patch("builtins.open", mock_open(read_data=b"data")) as m_open:
             result = client.upload_document("doc.txt", "proj1")
        
        assert result["job_id"] == "123"
        # Verify correct ingestion endpoint
        mock_instance.post.assert_called_with(
            "http://test/documents",
            files={'file': ('doc.txt', m_open.return_value)},
            data={'project_id': 'proj1', 'document_type': 'general'}
        )

# Compliance Client Tests

def test_compliance_client_transcript_status():
    with patch("httpx.Client") as mock_client_cls:
        mock_instance = mock_client_cls.return_value.__enter__.return_value
        mock_response = Mock()
        mock_response.json.return_value = {"status": "completed"}
        mock_response.raise_for_status.return_value = None
        mock_instance.get.return_value = mock_response

        client = ComplianceClient(base_url="http://test")
        client.get_transcript_job_status("job123")
        
        # Verify correct compliance endpoint (singular job)
        mock_instance.get.assert_called_with("http://test/clinical-transcripts/job/job123")

@pytest.mark.asyncio
async def test_async_compliance_check_status():
    with patch("httpx.AsyncClient", new_callable=Mock) as mock_client_cls:
        mock_instance = mock_client_cls.return_value
        
        mock_response = Mock()
        mock_response.json.return_value = {"status": "completed"}
        mock_response.raise_for_status.return_value = None
        mock_instance.get = AsyncMock(return_value=mock_response)

        client = AsyncComplianceClient(base_url="http://test")
        result = await client.get_transcript_job_status("job123")
        
        assert result["status"] == "completed"
        # Verify correct compliance endpoint (singular job)
        mock_instance.get.assert_awaited_with("http://test/clinical-transcripts/job/job123")

# RAG Client Tests

def test_rag_client_query():
    with patch("httpx.Client") as mock_client_cls:
        mock_instance = mock_client_cls.return_value.__enter__.return_value
        mock_response = Mock()
        mock_response.json.return_value = {"answer": "The answer is 42", "sources": []}
        mock_response.raise_for_status.return_value = None
        mock_instance.post.return_value = mock_response

        client = RAGClient(base_url="http://test")
        result = client.query("question", "proj1")
        
        assert result["answer"] == "The answer is 42"
        mock_instance.post.assert_called_once()
