"""
Ingestion API routes for the unified application.

This module provides endpoints for document ingestion:
- Upload documents for processing
- Check processing status
- Configure indexing options
"""

import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel

from app.workers.tasks import process_document
from app.workers.transcript_tasks import analyze_clinical_transcript

router = APIRouter()

class JobStatus(BaseModel):
    """Response model for job status."""

    job_id: str
    status: str
    progress: int | None = None
    error: str | None = None
    result: dict | None = None


class UploadResponse(BaseModel):
    """Response model for document upload."""

    job_id: str
    message: str


@router.get("/health")
def ingestion_health():
    """Health check for the ingestion module."""
    return {"status": "ok", "module": "ingestion"}


@router.post("/documents", response_model=UploadResponse, status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    document_type: str = Form(default="general"),  # "general", "hipaa_regulation"
    index_to_vector: bool = Form(default=True),
    index_to_graph: bool = Form(default=False),
    # Optional fields for hipaa_regulation type
    source: str | None = Form(default=None),  # e.g., "45 CFR 164.514"
    title: str | None = Form(default=None),
    category: str | None = Form(default=None),  # privacy_rule, security_rule, etc.
):
    """
    Upload a document for processing.

    The document will be processed asynchronously via Celery.
    Use the returned job_id to check the processing status.

    Args:
        file: The document file to upload.
        project_id: Project identifier for multi-tenancy.
        document_type: Type of document - "general" or "hipaa_regulation".
        index_to_vector: Whether to index to vector database (default: True).
        index_to_graph: Whether to index to graph database (default: False).
        source: For regulations - source identifier (e.g., "45 CFR 164.514").
        title: For regulations - human-readable title.
        category: For regulations - category (privacy_rule, security_rule, etc.).

    Returns:
        UploadResponse: Contains job_id for tracking.
    """
    # Generate a unique job ID
    job_id = str(uuid.uuid4())

    # Read file content
    file_content = await file.read()
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "unknown"

    logger.info(
        f"Received {document_type} upload: {filename} ({content_type}) for project {project_id}"
    )
 
    import sys
    print(f"DEBUG_PRINT: Processing upload for {filename}", file=sys.stderr)

    try:
        from app.workers.tasks import process_document
        print(f"DEBUG_PRINT: Imported task {process_document.name}", file=sys.stderr)
        print(f"DEBUG_PRINT: Task Broker: {process_document.app.conf.broker_url}", file=sys.stderr)
        
        # Test connection validity
        with process_document.app.connection_for_write() as conn:
            print(f"DEBUG_PRINT: Connection info: {conn.info()}", file=sys.stderr)

    except Exception as e:
        print(f"DEBUG_PRINT: Error exploring task: {e}", file=sys.stderr)

    # Queue task via Celery with document_type for routing
    process_document.delay(
        job_id=job_id,
        file_content=file_content,
        filename=filename,
        content_type=content_type,
        project_id=project_id,
        document_type=document_type,
        index_to_vector=index_to_vector,
        index_to_graph=index_to_graph,
        # Regulation-specific metadata
        source=source,
        title=title,
        category=category,
    )

    logger.info(f"[{job_id}] Queued {document_type} processing via Celery")

    return UploadResponse(job_id=job_id, message=f"Document '{filename}' queued for processing")


@router.get("/documents/{job_id}/status", response_model=JobStatus)
def get_document_status(job_id: str):
    """
    Get the processing status of an uploaded document.

    Queries the PostgreSQL job ledger for job status.

    Args:
        job_id: The job ID returned from the upload endpoint.

    Returns:
        JobStatus: Current status of the processing job.

    Raises:
        HTTPException: 404 if job_id is not found.
    """
    from app.ingestion.services.job_ledger import JobLedgerService

    try:
        ledger_service = JobLedgerService()
        job_info = ledger_service.get_job(job_id)

        if job_info:
            return JobStatus(
                job_id=job_info["job_id"],
                status=job_info["status"],
                progress=job_info.get("progress"),
                error=job_info.get("error"),
                result={
                    "items_indexed": job_info.get("items_indexed"),
                    "storage_path": job_info.get("storage_path"),
                }
                if job_info.get("items_indexed")
                else None,
            )
        else:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to fetch job from ledger: {e}")
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


# ==============================================================================
# HIPAA COMPLIANCE ENDPOINTS
# ==============================================================================

from typing import Any


class TranscriptUploadResponse(BaseModel):
    """Response model for clinical transcript upload."""

    transcript_id: str
    filename: str
    phi_detected: int
    processing_time_ms: int
    message: str
    compliance_report: Optional["ComplianceReportResponse"] = None


class ComplianceReportResponse(BaseModel):
    """Response model for compliance report."""

    report_id: str
    transcript_id: str
    overall_risk_level: str
    total_phi_detected: int
    total_violations: int
    sections: list[dict[str, Any]]
    generated_at: str


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


# ============================================================
# Clinical Transcript Processing (PHI Detection + Compliance)
# ============================================================


@router.post("/clinical-transcripts", response_model=TranscriptJobResponse, status_code=202)
async def upload_clinical_transcript(
    file: UploadFile = File(...),
    project_id: str = Form(...),
):
    """
    Upload a clinical transcript for HIPAA compliance analysis.

    Returns immediately with a job_id. Use GET /clinical-transcripts/jobs/{job_id}
    to poll for status and retrieve the compliance report when complete.

    Recommended for:
    - Large transcripts (>10KB)
    - Batch processing
    - Production deployments

    Args:
        file: The clinical transcript file (.txt)
        project_id: Project identifier for multi-tenancy

    Returns:
        TranscriptJobResponse: Contains job_id for polling
    """
    # Read file content
    file_content = await file.read()
    text = file_content.decode("utf-8")
    filename = file.filename or "unknown.txt"

    # Queue Celery task - use apply_async to set task_id, which becomes our job_id
    job_id = str(uuid.uuid4())
    
    analyze_clinical_transcript.apply_async(
        kwargs={
            "job_id": job_id,
            "text": text,
            "filename": filename,
            "project_id": project_id,
        },
        task_id=job_id,  # Use job_id as Celery task_id for polling
    )

    logger.info(f"[{job_id}] Queued transcript analysis via Celery")

    return TranscriptJobResponse(
        job_id=job_id,
        status="pending",
        message="Transcript queued for analysis. Poll /clinical-transcripts/jobs/{job_id} for status.",
    )


@router.get("/clinical-transcripts/jobs/{job_id}", response_model=TranscriptJobStatus)
async def get_transcript_job_status(job_id: str):
    """
    Get status of an async transcript analysis job.

    Poll this endpoint to check if analysis is complete.
    When status is 'completed', the result field contains the full compliance report.

    Args:
        job_id: The job ID returned from POST /clinical-transcripts/async

    Returns:
        TranscriptJobStatus: Current job status and result if complete
    """
    from celery.result import AsyncResult

    # Check Celery task status
    task_result = AsyncResult(job_id, app=analyze_clinical_transcript.app)

    if task_result.ready():
        if task_result.successful():
            result_data = task_result.result

            if result_data.get("status") == "completed":
                # Build response matching TranscriptUploadResponse
                compliance_report = None
                if result_data.get("compliance_report"):
                    compliance_report = ComplianceReportResponse(**result_data["compliance_report"])

                return TranscriptJobStatus(
                    job_id=job_id,
                    status="completed",
                    result=TranscriptUploadResponse(
                        transcript_id=result_data.get("transcript_id", "unknown"),
                        filename=result_data.get("filename", "unknown"),
                        phi_detected=result_data.get("phi_detected", 0),
                        processing_time_ms=result_data.get("processing_time_ms", 0),
                        message="Transcript analyzed successfully.",
                        compliance_report=compliance_report,
                    ),
                )
            else:
                return TranscriptJobStatus(
                    job_id=job_id,
                    status="failed",
                    error=result_data.get("error", "Unknown error"),
                )
        else:
            # Task failed
            return TranscriptJobStatus(
                job_id=job_id,
                status="failed",
                error=str(task_result.result) if task_result.result else "Task failed",
            )
    else:
        # Still processing
        state = task_result.state
        if state == "PENDING":
            status = "pending"
        elif state == "STARTED":
            status = "processing"
        else:
            status = "processing"

        return TranscriptJobStatus(
            job_id=job_id,
            status=status,
        )


# ============================================================
# Clinical Transcript Compliance Report Retrieval
# ============================================================


@router.get(
    "/clinical-transcripts/{transcript_id}/compliance-report",
    response_model=ComplianceReportResponse,
)
async def get_compliance_report(transcript_id: str, project_id: str):
    """
    Get HIPAA compliance report for a transcript.

    Generates a compliance report with:
    - PHI detection summary
    - Risk assessment
    - Remediation recommendations

    Args:
        transcript_id: ID of the analyzed transcript
        project_id: Project identifier

    Returns:
        ComplianceReportResponse: Full compliance report
    """
    import os
    import sys

    from app.compliance.services.compliance_report_service import ComplianceReportService

    from shorui_core.domain.hipaa_schemas import PHIExtractionResult

    # In a full implementation, we'd fetch the extraction result from storage
    # For now, generate a minimal report
    report_service = ComplianceReportService()

    # Create placeholder extraction result (in production, fetch from DB)
    extraction_result = PHIExtractionResult(
        transcript_id=transcript_id,
        phi_spans=[],
        processing_time_ms=0,
    )

    report = report_service.generate_report(
        transcript_id=transcript_id,
        extraction_result=extraction_result,
    )

    return ComplianceReportResponse(
        report_id=report.id,
        transcript_id=transcript_id,
        overall_risk_level=report.overall_risk_level,
        total_phi_detected=report.total_phi_detected,
        total_violations=report.total_violations,
        sections=[
            {
                "title": s.title,
                "findings": s.findings,
                "recommendations": s.recommendations,
                "severity": s.severity,
            }
            for s in report.sections
        ],
        generated_at=report.generated_at.isoformat(),
    )


@router.get("/audit-log", response_model=AuditLogResponse)
async def get_audit_log(
    event_type: str | None = None,
    resource_type: str | None = None,
    limit: int = 100,
):
    """
    Query HIPAA audit log (admin only).

    Returns audit events for compliance reporting.

    Args:
        event_type: Filter by event type (e.g., PHI_DETECTED, PHI_ACCESSED)
        resource_type: Filter by resource type (e.g., Transcript, PHI)
        limit: Maximum number of events to return

    Returns:
        AuditLogResponse: List of audit events
    """
    import os
    import sys

    from app.compliance.services.audit_service import AuditService

    from shorui_core.domain.hipaa_schemas import AuditEventType

    audit_service = AuditService()

    # Convert string to enum if provided
    event_type_enum = None
    if event_type:
        try:
            event_type_enum = AuditEventType(event_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid event_type: {event_type}")

    events = await audit_service.query_events(
        event_type=event_type_enum,
        resource_type=resource_type,
        limit=limit,
    )

    return AuditLogResponse(
        events=[
            AuditLogEntry(
                id=e["id"],
                event_type=e["event_type"],
                description=e["description"],
                resource_type=e.get("resource_type"),
                resource_id=e.get("resource_id"),
                timestamp=e["timestamp"],
                user_id=e.get("user_id"),
            )
            for e in events
        ],
        total=len(events),
    )


# ==============================================================================
# HIPAA REGULATION ADMIN ENDPOINTS
# Note: For uploading HIPAA regulations, use POST /documents with document_type="hipaa_regulation"
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


@router.get("/hipaa-regulations/stats", response_model=RegulationCollectionStats)
async def get_regulation_stats():
    """
    Get statistics about the HIPAA regulations collection.

    Returns:
        RegulationCollectionStats: Collection statistics
    """
    from app.compliance.services.hipaa_regulation_service import HIPAARegulationService

    service = HIPAARegulationService()
    stats = service.get_collection_stats()

    return RegulationCollectionStats(
        exists=stats.get("exists", False),
        points_count=stats.get("points_count", 0),
        message="HIPAA regulations collection ready"
        if stats.get("exists")
        else "Collection not initialized",
    )
