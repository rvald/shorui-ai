"""
HIPAA Domain Schemas for PHI detection and compliance verification.

This module defines the core domain models for HIPAA compliance:
- PHICategory: The 18 Safe Harbor PHI identifiers
- PHISpan: A detected PHI instance with location metadata
- ComplianceVerdict: Regulation mapping and violation assessment
- AuditEvent: Tamper-evident audit trail entry
"""

from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from shorui_core.domain.base.graph import GraphBaseModel


class PHICategory(str, Enum):
    """
    HIPAA Safe Harbor PHI Categories (18 identifiers).

    Under the Safe Harbor method, covered entities must remove these
    18 identifiers to de-identify protected health information.
    """

    # Names
    NAME = "NAME"

    # Geographic data
    GEOGRAPHIC = "GEOGRAPHIC"  # Smaller than state (street, city, zip)

    # Dates
    DATE = "DATE"  # All dates except year for ages > 89

    # Contact information
    PHONE = "PHONE"
    FAX = "FAX"
    EMAIL = "EMAIL"

    # Identification numbers
    SSN = "SSN"
    MRN = "MRN"  # Medical Record Number
    HEALTH_PLAN_ID = "HEALTH_PLAN_ID"
    ACCOUNT_NUMBER = "ACCOUNT_NUMBER"
    LICENSE_NUMBER = "LICENSE_NUMBER"  # Driver's license, professional license
    VEHICLE_ID = "VEHICLE_ID"  # VIN, license plate
    DEVICE_ID = "DEVICE_ID"  # Serial numbers, device identifiers

    # Web/network identifiers
    URL = "URL"
    IP_ADDRESS = "IP_ADDRESS"

    # Biometric identifiers
    BIOMETRIC = "BIOMETRIC"  # Fingerprints, voice prints, retina scans

    # Visual identifiers
    PHOTO = "PHOTO"  # Full-face photos, comparable images

    # Other unique identifiers
    OTHER_UNIQUE_ID = "OTHER_UNIQUE_ID"


class RedactionAction(str, Enum):
    """Actions that can be taken to de-identify PHI."""

    REMOVE = "REMOVE"  # Delete entirely
    MASK = "MASK"  # Replace with [REDACTED] or similar
    GENERALIZE = "GENERALIZE"  # Replace with less specific value (e.g., age range)
    ENCRYPT = "ENCRYPT"  # Store encrypted reference


class PHISpan(BaseModel):
    """
    A detected PHI instance within a document.

    Stores the detection metadata but NOT the actual PHI text.
    Raw text is stored separately in encrypted storage (MinIO)
    and referenced via `storage_pointer`.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Detection metadata
    category: PHICategory
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence score")
    detector: str = Field(description="Which detector found this (presidio, llm, manual)")

    # Location within source document
    start_char: int = Field(ge=0, description="Start character offset in source text")
    end_char: int = Field(gt=0, description="End character offset in source text")

    # Secure storage pointer (actual text stored encrypted in MinIO)
    storage_pointer: str | None = Field(
        None, description="MinIO path to encrypted PHI value (e.g., 'minio://phi-bucket/abc123')"
    )

    # Source linkage
    source_transcript_id: str | None = Field(None, description="ID of parent Transcript")


class Transcript(GraphBaseModel):
    """
    A clinical transcript ingested for compliance analysis.

    This is the primary document node in the HIPAA knowledge graph.
    Contains metadata about the source but NOT the raw PHI text.
    """

    # Document metadata
    filename: str
    file_hash: str = Field(description="SHA-256 hash for integrity verification")
    ingested_at: datetime = Field(default_factory=datetime.utcnow)

    # Storage references
    storage_pointer: str = Field(description="MinIO path to encrypted full text")

    # Processing status
    phi_extraction_complete: bool = False
    compliance_review_complete: bool = False

    # Statistics
    phi_count: int = 0
    violation_count: int = 0

    class Meta:
        database_name = "neo4j"


class PHISpanNode(GraphBaseModel):
    """
    Graph node representing a detected PHI span.

    This node stores ONLY the metadata and a pointer to encrypted storage.
    The actual PHI text is NEVER stored in Neo4j.
    """

    # Detection metadata
    category: str  # PHICategory value
    confidence: float
    detector: str

    # Position in source (for reconstruction)
    start_char: int
    end_char: int

    # Secure pointer - NEVER store actual PHI here
    storage_pointer: str

    # Aggregation key for deduplication (e.g., hash of normalized value)
    value_hash: str | None = None

    class Meta:
        database_name = "neo4j"


class RegulationSection(GraphBaseModel):
    """
    A HIPAA regulation section that can be cited in compliance decisions.

    Pre-populated with common HIPAA regulation references.
    """

    section_id: str  # e.g., "164.502", "164.514"
    title: str
    description: str
    category: str  # e.g., "Privacy Rule", "Security Rule", "Breach Notification"

    class Meta:
        database_name = "neo4j"


class ViolationSeverity(str, Enum):
    """Severity levels for HIPAA violations."""

    LOW = "LOW"  # Minor technical violation
    MEDIUM = "MEDIUM"  # Significant violation, correctable
    HIGH = "HIGH"  # Serious violation, potential patient harm
    CRITICAL = "CRITICAL"  # Willful neglect, immediate action required


class ComplianceDecision(GraphBaseModel):
    """
    A compliance decision linking PHI detection to HIPAA regulations.

    Represents the reasoning about whether a PHI instance
    constitutes a violation and what action should be taken.
    """

    # The decision
    is_violation: bool
    severity: str | None = None  # ViolationSeverity value

    # Reasoning (from LLM or rule engine)
    reasoning: str
    recommended_action: str

    # References
    phi_span_id: str
    regulation_section_id: str | None = None

    # Audit trail
    decided_at: datetime = Field(default_factory=datetime.utcnow)
    decided_by: str = Field(default="system", description="User or system that made decision")

    class Meta:
        database_name = "neo4j"


class AuditEventType(str, Enum):
    """Types of auditable events."""

    PHI_DETECTED = "PHI_DETECTED"
    PHI_ACCESSED = "PHI_ACCESSED"
    PHI_EXPORTED = "PHI_EXPORTED"
    COMPLIANCE_DECISION = "COMPLIANCE_DECISION"
    REPORT_GENERATED = "REPORT_GENERATED"
    USER_LOGIN = "USER_LOGIN"
    # Required events per component_audit_ledger.md
    TRANSCRIPT_UPLOADED = "TRANSCRIPT_UPLOADED"
    DOCUMENT_INGESTED = "DOCUMENT_INGESTED"
    COMPLIANCE_REPORT_GENERATED = "COMPLIANCE_REPORT_GENERATED"


class AuditEvent(BaseModel):
    """
    Tamper-evident audit trail entry.

    Stored in PostgreSQL (not Neo4j) for WORM-style append-only logging.
    This model is for creating events; the table has additional
    integrity fields (sequence number, hash chain).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Tenant scoping (required per component_audit_ledger.md)
    tenant_id: str
    project_id: str

    # What happened
    event_type: AuditEventType
    description: str

    # Who did it
    user_id: str | None = None
    user_ip: str | None = None

    # What was affected
    resource_type: str | None = None  # e.g., "Transcript", "PHISpan"
    resource_id: str | None = None

    # When
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Additional context (PHI-safe keys only)
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Extraction and Compliance Result Models ---


class PHIComplianceAnalysis(BaseModel):
    """LLM analysis of PHI compliance for a single detected span."""

    phi_span_index: int = Field(description="Index of the PHI span being analyzed (0-indexed)")
    is_violation: bool = Field(description="Whether this PHI instance violates HIPAA")
    severity: str | None = Field(None, description="LOW, MEDIUM, HIGH, or CRITICAL")
    reasoning: str = Field(description="Explanation of the compliance decision")
    regulation_citation: str | None = Field(
        None, description="Relevant HIPAA section (e.g., '164.502')"
    )
    recommended_action: str = Field(description="What action should be taken")


class TranscriptComplianceResult(BaseModel):
    """Full compliance analysis result from LLM."""

    overall_assessment: str = Field(description="Summary of compliance status")
    phi_analyses: list[PHIComplianceAnalysis] = Field(default_factory=list)
    requires_immediate_action: bool = Field(default=False)


class PHIExtractionResult(BaseModel):
    """Result from PHI extraction pipeline."""

    transcript_id: str
    phi_spans: list[PHISpan]
    processing_time_ms: int
    detector_versions: dict[str, str] = Field(
        default_factory=dict, description="Versions of detectors used (e.g., {'presidio': '2.2.0'})"
    )
    compliance_analysis: TranscriptComplianceResult | None = Field(
        None, description="RAG-grounded compliance analysis from LLM"
    )


class ComplianceReportSection(BaseModel):
    """A section of a compliance report."""

    title: str
    findings: list[str]
    recommendations: list[str]
    severity: str | None = None


class ComplianceReport(BaseModel):
    """Full compliance report for a transcript or batch."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Summary
    total_phi_detected: int
    total_violations: int
    overall_risk_level: str

    # Detailed sections
    sections: list[ComplianceReportSection]

    # Covered transcripts
    transcript_ids: list[str]
