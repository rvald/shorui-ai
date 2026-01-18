"""
Unit tests for AuditService.

Tests the HIPAA-compliant audit logging and querying capabilities
using mocked PostgreSQL connections.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.compliance.services.audit_service import AuditService
from shorui_core.domain.hipaa_schemas import AuditEventType


class TestAuditServiceInit:
    """Tests for service initialization."""

    def test_init_creates_table(self, mock_postgres):
        """Initializing service should attempt to create table."""
        mock_cursor = mock_postgres["cursor"]
        
        AuditService()
        
        # Should have executed CREATE TABLE
        mock_cursor.execute.assert_called()
        call_args = str(mock_cursor.execute.call_args[0][0]).upper()
        assert "CREATE TABLE" in call_args
        assert "AUDIT_EVENTS" in call_args


class TestAuditLog:
    """Tests for logging audit events."""

    @pytest.mark.asyncio
    async def test_log_event_inserts_to_db(self, mock_postgres):
        """Logging an event should insert into database."""
        service = AuditService()
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.reset_mock()  # Clear init calls

        await service.log(
            event_type=AuditEventType.PHI_DETECTED,
            description="Found PHI",
            resource_type="Transcript",
            resource_id="123"
        )

        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0]
        query = call_args[0].upper()
        
        assert "INSERT INTO AUDIT_EVENTS" in query
        assert "VALUES" in query

    @pytest.mark.asyncio
    async def test_log_returns_event_object(self, mock_postgres):
        """Logging should return the created event object."""
        service = AuditService()
        
        event = await service.log(
            event_type=AuditEventType.USER_LOGIN,
            description="User logged in"
        )

        assert event.event_type == AuditEventType.USER_LOGIN
        assert event.description == "User logged in"
        assert event.id is not None
        assert event.timestamp is not None


class TestAuditQuery:
    """Tests for querying audit events."""

    @pytest.mark.asyncio
    async def test_query_executes_select(self, mock_postgres):
        """Querying events should execute SELECT statement."""
        service = AuditService()
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.reset_mock()

        # Mock results
        mock_cursor.fetchall.return_value = []

        await service.query_events(limit=50)

        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0]
        query = str(call_args[0]).upper()
        params = call_args[1]
        
        assert "SELECT" in query
        assert "FROM AUDIT_EVENTS" in query
        assert "LIMIT %S" in query.replace("%s", "%S")  # Normalize placeholder check
        assert 50 in params

    @pytest.mark.asyncio
    async def test_query_filters_by_type(self, mock_postgres):
        """Querying with filters should add WHERE clauses."""
        service = AuditService()
        mock_cursor = mock_postgres["cursor"]
        mock_cursor.reset_mock()
        mock_cursor.fetchall.return_value = []

        await service.query_events(
            event_type=AuditEventType.PHI_DETECTED,
            resource_id="res-123"
        )

        query = str(mock_cursor.execute.call_args[0][0]).upper()
        params = mock_cursor.execute.call_args[0][1]

        assert "EVENT_TYPE =" in query
        assert "RESOURCE_ID =" in query
        assert AuditEventType.PHI_DETECTED.value in params
        assert "res-123" in params


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
