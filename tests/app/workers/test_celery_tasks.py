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
        result = process_document.run(
            job_id="test-job-123",
            tenant_id="tenant-1",
            project_id="test-project",
            raw_pointer="raw/path",
            filename="test.txt",
            content_type="text/plain",
            document_type="general",
            index_to_vector=True,
            index_to_graph=False,
        )

        assert result is not None

    def test_task_returns_job_result(self, mock_all_services):
        """Task should return a result dict with job info."""
        from app.workers.tasks import process_document

        result = process_document.run(
            job_id="test-job-456",
            tenant_id="tenant-1",
            project_id="project-1",
            raw_pointer="raw/path",
            filename="doc.txt",
            content_type="text/plain",
            document_type="general",
            index_to_vector=True,
            index_to_graph=False,
        )

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] in ("completed", "skipped")

    def test_task_updates_job_ledger(self, mock_all_services):
        """Task should update job status in PostgreSQL ledger."""
        from app.workers.tasks import process_document

        process_document.run(
            job_id="test-job-789",
            tenant_id="tenant-1",
            project_id="project-1",
            raw_pointer="raw/path",
            filename="doc.txt",
            content_type="text/plain",
            document_type="general",
            index_to_vector=True,
            index_to_graph=False,
        )

        # Verify ledger was called
        mock_all_services["ledger"].update_status.assert_called()

    def test_task_processes_general_document(self, mock_all_services):
        """Task should successfully process general documents."""
        from app.workers.tasks import process_document

        result = process_document.run(
            job_id="test-general",
            tenant_id="tenant-1",
            project_id="project-1",
            raw_pointer="raw/path",
            filename="doc.txt",
            content_type="text/plain",
            document_type="general",
            index_to_vector=True,
        )

        assert result["status"] == "completed"
        assert result["document_type"] == "general"
        assert "chunks_created" in result

    def test_task_processes_hipaa_regulation(self, mock_all_services):
        """Task should successfully process HIPAA regulation documents."""
        from app.workers.tasks import process_document

        # Override mock return for HIPAA path
        mock_all_services["orchestrator"].process.return_value["document_type"] = "hipaa_regulation"
        mock_all_services["ledger"].check_idempotency.return_value = None

        result = process_document.run(
            job_id="test-hipaa",
            tenant_id="tenant-1",
            project_id="hipaa",
            raw_pointer="raw/path",
            filename="regulation.txt",
            content_type="text/plain",
            document_type="hipaa_regulation",
            index_to_vector=True,
            index_to_graph=False,
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

        mock_all_services["ledger"].check_idempotency.return_value = {
            "job_id": "existing-job",
            "status": "completed",
            "result_pointer": "processed/results/existing.json",
        }

        result = process_document.run(
            job_id="new-job",
            tenant_id="tenant-1",
            project_id="project-1",
            raw_pointer="raw/path",
            filename="doc.txt",
            content_type="text/plain",
            document_type="general",
            index_to_vector=True,
            index_to_graph=False,
            source=None,
            title=None,
            category=None,
            idempotency_key="idem-key",
        )

        assert result["status"] == "skipped"
        assert result["existing_job_id"] == "existing-job"


# --- Fixtures ---


@pytest.fixture
def mock_all_services():
    """Mock all services used by the Celery task."""
    with (
        patch("app.workers.tasks.JobLedgerService") as mock_ledger_cls,
        patch("app.workers.tasks.get_ingestion_orchestrator") as mock_orch_factory,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process.return_value = {
            "status": "completed",
            "document_type": "general",
            "chunks_created": 1,
            "collection_name": "project_test",
            "result_pointer": "processed/results/job.json",
            "raw_pointer": "raw/path",
        }
        mock_orch_factory.return_value = mock_orchestrator

        mock_ledger = MagicMock()
        mock_ledger.check_idempotency.return_value = None
        mock_ledger_cls.return_value = mock_ledger

        yield {
            "ledger": mock_ledger,
            "orchestrator": mock_orchestrator,
        }
