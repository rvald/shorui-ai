"""
Compliance module protocols.

This module defines the interfaces for the main components of the compliance
system, allowing for loose coupling and easier testing.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from shorui_core.domain.hipaa_schemas import (
    AuditEvent,
    AuditEventType,
    ComplianceReport,
    PHIExtractionResult,
    PHISpan,
    PHICategory,
)


@runtime_checkable
class PHIDetector(Protocol):
    """Protocol for PHI detection services."""

    def detect(self, text: str, source_transcript_id: str | None = None) -> list[PHISpan]:
        """Detect PHI in text."""
        ...

    def detect_with_text(
        self, text: str, source_transcript_id: str | None = None
    ) -> list[tuple[PHISpan, str]]:
        """Detect PHI and return spans with the matched text."""
        ...

    def get_phi_summary(self, text: str) -> dict:
        """Get a summary of PHI detected in text."""
        ...


@runtime_checkable
class AuditLogger(Protocol):
    """Protocol for audit logging services."""

    async def log(
        self,
        event_type: AuditEventType,
        description: str,
        tenant_id: str,
        project_id: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Log an audit event."""
        ...

    async def query_events(
        self,
        event_type: AuditEventType | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query audit events."""
        ...


@runtime_checkable
class RegulationRetriever(Protocol):
    """Protocol for regulation retrieval services."""

    def retrieve_for_phi_category(
        self,
        category: PHICategory,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Retrieve regulations for a specific PHI category."""
        ...

    def retrieve_for_context(
        self,
        phi_spans: list[PHISpan],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve regulations relevant to a set of PHI spans."""
        ...

    def format_for_prompt(
        self,
        regulations: list[dict[str, Any]],
        max_chars: int = 3000,
    ) -> str:
        """Format regulations for an LLM prompt."""
        ...


@runtime_checkable
class ComplianceReporter(Protocol):
    """Protocol for compliance reporting services."""

    def generate_report(
        self,
        transcript_id: str,
        extraction_result: PHIExtractionResult,
    ) -> ComplianceReport:
        """Generate a compliance report."""
        ...


@runtime_checkable
class GraphIngestor(Protocol):
    """Protocol for graph ingestion services."""

    async def ingest_transcript(
        self,
        text: str,
        extraction_result: PHIExtractionResult,
        filename: str,
        project_id: str,
    ) -> dict[str, Any]:
        """Ingest a transcript into the knowledge graph."""
        ...
