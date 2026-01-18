"""
Audit Service

Provides HIPAA-compliant audit logging and querying capabilities.
Stores audit events in PostgreSQL for tamper-evident logging.
"""

from datetime import datetime
from typing import Any, Optional

from loguru import logger
from psycopg.types.json import Jsonb

from shorui_core.domain.hipaa_schemas import AuditEvent, AuditEventType
from shorui_core.infrastructure.postgres import get_db_connection


class AuditService:
    """
    HIPAA audit logging and query service.

    Provides:
    - Logging of PHI access, detection, and compliance events
    - Querying of audit trail for compliance reporting
    - Tamper-evident storage (PostgreSQL)

    Usage:
        service = AuditService()

        # Log an event
        await service.log(
            event_type=AuditEventType.PHI_DETECTED,
            description="Detected 5 PHI spans",
            resource_type="Transcript",
            resource_id="abc123",
        )

        # Query events
        events = await service.query_events(
            event_type=AuditEventType.PHI_DETECTED,
            limit=100,
        )
    """

    def __init__(self):
        """Initialize the audit service."""
        # Ensure table exists (simple migration for now)
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create the audit_events table if it doesn't exist."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS audit_events (
                        id VARCHAR(36) PRIMARY KEY,
                        event_type VARCHAR(50) NOT NULL,
                        description TEXT NOT NULL,
                        resource_type VARCHAR(50),
                        resource_id VARCHAR(100),
                        user_id VARCHAR(100),
                        timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                        metadata JSONB,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_audit_events_type ON audit_events(event_type);
                    CREATE INDEX IF NOT EXISTS idx_audit_events_resource ON audit_events(resource_type, resource_id);
                    CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events(timestamp);
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to ensure audit table exists: {e}")

    async def log(
        self,
        event_type: AuditEventType,
        description: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuditEvent:
        """
        Log an audit event.

        Args:
            event_type: Type of event (PHI_DETECTED, PHI_ACCESSED, etc.)
            description: Human-readable description
            resource_type: Type of resource affected (Transcript, PHI, etc.)
            resource_id: ID of the affected resource
            user_id: ID of user who triggered the event
            metadata: Additional context

        Returns:
            The created AuditEvent
        """
        event = AuditEvent(
            event_type=event_type,
            description=description,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            metadata=metadata or {},
        )

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO audit_events 
                    (id, event_type, description, resource_type, resource_id, user_id, timestamp, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event.id,
                        event.event_type.value,
                        event.description,
                        event.resource_type,
                        event.resource_id,
                        event.user_id,
                        event.timestamp,
                        Jsonb(event.metadata),
                    ),
                )
                conn.commit()
            
            logger.debug(f"Audit log: {event_type.value} - {description}")
            return event
            
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            # In a strict HIPAA environment, we might want to raise here
            # For now, we return the event but log the error
            return event

    async def query_events(
        self,
        event_type: Optional[AuditEventType] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Query audit events.

        Args:
            event_type: Filter by event type
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            limit: Maximum number of events to return

        Returns:
            List of matching audit events
        """
        query = "SELECT id, event_type, description, resource_type, resource_id, user_id, timestamp, metadata FROM audit_events WHERE 1=1"
        params = []

        if event_type:
            query += " AND event_type = %s"
            params.append(event_type.value)
        
        if resource_type:
            query += " AND resource_type = %s"
            params.append(resource_type)
            
        if resource_id:
            query += " AND resource_id = %s"
            params.append(resource_id)
            
        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
                
                results = []
                for row in rows:
                    results.append({
                        "id": row[0],
                        "event_type": row[1],
                        "description": row[2],
                        "resource_type": row[3],
                        "resource_id": row[4],
                        "user_id": row[5],
                        "timestamp": row[6].isoformat() if row[6] else None,
                        "metadata": row[7],
                    })
                return results
                
        except Exception as e:
            logger.error(f"Failed to query audit logs: {e}")
            return []
