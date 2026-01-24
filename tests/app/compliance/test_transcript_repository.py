"""
Unit tests for TranscriptRepository.

Tests the CRUD operations for transcript records using mocked PostgreSQL.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.compliance.services.transcript_repository import TranscriptRepository


class TestTranscriptCreate:
    """Tests for creating transcript records."""

    def test_create_inserts_to_db(self, mock_postgres):
        """Creating a transcript should insert into database."""
        repo = TranscriptRepository()
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.reset_mock()

        result = repo.create(
            tenant_id="tenant-1",
            project_id="project-1",
            filename="notes.txt",
            storage_pointer="raw/tenant-1/project-1/uuid_notes.txt",
            byte_size=1024,
            text_length=500,
            file_hash="abc123",
            job_id="job-uuid",
        )

        # Should have executed INSERT
        mock_cursor.execute.assert_called()
        query = str(mock_cursor.execute.call_args[0][0]).upper()
        assert "INSERT INTO TRANSCRIPTS" in query
        assert result is not None

    def test_create_returns_transcript_id(self, mock_postgres):
        """Creating a transcript should return the transcript ID."""
        repo = TranscriptRepository()

        result = repo.create(
            tenant_id="tenant-1",
            project_id="project-1",
            filename="notes.txt",
            storage_pointer="raw/tenant-1/project-1/uuid_notes.txt",
        )

        # Should return a UUID string
        assert isinstance(result, str)
        assert len(result) == 36  # UUID format

    def test_create_with_preset_id(self, mock_postgres):
        """Creating with a preset transcript_id should use that ID."""
        repo = TranscriptRepository()

        result = repo.create(
            tenant_id="tenant-1",
            project_id="project-1",
            filename="notes.txt",
            storage_pointer="raw/path",
            transcript_id="preset-uuid-123",
        )

        assert result == "preset-uuid-123"


class TestTranscriptGetById:
    """Tests for retrieving transcripts by ID."""

    def test_get_by_id_returns_dict(self, mock_postgres):
        """Getting a transcript returns a dictionary."""
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchone.return_value = (
            "trans-123",  # transcript_id
            "tenant-1",   # tenant_id
            "project-1",  # project_id
            "notes.txt",  # filename
            "raw/path",   # storage_pointer
            1024,         # byte_size
            500,          # text_length
            "abc123",     # file_hash
            None,         # created_at
            "job-123",    # created_by_job_id
        )

        repo = TranscriptRepository()
        result = repo.get_by_id("trans-123")

        assert result is not None
        assert result["transcript_id"] == "trans-123"
        assert result["tenant_id"] == "tenant-1"
        assert result["project_id"] == "project-1"
        assert result["filename"] == "notes.txt"

    def test_get_by_id_not_found(self, mock_postgres):
        """Getting a non-existent transcript returns None."""
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchone.return_value = None

        repo = TranscriptRepository()
        result = repo.get_by_id("nonexistent")

        assert result is None


class TestTranscriptGetByJobId:
    """Tests for retrieving transcripts by job ID."""

    def test_get_by_job_id_returns_dict(self, mock_postgres):
        """Getting a transcript by job ID returns a dictionary."""
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchone.return_value = (
            "trans-123",
            "tenant-1",
            "project-1",
            "notes.txt",
            "raw/path",
            1024,
            500,
            "abc123",
            None,
            "job-123",
        )

        repo = TranscriptRepository()
        result = repo.get_by_job_id("job-123")

        assert result is not None
        assert result["created_by_job_id"] == "job-123"

    def test_get_by_job_id_not_found(self, mock_postgres):
        """Getting by non-existent job ID returns None."""
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchone.return_value = None

        repo = TranscriptRepository()
        result = repo.get_by_job_id("nonexistent")

        assert result is None


@pytest.fixture
def mock_postgres():
    """Provides mock PostgreSQL connection and cursor."""
    with patch("app.compliance.services.transcript_repository.get_db_connection") as mock_get_conn:
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
