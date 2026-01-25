"""
Unit tests for ArtifactService.

Tests the canonical artifact registry CRUD operations.
"""

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from shorui_core.artifacts import (
    Artifact,
    ArtifactService,
    ArtifactType,
    JobStatus,
    JobType,
    get_artifact_service,
)
from shorui_core.artifacts.models import StorageBackend


# =============================================================================
# Test: ArtifactType Enum
# =============================================================================


class TestArtifactType:
    """Tests for ArtifactType enum values."""

    def test_ingestion_types_exist(self):
        """Ingestion-related artifact types should exist."""
        assert ArtifactType.RAW_UPLOAD == "raw_upload"
        assert ArtifactType.INGESTION_RESULT == "ingestion_result"
        assert ArtifactType.PROCESSED_DOCUMENT == "processed_document"

    def test_compliance_types_exist(self):
        """Compliance-related artifact types should exist."""
        assert ArtifactType.TRANSCRIPT == "transcript"
        assert ArtifactType.COMPLIANCE_REPORT == "compliance_report"
        assert ArtifactType.REDACTED_TEXT == "redacted_text"

    def test_rag_types_exist(self):
        """RAG-related artifact types should exist."""
        assert ArtifactType.RAG_RETRIEVAL_RESULT == "rag_retrieval_result"
        assert ArtifactType.INDEX_SUMMARY == "index_summary"


# =============================================================================
# Test: JobType Enum
# =============================================================================


class TestJobType:
    """Tests for JobType enum values."""

    def test_ingestion_job_types(self):
        """Ingestion job types should exist."""
        assert JobType.INGESTION_DOCUMENT == "ingestion_document"
        assert JobType.INGESTION_REGULATION == "ingestion_regulation"

    def test_compliance_job_type(self):
        """Compliance job type should exist."""
        assert JobType.COMPLIANCE_TRANSCRIPT == "compliance_transcript"


# =============================================================================
# Test: JobStatus Enum
# =============================================================================


class TestJobStatus:
    """Tests for JobStatus enum values."""

    def test_all_statuses_exist(self):
        """All canonical job statuses should exist."""
        assert JobStatus.PENDING == "pending"
        assert JobStatus.PROCESSING == "processing"
        assert JobStatus.COMPLETED == "completed"
        assert JobStatus.FAILED == "failed"
        assert JobStatus.SKIPPED == "skipped"


# =============================================================================
# Test: Artifact Model
# =============================================================================


class TestArtifactModel:
    """Tests for Artifact Pydantic model."""

    def test_artifact_creation(self):
        """Artifact model should accept all fields."""
        artifact = Artifact(
            artifact_id="test-id",
            tenant_id="tenant-1",
            project_id="project-1",
            artifact_type=ArtifactType.TRANSCRIPT,
            storage_backend=StorageBackend.MINIO,
            storage_pointer="raw/tenant-1/project-1/file.txt",
            content_type="text/plain",
            byte_size=1024,
            sha256="abc123",
            schema_version="1.0",
            created_at=datetime.utcnow(),
            created_by_job_id="job-123",
        )
        assert artifact.artifact_id == "test-id"
        assert artifact.tenant_id == "tenant-1"
        assert artifact.artifact_type == "transcript"

    def test_artifact_from_db_row(self):
        """Artifact.from_db_row should construct from tuple."""
        row = (
            uuid.uuid4(),  # artifact_id
            "tenant-1",  # tenant_id
            "project-1",  # project_id
            "transcript",  # artifact_type
            "minio",  # storage_backend
            "raw/path/file.txt",  # storage_pointer
            "text/plain",  # content_type
            1024,  # byte_size
            "sha256hash",  # sha256
            "1.0",  # schema_version
            datetime.utcnow(),  # created_at
            uuid.uuid4(),  # created_by_job_id
        )
        artifact = Artifact.from_db_row(row)
        assert artifact.tenant_id == "tenant-1"
        assert artifact.storage_pointer == "raw/path/file.txt"


# =============================================================================
# Test: ArtifactService
# =============================================================================


class TestArtifactServiceRegister:
    """Tests for ArtifactService.register()."""

    @patch("shorui_core.artifacts.artifact_service.get_db_connection")
    def test_register_returns_artifact_id(self, mock_get_db):
        """register() should return a UUID artifact ID."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_get_db.return_value = mock_conn

        service = ArtifactService()
        result = service.register(
            tenant_id="tenant-1",
            project_id="project-1",
            artifact_type=ArtifactType.RAW_UPLOAD,
            storage_pointer="raw/tenant-1/project-1/file.pdf",
        )

        assert result is not None
        # Verify it's a valid UUID format
        uuid.UUID(result)

    @patch("shorui_core.artifacts.artifact_service.get_db_connection")
    def test_register_uses_provided_artifact_id(self, mock_get_db):
        """register() should use provided artifact_id if given."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_get_db.return_value = mock_conn

        service = ArtifactService()
        custom_id = "custom-artifact-id"
        result = service.register(
            tenant_id="tenant-1",
            project_id="project-1",
            artifact_type=ArtifactType.TRANSCRIPT,
            storage_pointer="transcripts/file.txt",
            artifact_id=custom_id,
        )

        assert result == custom_id

    @patch("shorui_core.artifacts.artifact_service.get_db_connection")
    def test_register_accepts_string_artifact_type(self, mock_get_db):
        """register() should accept string artifact type."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_get_db.return_value = mock_conn

        service = ArtifactService()
        result = service.register(
            tenant_id="tenant-1",
            project_id="project-1",
            artifact_type="custom_type",  # String instead of enum
            storage_pointer="path/to/file",
        )

        assert result is not None


class TestArtifactServiceGetById:
    """Tests for ArtifactService.get_by_id()."""

    @patch("shorui_core.artifacts.artifact_service.get_db_connection")
    def test_get_by_id_returns_artifact(self, mock_get_db):
        """get_by_id() should return Artifact when found."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            uuid.uuid4(),
            "tenant-1",
            "project-1",
            "transcript",
            "minio",
            "raw/path/file.txt",
            "text/plain",
            1024,
            "sha256hash",
            "1.0",
            datetime.utcnow(),
            uuid.uuid4(),
        )
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_get_db.return_value = mock_conn

        service = ArtifactService()
        result = service.get_by_id("some-id")

        assert result is not None
        assert isinstance(result, Artifact)
        assert result.tenant_id == "tenant-1"

    @patch("shorui_core.artifacts.artifact_service.get_db_connection")
    def test_get_by_id_returns_none_when_not_found(self, mock_get_db):
        """get_by_id() should return None when not found."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_get_db.return_value = mock_conn

        service = ArtifactService()
        result = service.get_by_id("nonexistent-id")

        assert result is None


class TestArtifactServiceGetByJobId:
    """Tests for ArtifactService.get_by_job_id()."""

    @patch("shorui_core.artifacts.artifact_service.get_db_connection")
    def test_get_by_job_id_returns_list(self, mock_get_db):
        """get_by_job_id() should return list of Artifacts."""
        job_id = uuid.uuid4()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (
                uuid.uuid4(),
                "tenant-1",
                "project-1",
                "raw_upload",
                "minio",
                "raw/path/file.pdf",
                "application/pdf",
                2048,
                None,
                None,
                datetime.utcnow(),
                job_id,
            ),
            (
                uuid.uuid4(),
                "tenant-1",
                "project-1",
                "ingestion_result",
                "minio",
                "results/job.json",
                "application/json",
                512,
                None,
                "1.0",
                datetime.utcnow(),
                job_id,
            ),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_get_db.return_value = mock_conn

        service = ArtifactService()
        result = service.get_by_job_id(str(job_id))

        assert len(result) == 2
        assert all(isinstance(a, Artifact) for a in result)

    @patch("shorui_core.artifacts.artifact_service.get_db_connection")
    def test_get_by_job_id_returns_empty_list(self, mock_get_db):
        """get_by_job_id() should return empty list when no artifacts found."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_get_db.return_value = mock_conn

        service = ArtifactService()
        result = service.get_by_job_id("nonexistent-job")

        assert result == []


class TestArtifactServiceFactory:
    """Tests for get_artifact_service() factory."""

    def test_factory_returns_artifact_service(self):
        """get_artifact_service() should return ArtifactService instance."""
        # Reset singleton for test
        import shorui_core.artifacts.artifact_service as module
        module._artifact_service = None

        service = get_artifact_service()
        assert isinstance(service, ArtifactService)

    def test_factory_returns_singleton(self):
        """get_artifact_service() should return the same instance."""
        import shorui_core.artifacts.artifact_service as module
        module._artifact_service = None

        service1 = get_artifact_service()
        service2 = get_artifact_service()
        assert service1 is service2
