"""
Unit tests for Ingestion API endpoints.

These tests verify the ingestion API routes work correctly
with the underlying services via dependency injection.
"""

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestUploadDocuments:
    """Tests for POST /ingest/documents endpoint."""

    def test_upload_single_document_returns_job_id(self, test_client, mock_services):
        """Uploading a document should return a job ID for tracking."""
        # Create a mock file
        file_content = b"Hello, this is test content."
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}

        response = test_client.post(
            "/ingest/documents", files=files, data={"project_id": "test-project"}
        )

        assert response.status_code == 202  # Accepted
        assert "job_id" in response.json()

    def test_upload_document_requires_file(self, test_client):
        """Upload endpoint should require a file."""
        response = test_client.post("/ingest/documents", data={"project_id": "test-project"})

        assert response.status_code == 422  # Validation error

    def test_upload_document_requires_project_id(self, test_client):
        """Upload endpoint should require a project_id."""
        file_content = b"Test content"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}

        response = test_client.post("/ingest/documents", files=files)

        assert response.status_code == 422  # Validation error

    def test_upload_accepts_pdf_files(self, test_client, mock_services):
        """Upload should accept PDF files."""
        file_content = b"%PDF-1.4 fake pdf content"
        files = {"file": ("document.pdf", io.BytesIO(file_content), "application/pdf")}

        response = test_client.post(
            "/ingest/documents", files=files, data={"project_id": "test-project"}
        )

        assert response.status_code == 202


class TestDocumentStatus:
    """Tests for GET /ingest/documents/{job_id}/status endpoint."""

    def test_get_status_returns_job_info(self, test_client, mock_job_storage):
        """Getting status should return job information."""
        mock_job_storage.get_job.return_value = {
            "job_id": "test-job-123",
            "status": "processing",
            "progress": 50,
        }

        # Mock the JobLedgerService constructor to return our mock
        with patch("app.ingestion.services.job_ledger.JobLedgerService", return_value=mock_job_storage):
            response = test_client.get("/ingest/documents/test-job-123/status")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "test-job-123"
        assert "status" in data

    def test_get_status_returns_404_for_unknown_job(self, test_client, mock_job_storage):
        """Getting status for unknown job should return 404."""
        mock_job_storage.get_job.return_value = None

        with patch("app.ingestion.services.job_ledger.JobLedgerService", return_value=mock_job_storage):
            response = test_client.get("/ingest/documents/unknown-job/status")

        assert response.status_code == 404


class TestProcessingOptions:
    """Tests for processing options on upload."""

    def test_upload_with_index_to_vector_option(self, test_client, mock_services):
        """Upload should accept index_to_vector option."""
        file_content = b"Test content"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}

        response = test_client.post(
            "/ingest/documents",
            files=files,
            data={"project_id": "test-project", "index_to_vector": "true"},
        )

        assert response.status_code == 202

    def test_upload_with_index_to_graph_option(self, test_client, mock_services):
        """Upload should accept index_to_graph option."""
        file_content = b"Test content"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}

        response = test_client.post(
            "/ingest/documents",
            files=files,
            data={"project_id": "test-project", "index_to_graph": "true"},
        )

        assert response.status_code == 202


# --- Fixtures ---


@pytest.fixture
def test_client():
    """Provides a TestClient for the unified app."""
    from app.main import app

    return TestClient(app)


@pytest.fixture
def mock_services():
    """Mock services to avoid external dependencies (Celery, storage, DB)."""
    mock_storage = MagicMock()
    mock_storage.raw_bucket = "raw"
    mock_storage.upload.return_value = "raw/mock/path"

    mock_ledger = MagicMock()
    mock_ledger.compute_content_hash.return_value = "hash"
    mock_ledger.build_idempotency_key.return_value = "idem"
    mock_ledger.check_idempotency.return_value = None
    mock_ledger.create_job.return_value = "job-1"
    mock_ledger.register_artifact.return_value = "artifact-1"

    with (
        patch("app.ingestion.routes.documents.process_document") as mock_task,
        patch("app.ingestion.routes.documents.get_storage_service", return_value=mock_storage),
        patch("app.ingestion.routes.documents.JobLedgerService", return_value=mock_ledger),
    ):
        mock_task.delay.return_value = MagicMock(id="mock-task-id")
        yield {"task": mock_task, "storage": mock_storage, "ledger": mock_ledger}


@pytest.fixture
def mock_job_storage():
    """Provides a mock job storage."""
    return MagicMock()
