"""
Pydantic schemas for the compliance module.

This module contains request/response models for HIPAA compliance and regulation services.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


# ==============================================================================
# HIPAA COMPLIANCE SCHEMAS
# ==============================================================================


class ComplianceReportResponse(BaseModel):
    """Response model for compliance report."""

    report_id: str
    transcript_id: str
    overall_risk_level: str
    total_phi_detected: int
    total_violations: int
    sections: list[dict[str, Any]]
    generated_at: str


class TranscriptUploadResponse(BaseModel):
    """Response model for clinical transcript upload."""

    transcript_id: str
    filename: str
    phi_detected: int
    processing_time_ms: int
    message: str
    compliance_report: Optional[ComplianceReportResponse] = None


class AuditLogEntry(BaseModel):
    """Response model for audit log entries."""

    id: str
    event_type: str
    description: str
    resource_type: str | None
    resource_id: str | None
    timestamp: str
    user_id: str | None = None


class AuditLogResponse(BaseModel):
    """Response model for audit log query."""

    events: list[AuditLogEntry]
    total: int


class TranscriptJobResponse(BaseModel):
    """Response model for async transcript analysis."""

    job_id: str
    status: str
    message: str


class TranscriptJobStatus(BaseModel):
    """Response model for transcript job status."""

    job_id: str
    status: str  # pending, processing, completed, failed
    result: TranscriptUploadResponse | None = None
    error: str | None = None


# ==============================================================================
# HIPAA REGULATION SCHEMAS
# ==============================================================================


class RegulationUploadResponse(BaseModel):
    """Response model for regulation upload."""

    source: str
    chunks_created: int
    sections_found: list[str]
    success: bool


class RegulationCollectionStats(BaseModel):
    """Response model for regulation collection stats."""

    exists: bool
    points_count: int = 0
    message: str = ""
