"""
Unit tests for MinIO document storage service.

The storage service should:
1. Use the MinIO singleton from shorui_core.infrastructure
2. Upload documents to MinIO before processing
3. Store the MinIO path in job metadata
4. Support retrieval of documents for re-processing
"""

from unittest.mock import MagicMock, patch

import pytest


class TestStorageServiceUpload:
    """Tests for document upload to MinIO."""

    def test_upload_returns_storage_path(self, mock_minio_connector):
        """Uploading a document should return a storage path."""
        from app.ingestion.services.storage import StorageService

        service = StorageService()

        content = b"Test document content"
        path = service.upload(
            content=content,
            filename="test.pdf",
            tenant_id="test-tenant",
            project_id="test-project",
        )

        # Should return a path like "raw/tenant/project/uuid_test.pdf"
        assert path is not None
        assert "test-project" in path
        assert "test.pdf" in path

    def test_upload_calls_minio_put_object(self, mock_minio_connector):
        """Upload should call MinIO put_object."""
        from app.ingestion.services.storage import StorageService

        service = StorageService()
        mock_client = mock_minio_connector

        content = b"Test content"
        service.upload(
            content=content,
            filename="doc.pdf",
            tenant_id="tenant-1",
            project_id="proj-1",
        )

        # Verify put_object was called
        mock_client.put_object.assert_called_once()

    def test_upload_uses_raw_bucket(self, mock_minio_connector):
        """Upload should use the raw bucket."""
        from app.ingestion.services.storage import StorageService

        service = StorageService()
        mock_client = mock_minio_connector

        content = b"Content"
        service.upload(
            content=content,
            filename="file.pdf",
            tenant_id="tenant-1",
            project_id="project-1",
        )

        # First argument should be the bucket name
        call_args = mock_client.put_object.call_args
        assert call_args[1]["bucket_name"] == "raw"


class TestStorageServiceDownload:
    """Tests for document download from MinIO."""

    def test_download_returns_content(self, mock_minio_connector):
        """Downloading should return the file content."""
        from app.ingestion.services.storage import StorageService

        mock_client = mock_minio_connector

        # Setup mock to return content
        mock_response = MagicMock()
        mock_response.read.return_value = b"Original document content"
        mock_response.close = MagicMock()
        mock_response.release_conn = MagicMock()
        mock_client.get_object.return_value = mock_response

        service = StorageService()

        content = service.download("raw/project-1/uuid_doc.pdf")

        assert content == b"Original document content"


class TestStorageServiceConfiguration:
    """Tests for storage service configuration."""

    def test_default_buckets_configured(self, mock_minio_connector):
        """Service should have default bucket names."""
        from app.ingestion.services.storage import StorageService

        service = StorageService()

        assert service.raw_bucket == "raw"
        assert service.processed_bucket == "processed"

    def test_ensures_bucket_exists(self, mock_minio_connector):
        """Service should ensure buckets exist on init."""
        from app.ingestion.services.storage import StorageService

        mock_client = mock_minio_connector
        mock_client.bucket_exists.return_value = False

        StorageService()

        # Should have called make_bucket for buckets that don't exist
        assert mock_client.make_bucket.call_count >= 1


# --- Fixtures ---


@pytest.fixture
def mock_minio_connector():
    """Provides a mock MinIO client via the connector."""
    with patch("app.ingestion.services.storage.get_minio_client") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client

        # Default behaviors
        mock_client.bucket_exists.return_value = True
        mock_client.put_object.return_value = None

        yield mock_client
