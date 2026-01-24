"""
Unit tests for AuditService.

Tests the HIPAA-compliant audit logging and querying capabilities
with hash-chaining for tamper evidence.
"""

from unittest.mock import MagicMock, patch
import hashlib
import json

import pytest

from app.compliance.services.audit_service import AuditService, ALLOWED_METADATA_KEYS
from shorui_core.domain.hipaa_schemas import AuditEventType


class TestAuditServiceInit:
    """Tests for service initialization."""

    def test_init_does_not_create_table(self, mock_postgres):
        """Initializing service should NOT attempt to create table (removed DDL)."""
        mock_cursor = mock_postgres["cursor"]
        
        AuditService()
        
        # Should NOT have executed CREATE TABLE (DDL removed)
        mock_cursor.execute.assert_not_called()


class TestAuditLog:
    """Tests for logging audit events."""

    @pytest.mark.asyncio
    async def test_log_event_inserts_with_hash_chain(self, mock_postgres):
        """Logging an event should insert with hash chain fields."""
        service = AuditService()
        mock_cursor = mock_postgres["cursor"]
        
        # Mock no previous events
        mock_cursor.fetchone.return_value = None

        await service.log(
            event_type=AuditEventType.PHI_DETECTED,
            description="Found PHI",
            tenant_id="tenant-123",
            project_id="project-456",
            resource_type="Transcript",
            resource_id="123"
        )

        mock_cursor.execute.assert_called()
        
        # Find the INSERT call
        insert_call = None
        for call in mock_cursor.execute.call_args_list:
            query_str = str(call[0][0]).upper()
            if "INSERT INTO AUDIT_EVENTS" in query_str:
                insert_call = call
                break
        
        assert insert_call is not None, f"No INSERT call found. Calls: {mock_cursor.execute.call_args_list}"
        query = insert_call[0][0].upper()
        
        assert "PREVIOUS_HASH" in query
        assert "EVENT_HASH" in query
        assert "TENANT_ID" in query
        assert "PROJECT_ID" in query

    @pytest.mark.asyncio
    async def test_log_returns_event_object(self, mock_postgres):
        """Logging should return the created event object."""
        service = AuditService()
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchone.return_value = None
        
        event = await service.log(
            event_type=AuditEventType.USER_LOGIN,
            description="User logged in",
            tenant_id="tenant-1",
            project_id="project-1",
        )

        assert event.event_type == AuditEventType.USER_LOGIN
        assert event.description == "User logged in"
        assert event.tenant_id == "tenant-1"
        assert event.project_id == "project-1"
        assert event.id is not None
        assert event.timestamp is not None

    @pytest.mark.asyncio
    async def test_log_chains_to_previous_hash(self, mock_postgres):
        """Logging should chain to the previous event's hash."""
        service = AuditService()
        mock_cursor = mock_postgres["cursor"]
        
        # Mock a previous hash exists
        previous_hash = "abc123def456"
        mock_cursor.fetchone.return_value = (previous_hash,)

        await service.log(
            event_type=AuditEventType.PHI_DETECTED,
            description="Found PHI",
            tenant_id="tenant-123",
            project_id="project-456",
        )

        # Check that the INSERT includes the previous_hash
        insert_call = None
        for call in mock_cursor.execute.call_args_list:
            query_str = str(call[0][0]).upper()
            if "INSERT INTO AUDIT_EVENTS" in query_str:
                insert_call = call
                break
        
        assert insert_call is not None, f"No INSERT call found. Calls: {mock_cursor.execute.call_args_list}"
        params = insert_call[0][1]
        # previous_hash should be in the params (position -2)
        assert previous_hash in params

    @pytest.mark.asyncio
    async def test_log_first_event_has_null_previous_hash(self, mock_postgres):
        """First event should have None as previous_hash."""
        service = AuditService()
        mock_cursor = mock_postgres["cursor"]
        
        # No previous events
        mock_cursor.fetchone.return_value = None

        await service.log(
            event_type=AuditEventType.PHI_DETECTED,
            description="First event",
            tenant_id="tenant-123",
            project_id="project-456",
        )

        insert_call = None
        for call in mock_cursor.execute.call_args_list:
            query_str = str(call[0][0]).upper()
            if "INSERT INTO AUDIT_EVENTS" in query_str:
                insert_call = call
                break
        
        assert insert_call is not None, f"No INSERT call found. Calls: {mock_cursor.execute.call_args_list}"
        params = insert_call[0][1]
        # previous_hash (second to last param) should be None
        assert params[-2] is None


class TestMetadataValidation:
    """Tests for PHI-safe metadata validation."""

    @pytest.mark.asyncio
    async def test_allowed_metadata_passes_through(self, mock_postgres):
        """Metadata with allowed keys should pass through."""
        service = AuditService()
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchone.return_value = None
        
        event = await service.log(
            event_type=AuditEventType.PHI_DETECTED,
            description="Test",
            tenant_id="t",
            project_id="p",
            metadata={"phi_count": 5, "job_id": "abc-123"},
        )

        assert event.metadata == {"phi_count": 5, "job_id": "abc-123"}

    @pytest.mark.asyncio
    async def test_disallowed_metadata_filtered_out(self, mock_postgres):
        """Metadata with disallowed keys should be filtered."""
        service = AuditService()
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchone.return_value = None
        
        event = await service.log(
            event_type=AuditEventType.PHI_DETECTED,
            description="Test",
            tenant_id="t",
            project_id="p",
            metadata={
                "phi_count": 5,           # allowed
                "patient_name": "John",   # NOT allowed (PHI!)
                "ssn": "123-45-6789",     # NOT allowed (PHI!)
            },
        )

        # Only allowed keys remain
        assert "phi_count" in event.metadata
        assert "patient_name" not in event.metadata
        assert "ssn" not in event.metadata


class TestAuditQuery:
    """Tests for querying audit events."""

    @pytest.mark.asyncio
    async def test_query_requires_tenant_and_project(self, mock_postgres):
        """Querying events requires tenant_id and project_id."""
        service = AuditService()
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchall.return_value = []

        await service.query_events(
            tenant_id="tenant-123",
            project_id="project-456",
            limit=50
        )

        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0]
        query = str(call_args[0]).upper()
        params = call_args[1]
        
        assert "TENANT_ID = %S" in query.replace("%s", "%S")
        assert "PROJECT_ID = %S" in query.replace("%s", "%S")
        assert "tenant-123" in params
        assert "project-456" in params

    @pytest.mark.asyncio
    async def test_query_filters_by_type(self, mock_postgres):
        """Querying with filters should add WHERE clauses."""
        service = AuditService()
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.fetchall.return_value = []

        await service.query_events(
            tenant_id="tenant-123",
            project_id="project-456",
            event_type=AuditEventType.PHI_DETECTED,
            resource_id="res-123"
        )

        query = str(mock_cursor.execute.call_args[0][0]).upper()
        params = mock_cursor.execute.call_args[0][1]

        assert "EVENT_TYPE =" in query
        assert "RESOURCE_ID =" in query
        assert AuditEventType.PHI_DETECTED.value in params
        assert "res-123" in params


class TestHashComputation:
    """Tests for hash computation logic."""

    def test_compute_event_hash_is_deterministic(self):
        """Same inputs should produce same hash."""
        service = AuditService()
        
        event_data = {
            "id": "test-id",
            "tenant_id": "t1",
            "project_id": "p1",
            "event_type": "PHI_DETECTED",
            "description": "Test",
        }
        
        hash1 = service._compute_event_hash(event_data, None)
        hash2 = service._compute_event_hash(event_data, None)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length

    def test_compute_event_hash_changes_with_previous_hash(self):
        """Different previous_hash should produce different event_hash."""
        service = AuditService()
        
        event_data = {"id": "test-id", "description": "Test"}
        
        hash1 = service._compute_event_hash(event_data, None)
        hash2 = service._compute_event_hash(event_data, "abc123")
        
        assert hash1 != hash2

    def test_compute_event_hash_changes_with_data(self):
        """Different event data should produce different hash."""
        service = AuditService()
        
        hash1 = service._compute_event_hash({"id": "1", "desc": "A"}, None)
        hash2 = service._compute_event_hash({"id": "1", "desc": "B"}, None)
        
        assert hash1 != hash2


@pytest.fixture
def mock_postgres():
    """Provides mock PostgreSQL connection and cursor."""
    with patch("app.compliance.services.audit_service.get_db_connection") as mock_get_conn:
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
