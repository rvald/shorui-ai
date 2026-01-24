"""
Unit tests for PostgreSQL job ledger service.

The job ledger should:
1. Track document processing jobs with status
2. Provide idempotency (prevent duplicate processing)
3. Store DLQ entries for failed jobs
"""

from unittest.mock import MagicMock, patch

import pytest


class TestJobLedgerCreate:
    """Tests for creating job entries."""

    def test_create_job_returns_job_id(self, mock_postgres):
        """Creating a job should return a job ID."""
        from app.ingestion.services.job_ledger import JobLedgerService

        service = JobLedgerService()

        job_id = service.create_job(
            tenant_id="tenant-1",
            project_id="project-1",
            job_type="ingestion_document",
            raw_pointer="raw/tenant-1/project-1/uuid_doc.pdf",
        )

        assert job_id is not None
        assert isinstance(job_id, str)

    def test_create_job_inserts_to_database(self, mock_postgres):
        """Create should insert a record into the database."""
        from app.ingestion.services.job_ledger import JobLedgerService

        service = JobLedgerService()
        mock_cursor = mock_postgres["cursor"]

        service.create_job(
            tenant_id="tenant-1",
            project_id="project-1",
            job_type="ingestion_document",
            raw_pointer="raw/tenant-1/project-1/uuid_doc.pdf",
        )

        # Should have executed an INSERT
        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0][0]
        assert "INSERT" in call_args.upper()

    def test_create_job_uses_provided_job_id(self, mock_postgres):
        """When job_id is provided, create_job should use it instead of generating new one.

        Regression test: Previously create_job always generated a new UUID, causing
        mismatch with the route's job_id. Now it accepts an optional job_id parameter.
        """
        from app.ingestion.services.job_ledger import JobLedgerService

        service = JobLedgerService()
        provided_id = "my-custom-job-id-12345"

        returned_id = service.create_job(
            tenant_id="tenant-1",
            project_id="project-1",
            job_type="ingestion_document",
            raw_pointer="raw/tenant-1/project-1/uuid_doc.pdf",
            job_id=provided_id,
        )

        # The returned job_id should match what we provided
        assert returned_id == provided_id

    def test_create_job_inserts_provided_job_id_to_database(self, mock_postgres):
        """The provided job_id should be inserted into the database, not a new one.

        Regression test: Ensures the INSERT uses the provided job_id so that
        subsequent complete_job(job_id) calls can find the record.
        """
        from app.ingestion.services.job_ledger import JobLedgerService

        service = JobLedgerService()
        mock_cursor = mock_postgres["cursor"]
        provided_id = "route-generated-uuid-abc123"

        service.create_job(
            tenant_id="tenant-1",
            project_id="project-1",
            job_type="ingestion_document",
            raw_pointer="raw/tenant-1/project-1/uuid_doc.pdf",
            job_id=provided_id,
        )

        # Verify the INSERT was called with our provided job_id
        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0]  # (query, params)
        params = call_args[1]  # The tuple of parameters

        # First parameter should be our job_id
        assert params[0] == provided_id


class TestJobLedgerUpdate:
    """Tests for updating job status."""

    def test_update_status_changes_job_state(self, mock_postgres):
        """Updating status should modify the job record."""
        from app.ingestion.services.job_ledger import JobLedgerService

        service = JobLedgerService()
        mock_cursor = mock_postgres["cursor"]

        service.update_status("job-123", "processing", progress=50)

        # Should have executed an UPDATE
        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0][0]
        assert "UPDATE" in call_args.upper()

    def test_complete_job_sets_completed_status(self, mock_postgres):
        """Completing a job should set status to 'completed'."""
        from app.ingestion.services.job_ledger import JobLedgerService

        service = JobLedgerService()

        service.complete_job("job-123", items_indexed=1759)

        mock_cursor = mock_postgres["cursor"]
        call_args = mock_cursor.execute.call_args[0]
        assert "completed" in str(call_args).lower()


class TestJobLedgerIdempotency:
    """Tests for idempotency checking."""

    def test_check_idempotency_returns_existing_job(self, mock_postgres):
        """If document was already processed, return existing job."""
        from app.ingestion.services.job_ledger import JobLedgerService

        service = JobLedgerService()
        mock_cursor = mock_postgres["cursor"]

        # Simulate existing job found (3 columns: job_id, status, result_pointer)
        mock_cursor.fetchone.return_value = ("existing-job-id", "completed", "processed/results/existing.json")

        result = service.check_idempotency(
            idempotency_key="abc123hash",
            job_type="ingestion_document",
            tenant_id="tenant-1",
            project_id="project-1",
        )

        assert result is not None
        assert result["job_id"] == "existing-job-id"
        assert result["status"] == "completed"

    def test_check_idempotency_returns_none_for_new(self, mock_postgres):
        """If document is new, return None."""
        from app.ingestion.services.job_ledger import JobLedgerService

        service = JobLedgerService()
        mock_cursor = mock_postgres["cursor"]

        # No existing job
        mock_cursor.fetchone.return_value = None

        result = service.check_idempotency(
            idempotency_key="newhash",
            job_type="ingestion_document",
            tenant_id="tenant-1",
            project_id="project-1",
        )

        assert result is None


class TestJobLedgerFailure:
    """Tests for handling failed jobs."""

    def test_fail_job_records_error(self, mock_postgres):
        """Failing a job should record the error message."""
        from app.ingestion.services.job_ledger import JobLedgerService

        service = JobLedgerService()

        service.fail_job("job-123", error="Connection timeout")

        mock_cursor = mock_postgres["cursor"]
        call_args = mock_cursor.execute.call_args[0]
        assert "failed" in str(call_args).lower()

    def test_add_to_dlq_creates_dlq_entry(self, mock_postgres):
        """Adding to DLQ should create a dead letter entry."""
        from app.ingestion.services.job_ledger import JobLedgerService

        service = JobLedgerService()
        mock_cursor = mock_postgres["cursor"]

        service.add_to_dlq("job-123", error="Max retries exceeded", traceback="...")

        # Should have inserted to DLQ table
        call_args = mock_cursor.execute.call_args[0][0]
        assert "INSERT" in call_args.upper()
        assert "dead_letter" in call_args.lower()


# --- Fixtures ---


@pytest.fixture
def mock_postgres():
    """Provides mock PostgreSQL connection and cursor."""
    with patch("app.ingestion.services.job_ledger.get_db_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_get_conn.return_value = mock_conn

        yield {
            "connection": mock_conn,
            "cursor": mock_cursor,
        }
