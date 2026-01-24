"""
Audit Service

Provides HIPAA-compliant audit logging and querying capabilities.
Stores audit events in PostgreSQL with tamper-evident hash chaining.
"""

import hashlib
import json
from datetime import datetime
from typing import Any, Optional

from loguru import logger
from psycopg.types.json import Jsonb

from shorui_core.domain.hipaa_schemas import AuditEvent, AuditEventType
from shorui_core.infrastructure.postgres import get_db_connection


# Allowlist of permitted metadata keys (PHI-safe)
ALLOWED_METADATA_KEYS = frozenset({
    "count",
    "phi_count",
    "violation_count",
    "risk_level",
    "job_id",
    "transcript_id",
    "report_id",
    "document_type",
    "byte_size",
    "items_indexed",
    "processing_time_ms",
    "detector",
    "model_version",
    "request_id",
})


class AuditService:
    """
    HIPAA audit logging and query service with tamper-evident hash chaining.

    Provides:
    - Logging of PHI access, detection, and compliance events
    - Hash-chained audit trail for tamper evidence
    - Querying of audit trail for compliance reporting
    - Tenant/project scoped entries

    Usage:
        service = AuditService()

        # Log an event
        await service.log(
            event_type=AuditEventType.PHI_DETECTED,
            description="Detected 5 PHI spans",
            tenant_id="tenant-123",
            project_id="project-456",
            resource_type="Transcript",
            resource_id="abc123",
            metadata={"phi_count": 5},
        )

        # Query events
        events = await service.query_events(
            tenant_id="tenant-123",
            project_id="project-456",
            event_type=AuditEventType.PHI_DETECTED,
            limit=100,
        )
    """

    def __init__(self):
        """Initialize the audit service."""
        # No runtime DDL - schema is managed via init-db.sql
        pass

    def _validate_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Validate and filter metadata to only allowed keys.
        
        This prevents accidental PHI leakage into audit logs.
        """
        if not metadata:
            return {}
        
        filtered = {}
        for key, value in metadata.items():
            if key in ALLOWED_METADATA_KEYS:
                filtered[key] = value
            else:
                logger.warning(f"Audit metadata key '{key}' not in allowlist, skipping")
        
        return filtered

    def _compute_event_hash(
        self, 
        event_data: dict[str, Any], 
        previous_hash: str | None
    ) -> str:
        """
        Compute SHA-256 hash of event data + previous hash for tamper evidence.
        
        Uses canonical JSON serialization (sorted keys) for deterministic hashing.
        """
        canonical = json.dumps(event_data, sort_keys=True, default=str)
        hash_input = (previous_hash or "") + canonical
        return hashlib.sha256(hash_input.encode()).hexdigest()

    def _get_last_event_hash(self, cursor) -> str | None:
        """
        Get the event_hash of the most recent audit event.
        
        This is called within a transaction to ensure atomicity.
        """
        cursor.execute("""
            SELECT event_hash 
            FROM audit_events 
            ORDER BY sequence_number DESC 
            LIMIT 1
            FOR UPDATE
        """)
        row = cursor.fetchone()
        return row[0] if row else None

    async def log(
        self,
        event_type: AuditEventType,
        description: str,
        tenant_id: str,
        project_id: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_ip: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuditEvent:
        """
        Log an audit event with hash chaining for tamper evidence.

        Args:
            event_type: Type of event (PHI_DETECTED, PHI_ACCESSED, etc.)
            description: Human-readable description (PHI-safe)
            tenant_id: Tenant identifier (required)
            project_id: Project identifier (required)
            resource_type: Type of resource affected (Transcript, PHI, etc.)
            resource_id: ID of the affected resource
            user_id: ID of user who triggered the event
            user_ip: IP address of the user (if available)
            metadata: Additional context (PHI-safe keys only)

        Returns:
            The created AuditEvent
        """
        # Validate and filter metadata
        safe_metadata = self._validate_metadata(metadata or {})

        event = AuditEvent(
            event_type=event_type,
            description=description,
            tenant_id=tenant_id,
            project_id=project_id,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            user_ip=user_ip,
            metadata=safe_metadata,
        )

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get last hash atomically (FOR UPDATE locks the row)
                previous_hash = self._get_last_event_hash(cursor)
                
                # Build event data for hashing (excludes hash fields)
                event_data = {
                    "id": event.id,
                    "tenant_id": event.tenant_id,
                    "project_id": event.project_id,
                    "event_type": event.event_type.value,
                    "description": event.description,
                    "resource_type": event.resource_type,
                    "resource_id": event.resource_id,
                    "user_id": event.user_id,
                    "user_ip": event.user_ip,
                    "timestamp": event.timestamp.isoformat(),
                    "metadata": event.metadata,
                }
                
                # Compute hash chain
                event_hash = self._compute_event_hash(event_data, previous_hash)
                
                # Insert with hash chain
                cursor.execute(
                    """
                    INSERT INTO audit_events 
                    (id, tenant_id, project_id, event_type, description, 
                     resource_type, resource_id, user_id, user_ip, 
                     timestamp, metadata, previous_hash, event_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event.id,
                        event.tenant_id,
                        event.project_id,
                        event.event_type.value,
                        event.description,
                        event.resource_type,
                        event.resource_id,
                        event.user_id,
                        event.user_ip,
                        event.timestamp,
                        Jsonb(event.metadata),
                        previous_hash,
                        event_hash,
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
        tenant_id: str,
        project_id: str,
        event_type: Optional[AuditEventType] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Query audit events for a tenant/project.

        Args:
            tenant_id: Filter by tenant (required)
            project_id: Filter by project (required)
            event_type: Filter by event type
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            limit: Maximum number of events to return

        Returns:
            List of matching audit events
        """
        query = """
            SELECT id, tenant_id, project_id, event_type, description, 
                   resource_type, resource_id, user_id, user_ip, 
                   timestamp, metadata, previous_hash, event_hash
            FROM audit_events 
            WHERE tenant_id = %s AND project_id = %s
        """
        params: list[Any] = [tenant_id, project_id]

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
                        "tenant_id": row[1],
                        "project_id": row[2],
                        "event_type": row[3],
                        "description": row[4],
                        "resource_type": row[5],
                        "resource_id": row[6],
                        "user_id": row[7],
                        "user_ip": row[8],
                        "timestamp": row[9].isoformat() if row[9] else None,
                        "metadata": row[10],
                        "previous_hash": row[11],
                        "event_hash": row[12],
                    })
                return results
                
        except Exception as e:
            logger.error(f"Failed to query audit logs: {e}")
            return []

    async def verify_chain_integrity(
        self,
        tenant_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> tuple[bool, list[str]]:
        """
        Verify the hash chain integrity of audit events.
        
        Returns:
            Tuple of (is_valid, list of error messages)
        """
        query = """
            SELECT id, tenant_id, project_id, event_type, description,
                   resource_type, resource_id, user_id, user_ip,
                   timestamp, metadata, previous_hash, event_hash
            FROM audit_events
        """
        params: list[Any] = []
        conditions = []
        
        if tenant_id:
            conditions.append("tenant_id = %s")
            params.append(tenant_id)
        if project_id:
            conditions.append("project_id = %s")
            params.append(project_id)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY sequence_number ASC"
        
        errors: list[str] = []
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
                
                expected_previous_hash: str | None = None
                
                for row in rows:
                    event_id = row[0]
                    stored_previous_hash = row[11]
                    stored_event_hash = row[12]
                    
                    # Check previous_hash links correctly
                    if stored_previous_hash != expected_previous_hash:
                        errors.append(
                            f"Event {event_id}: previous_hash mismatch. "
                            f"Expected '{expected_previous_hash}', got '{stored_previous_hash}'"
                        )
                    
                    # Recompute event_hash
                    event_data = {
                        "id": row[0],
                        "tenant_id": row[1],
                        "project_id": row[2],
                        "event_type": row[3],
                        "description": row[4],
                        "resource_type": row[5],
                        "resource_id": row[6],
                        "user_id": row[7],
                        "user_ip": row[8],
                        "timestamp": row[9].isoformat() if row[9] else None,
                        "metadata": row[10],
                    }
                    computed_hash = self._compute_event_hash(event_data, stored_previous_hash)
                    
                    if computed_hash != stored_event_hash:
                        errors.append(
                            f"Event {event_id}: event_hash mismatch. "
                            f"Computed '{computed_hash}', stored '{stored_event_hash}'"
                        )
                    
                    expected_previous_hash = stored_event_hash
                
                return len(errors) == 0, errors
                
        except Exception as e:
            logger.error(f"Failed to verify audit chain: {e}")
            return False, [f"Verification failed: {e}"]
