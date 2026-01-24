"""
Unit tests for ReportRepository.

Tests the CRUD operations for compliance report records using mocked PostgreSQL.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.compliance.services.report_repository import ReportRepository


class TestReportCreate:
    """Tests for creating report records."""

    def test_create_inserts_to_db(self, mock_postgres, mock_report):
        """Creating a report should insert into database."""
        repo = ReportRepository()
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.reset_mock()

        result = repo.create(
            tenant_id="tenant-1",
            project_id="project-1",
            transcript_id="trans-123",
            report=mock_report,
            job_id="job-uuid",
        )

        # Should have executed INSERT
        mock_cursor.execute.assert_called()
        query = str(mock_cursor.execute.call_args[0][0]).upper()
        assert "INSERT INTO COMPLIANCE_REPORTS" in query
        assert result is not None

    def test_create_returns_report_id(self, mock_postgres, mock_report):
        """Creating a report should return the report ID."""
        repo = ReportRepository()

        result = repo.create(
            tenant_id="tenant-1",
            project_id="project-1",
            transcript_id="trans-123",
            report=mock_report,
        )

        # Should return a UUID string
        assert isinstance(result, str)

    def test_create_stores_jsonb(self, mock_postgres, mock_report):
        """Creating a report should store sections as JSONB."""
        repo = ReportRepository()
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.reset_mock()

        repo.create(
            tenant_id="tenant-1",
            project_id="project-1",
            transcript_id="trans-123",
            report=mock_report,
        )

        # Check the params include JSON
        params = mock_cursor.execute.call_args[0][1]
        # The 8th param (index 7) is report_json
        json_str = params[7]
        parsed = json.loads(json_str)
        assert "sections" in parsed


class TestReportGetById:
    """Tests for retrieving reports by ID."""

    def test_get_by_id_returns_dict(self, mock_postgres):
        """Getting a report returns a dictionary."""
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchone.return_value = (
            "report-123",   # report_id
            "tenant-1",     # tenant_id
            "project-1",    # project_id
            "trans-123",    # transcript_id
            "HIGH",         # overall_risk_level
            5,              # total_phi_detected
            2,              # total_violations
            '{"sections": []}',  # report_json
            "1.0",          # schema_version
            datetime.now(), # generated_at
            "job-123",      # created_by_job_id
        )

        repo = ReportRepository()
        result = repo.get_by_id("report-123")

        assert result is not None
        assert result["report_id"] == "report-123"
        assert result["overall_risk_level"] == "HIGH"
        assert result["total_phi_detected"] == 5

    def test_get_by_id_not_found(self, mock_postgres):
        """Getting a non-existent report returns None."""
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchone.return_value = None

        repo = ReportRepository()
        result = repo.get_by_id("nonexistent")

        assert result is None


class TestReportGetByTranscriptId:
    """Tests for retrieving reports by transcript ID."""

    def test_get_by_transcript_id_returns_dict(self, mock_postgres):
        """Getting a report by transcript ID returns a dictionary."""
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchone.return_value = (
            "report-123",
            "tenant-1",
            "project-1",
            "trans-123",
            "MEDIUM",
            3,
            1,
            '{"sections": [{"title": "Summary", "findings": [], "recommendations": [], "severity": "INFO"}]}',
            "1.0",
            datetime.now(),
            "job-123",
        )

        repo = ReportRepository()
        result = repo.get_by_transcript_id("trans-123")

        assert result is not None
        assert result["transcript_id"] == "trans-123"
        assert len(result["report_json"]["sections"]) == 1

    def test_get_by_transcript_id_not_found(self, mock_postgres):
        """Getting by non-existent transcript ID returns None."""
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchone.return_value = None

        repo = ReportRepository()
        result = repo.get_by_transcript_id("nonexistent")

        assert result is None


@pytest.fixture
def mock_postgres():
    """Provides mock PostgreSQL connection and cursor."""
    with patch("app.compliance.services.report_repository.get_db_connection") as mock_get_conn:
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


@pytest.fixture
def mock_report():
    """Provides a mock ComplianceReport object."""
    mock = MagicMock()
    mock.id = None  # Let repo generate ID
    mock.overall_risk_level = "HIGH"
    mock.total_phi_detected = 5
    mock.total_violations = 2
    mock.transcript_ids = ["trans-123"]
    mock.generated_at = datetime.now()
    
    # Mock sections
    section = MagicMock()
    section.title = "PHI Summary"
    section.findings = ["Found 5 PHI instances"]
    section.recommendations = ["Review data handling"]
    section.severity = "INFO"
    mock.sections = [section]
    
    return mock
