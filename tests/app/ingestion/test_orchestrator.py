"""
Unit tests for IngestionOrchestrator.

Tests the orchestrator's pointer-based processing flow:
1. Downloads from storage using raw_pointer
2. Routes to correct processor based on document_type
3. Uploads result artifact and returns pointers
"""

import pytest
from unittest.mock import MagicMock, patch

from app.ingestion.services.orchestrator import (
    IngestionOrchestrator,
    GeneralDocumentProcessor,
    HipaaRegulationProcessor
)


@pytest.fixture
def mock_storage_backend():
    """Mock the get_storage_backend factory function."""
    with patch("app.ingestion.services.orchestrator.get_storage_backend") as mock_factory:
        mock_storage = MagicMock()
        mock_storage.raw_bucket = "raw"
        mock_storage.processed_bucket = "processed"
        mock_factory.return_value = mock_storage
        yield mock_storage


@pytest.fixture
def mock_document_service():
    """Mock DocumentIngestionService."""
    with patch("app.ingestion.services.document_ingestion_service.DocumentIngestionService") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_regulation_service():
    """Mock HIPAARegulationService."""
    with patch("app.compliance.services.hipaa_regulation_service.HIPAARegulationService") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


class TestIngestionOrchestrator:
    """Tests for the IngestionOrchestrator pointer-based flow."""

    def test_process_general_document(self, mock_storage_backend):
        """Test processing a general document via pointer."""
        # Setup mocks
        mock_storage_backend.download.return_value = b"document content"
        mock_storage_backend.upload_json.return_value = "processed/results/job-123.json"

        with patch.object(GeneralDocumentProcessor, "process") as mock_process:
            mock_process.return_value = {
                "document_type": "general",
                "chunks_created": 5,
                "collection_name": "project_proj-1",
                "indexed_to_vector": True,
            }

            orchestrator = IngestionOrchestrator()

            result = orchestrator.process(
                job_id="job-123",
                raw_pointer="raw/tenant-1/proj-1/uuid_file.pdf",
                filename="file.pdf",
                tenant_id="tenant-1",
                project_id="proj-1",
                content_type="application/pdf",
                document_type="general",
            )

            # Verify download was called with pointer
            mock_storage_backend.download.assert_called_once_with(
                "raw/tenant-1/proj-1/uuid_file.pdf"
            )

            # Verify processor was called with downloaded content
            mock_process.assert_called_once()
            call_kwargs = mock_process.call_args[1]
            assert call_kwargs["content"] == b"document content"
            assert call_kwargs["filename"] == "file.pdf"
            assert call_kwargs["project_id"] == "proj-1"

            # Verify result
            assert result["status"] == "completed"
            assert result["chunks_created"] == 5
            assert result["raw_pointer"] == "raw/tenant-1/proj-1/uuid_file.pdf"
            assert "result_pointer" in result

    def test_process_regulation_document(self, mock_storage_backend):
        """Test processing a HIPAA regulation document."""
        mock_storage_backend.download.return_value = b"regulation text content"
        mock_storage_backend.upload_json.return_value = "processed/results/job-456.json"

        with patch.object(HipaaRegulationProcessor, "process") as mock_process:
            mock_process.return_value = {
                "document_type": "hipaa_regulation",
                "chunks_created": 10,
                "sections_found": ["s1", "s2"],
            }

            orchestrator = IngestionOrchestrator()

            result = orchestrator.process(
                job_id="job-456",
                raw_pointer="raw/tenant-1/proj-1/uuid_reg.pdf",
                filename="reg.pdf",
                tenant_id="tenant-1",
                project_id="proj-1",
                content_type="application/pdf",
                document_type="hipaa_regulation",
                source="HHS",
                title="Privacy Rule",
            )

            # Verify download
            mock_storage_backend.download.assert_called_once()

            # Verify processor received regulation metadata
            mock_process.assert_called_once()
            call_kwargs = mock_process.call_args[1]
            assert call_kwargs["source"] == "HHS"
            assert call_kwargs["title"] == "Privacy Rule"

            # Verify result
            assert result["status"] == "completed"
            assert result["chunks_created"] == 10

    def test_unsupported_document_type(self, mock_storage_backend):
        """Test that unsupported document types raise ValueError."""
        mock_storage_backend.download.return_value = b"content"

        orchestrator = IngestionOrchestrator()

        with pytest.raises(ValueError, match="Unsupported document_type"):
            orchestrator.process(
                job_id="job-bad",
                raw_pointer="raw/t/p/file.txt",
                filename="bad.txt",
                tenant_id="t",
                project_id="p",
                content_type="text/plain",
                document_type="unknown",
            )

    def test_result_artifact_uploaded(self, mock_storage_backend):
        """Test that result JSON artifact is uploaded to storage."""
        mock_storage_backend.download.return_value = b"content"
        mock_storage_backend.upload_json.return_value = "processed/results/job-789.json"

        with patch.object(GeneralDocumentProcessor, "process") as mock_process:
            mock_process.return_value = {
                "document_type": "general",
                "chunks_created": 3,
                "collection_name": "project_p1",
                "indexed_to_vector": True,
            }

            orchestrator = IngestionOrchestrator()

            result = orchestrator.process(
                job_id="job-789",
                raw_pointer="raw/t/p/doc.pdf",
                filename="doc.pdf",
                tenant_id="t",
                project_id="p",
                content_type="application/pdf",
                document_type="general",
            )

            # Verify upload_json was called for result artifact
            mock_storage_backend.upload_json.assert_called_once()
            call_kwargs = mock_storage_backend.upload_json.call_args[1]
            assert call_kwargs["filename"] == "job-789.json"
            assert call_kwargs["tenant_id"] == "t"
            assert call_kwargs["project_id"] == "p"
            assert call_kwargs["prefix"] == "results"

            # Verify result includes the pointer
            assert result["result_pointer"] == "processed/results/job-789.json"
