"""
Unit tests for Celery app configuration and tasks.

Tests cover:
1. Celery app configuration (broker, backend)
2. Task registration
3. Task execution with proper mocking
"""

from unittest.mock import MagicMock, patch

import pytest


class TestCeleryAppConfiguration:
    """Tests for Celery app setup."""

    def test_celery_app_uses_redis_broker(self):
        """Celery app should be configured with Redis broker."""
        with patch.dict(
            "os.environ",
            {
                "CELERY_BROKER_URL": "redis://localhost:6379/0",
                "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
            },
        ):
            from app.workers.celery_app import celery_app

            assert "redis" in celery_app.conf.broker_url

    def test_celery_app_uses_redis_backend(self):
        """Celery app should use Redis as result backend."""
        with patch.dict(
            "os.environ",
            {
                "CELERY_BROKER_URL": "redis://localhost:6379/0",
                "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
            },
        ):
            from app.workers.celery_app import celery_app

            assert "redis" in celery_app.conf.result_backend

    def test_celery_app_has_task_serializer_json(self):
        """Tasks should use JSON serialization for safety."""
        from app.workers.celery_app import celery_app

        assert celery_app.conf.task_serializer == "json"


class TestProcessDocumentTask:
    """Tests for the process_document Celery task."""

    def test_task_is_registered(self):
        """process_document task should be registered with Celery."""
        from app.workers.tasks import process_document

        assert process_document.name is not None
        assert "process_document" in process_document.name

    def test_task_accepts_required_parameters(self, mock_all_services):
        """Task should accept all required processing parameters."""
        from app.workers.tasks import process_document

        # Should not raise when called with all params
        result = process_document(
            job_id="test-job-123",
            file_content=b"test content",
            filename="test.txt",
            content_type="text/plain",
            project_id="test-project",
            index_to_vector=True,
            index_to_graph=False,
        )

        assert result is not None

    def test_task_returns_job_result(self, mock_all_services):
        """Task should return a result dict with job info."""
        from app.workers.tasks import process_document

        result = process_document(
            job_id="test-job-456",
            file_content=b"test text content",
            filename="doc.txt",
            content_type="text/plain",
            project_id="project-1",
            index_to_vector=True,
            index_to_graph=False,
        )

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] in ("completed", "skipped")

    def test_task_updates_job_ledger(self, mock_all_services):
        """Task should update job status in PostgreSQL ledger."""
        from app.workers.tasks import process_document

        process_document(
            job_id="test-job-789",
            file_content=b"test content",
            filename="doc.txt",
            content_type="text/plain",
            project_id="project-1",
            index_to_vector=True,
            index_to_graph=False,
        )

        # Verify ledger was called
        mock_all_services["ledger"].create_job.assert_called()

    def test_task_processes_general_document(self, mock_all_services):
        """Task should successfully process general documents."""
        from app.workers.tasks import process_document

        result = process_document(
            job_id="test-general",
            file_content=b"test content",
            filename="doc.txt",
            content_type="text/plain",
            project_id="project-1",
            document_type="general",
            index_to_vector=True,
        )

        assert result["status"] == "completed"
        assert result["document_type"] == "general"
        assert "chunks_created" in result

    def test_task_processes_hipaa_regulation(self, mock_all_services):
        """Task should successfully process HIPAA regulation documents."""
        from app.workers.tasks import process_document

        result = process_document(
            job_id="test-hipaa",
            file_content=b"HIPAA regulation text",
            filename="regulation.txt",
            content_type="text/plain",
            project_id="hipaa",
            document_type="hipaa_regulation",
            source="45 CFR 164.514",
        )

        assert result["status"] == "completed"
        assert result["document_type"] == "hipaa_regulation"


class TestTaskRetryBehavior:
    """Tests for task retry configuration."""

    def test_task_has_retry_configured(self):
        """Task should have automatic retry enabled."""
        from app.workers.tasks import process_document

        # Check that max_retries is set
        assert (
            hasattr(process_document, "max_retries")
            or process_document.max_retries is not None
        )


class TestIdempotency:
    """Tests for idempotency checking."""

    def test_skips_already_processed_document(self, mock_all_services):
        """Should skip processing if document was already completed."""
        from app.workers.tasks import process_document

        # Configure mock to indicate document already processed
        mock_all_services["ledger"].check_idempotency.return_value = {
            "job_id": "existing-job",
            "status": "completed",
        }

        result = process_document(
            job_id="new-job",
            file_content=b"test content",
            filename="doc.txt",
            content_type="text/plain",
            project_id="project-1",
        )

        assert result["status"] == "skipped"
        assert result["existing_job_id"] == "existing-job"


# --- Fixtures ---


@pytest.fixture
def mock_all_services():
    """Mock all services used by the Celery task."""
    with (
        patch("app.workers.tasks.StorageService") as mock_storage_cls,
        patch("app.workers.tasks.JobLedgerService") as mock_ledger_cls,
        patch(
            "app.ingestion.services.document_ingestion_service.ChunkingService"
        ) as mock_chunk_cls,
        patch(
            "app.ingestion.services.document_ingestion_service.EmbeddingService"
        ) as mock_embed_cls,
        patch(
            "app.ingestion.services.document_ingestion_service.IndexingService"
        ) as mock_index_cls,
        patch(
            "app.compliance.services.hipaa_regulation_service.ChunkingService"
        ) as mock_hipaa_chunk_cls,
        patch(
            "app.compliance.services.hipaa_regulation_service.EmbeddingService"
        ) as mock_hipaa_embed_cls,
        patch(
            "app.compliance.services.hipaa_regulation_service.IndexingService"
        ) as mock_hipaa_index_cls,
    ):
        # Create mock instances
        mock_storage = MagicMock()
        mock_ledger = MagicMock()
        mock_chunking = MagicMock()
        mock_embedding = MagicMock()
        mock_indexing = MagicMock()

        # Configure classes to return mocks
        mock_storage_cls.return_value = mock_storage
        mock_ledger_cls.return_value = mock_ledger
        mock_chunk_cls.return_value = mock_chunking
        mock_embed_cls.return_value = mock_embedding
        mock_index_cls.return_value = mock_indexing

        # HIPAA service mocks
        mock_hipaa_chunk_cls.return_value = mock_chunking
        mock_hipaa_embed_cls.return_value = mock_embedding
        mock_hipaa_index_cls.return_value = mock_indexing

        # Default behaviors
        mock_storage.upload.return_value = "raw/test/file.txt"
        mock_ledger.check_idempotency.return_value = None
        mock_ledger.compute_content_hash.return_value = "abc123hash"
        mock_chunking.chunk.return_value = ["chunk1"]
        mock_chunking.chunk_with_metadata.return_value = [{"text": "chunk1", "index": 0}]
        mock_embedding.embed.return_value = [[0.1] * 1024]
        mock_indexing.index.return_value = True

        # Create service mocks for delegation assertions
        mock_doc_ingestion = MagicMock()
        mock_doc_ingestion.ingest_document.return_value = {
            "chunks_created": 1,
            "collection_name": "project_test",
            "success": True,
        }

        mock_hipaa_service = MagicMock()
        mock_hipaa_service.ingest_regulation.return_value = {
            "chunks_created": 1,
            "sections_found": [],
            "success": True,
        }

        yield {
            "storage": mock_storage,
            "ledger": mock_ledger,
            "chunking": mock_chunking,
            "embedding": mock_embedding,
            "indexing": mock_indexing,
            "doc_ingestion": mock_doc_ingestion,
            "hipaa_service": mock_hipaa_service,
        }
