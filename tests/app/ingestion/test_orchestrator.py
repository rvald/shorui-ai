import pytest
from unittest.mock import MagicMock, patch

from app.ingestion.services.orchestrator import (
    IngestionOrchestrator,
    GeneralDocumentProcessor,
    HipaaRegulationProcessor
)

@pytest.fixture
def mock_storage_service():
    with patch("app.ingestion.services.orchestrator.StorageService") as mock:
        yield mock.return_value

@pytest.fixture
def mock_document_service():
    with patch("app.ingestion.services.orchestrator.DocumentIngestionService") as mock:
        yield mock.return_value

@pytest.fixture
def mock_regulation_service():
    # Note: This mock needs to target where the class is imported, 
    # but since it's a lazy import inside the method, we patch the module path directly.
    with patch("app.compliance.services.hipaa_regulation_service.HIPAARegulationService") as mock:
        yield mock.return_value

class TestIngestionOrchestrator:
    def test_process_general_document(self, mock_storage_service, mock_document_service):
        orchestrator = IngestionOrchestrator()
        # Ensure the processors map uses instances that will acquire the new mocks when called?
        # Actually, GeneralDocumentProcessor instantiates DocumentIngestionService inside process().
        # So patching the class used in orchestrator.py (or where it's imported) is correct.
        
        # mock_storage_service is instantiated in __init__
        mock_storage_service.upload.return_value = "s3://bucket/file.pdf"
        
        mock_document_service.ingest_document.return_value = {
            "chunks_created": 5,
            "collection_name": "test_docs",
        }
        
        result = orchestrator.process(
            job_id="job-123",
            file_content=b"content",
            filename="file.pdf",
            project_id="proj-1",
            document_type="general",
            content_type="application/pdf"
        )
        
        # Verify Storage Upload
        mock_storage_service.upload.assert_called_once_with(b"content", "file.pdf", "proj-1")
        
        # Verify General Processor Logic
        mock_document_service.ingest_document.assert_called_once_with(
            content=b"content",
            filename="file.pdf",
            content_type="application/pdf",
            project_id="proj-1"
        )
        
        assert result["status"] == "completed"
        assert result["chunks_created"] == 5
        assert result["indexed_to_vector"] is True

    def test_process_regulation_document(self, mock_storage_service, mock_regulation_service):
        orchestrator = IngestionOrchestrator()
        
        mock_storage_service.upload.return_value = "s3://bucket/reg.pdf"
        mock_regulation_service.ingest_regulation.return_value = {
            "chunks_created": 10,
            "sections_found": ["s1"]
        }
        
        # Patch extract_text_content
        with patch("app.ingestion.services.orchestrator._extract_text_content") as mock_extract:
            mock_extract.return_value = "extracted text"
            
            result = orchestrator.process(
                job_id="job-456",
                file_content=b"reg content",
                filename="reg.pdf",
                project_id="proj-1",
                document_type="hipaa_regulation",
                source="HHS",
                title="Privacy Rule"
            )
            
            mock_extract.assert_called_once_with(b"reg content")
            
            # Verify Regulation Processor Logic
            mock_regulation_service.ingest_regulation.assert_called_once_with(
                text="extracted text",
                source="HHS",
                title="Privacy Rule",
                category="privacy_rule"
            )
            
            assert result["status"] == "completed"
            assert result["chunks_created"] == 10
            assert result["document_type"] == "hipaa_regulation"

    def test_unsupported_document_type(self, mock_storage_service):
        orchestrator = IngestionOrchestrator()
        
        with pytest.raises(ValueError, match="Unsupported document_type"):
            orchestrator.process(
                job_id="job-bad",
                file_content=b"",
                filename="bad.txt",
                project_id="p1",
                document_type="unknown"
            )
