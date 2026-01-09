"""
Audit Service

Provides HIPAA-compliant audit logging and querying capabilities.
Stores audit events in PostgreSQL for tamper-evident logging.
"""

from datetime import datetime
from typing import Any, Optional

from loguru import logger

from shorui_core.domain.hipaa_schemas import AuditEvent, AuditEventType


class AuditService:
    """
    HIPAA audit logging and query service.
    
    Provides:
    - Logging of PHI access, detection, and compliance events
    - Querying of audit trail for compliance reporting
    - Tamper-evident storage (PostgreSQL with sequence numbers)
    
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
        # In production, this would connect to PostgreSQL
        self._events: list[dict] = []  # In-memory for now
        logger.debug("AuditService initialized")
    
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
        
        # Store event (in production, this goes to PostgreSQL)
        event_dict = {
            "id": event.id,
            "event_type": event.event_type.value,
            "description": event.description,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "user_id": event.user_id,
            "timestamp": event.timestamp.isoformat(),
            "metadata": event.metadata,
        }
        self._events.append(event_dict)
        
        logger.debug(f"Audit log: {event_type.value} - {description}")
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
        # In production, this would query PostgreSQL
        # For now, filter in-memory events
        results = []
        
        for event in reversed(self._events):  # Most recent first
            if event_type and event["event_type"] != event_type.value:
                continue
            if resource_type and event.get("resource_type") != resource_type:
                continue
            if resource_id and event.get("resource_id") != resource_id:
                continue
            
            results.append(event)
            
            if len(results) >= limit:
                break
        
        return results
