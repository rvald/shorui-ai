"""
Compliance module routes.

This module provides the API endpoints for the compliance module, including:
- Clinical transcript upload and analysis
- Audit log querying
- HIPAA regulation statistics
"""

from __future__ import annotations
import uuid
from typing import Union

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from loguru import logger

from app.compliance.factory import get_audit_logger
from app.compliance.schemas import (
    AuditLogResponse,
    ComplianceReportResponse,
    RegulationCollectionStats,
    TranscriptJobResponse,
    TranscriptJobStatus,
    TranscriptUploadResponse,
)
from app.compliance.services.hipaa_regulation_service import HIPAARegulationService
from app.compliance.services.report_repository import get_report_repository
from app.ingestion.services.job_ledger import JobLedgerService
from app.workers.transcript_tasks import analyze_clinical_transcript
from shorui_core.domain.hipaa_schemas import AuditEventType

router = APIRouter(tags=["compliance"])


# ==============================================================================
# CLINICAL TRANSCRIPTS ENDPOINTS
# ==============================================================================


@router.post(
    "/clinical-transcripts",
    response_model=Union[TranscriptUploadResponse, TranscriptJobResponse],
    summary="Upload and analyze clinical transcript",
)
async def upload_clinical_transcript(
    file: UploadFile = File(...),
    project_id: str = Query("default", description="Project ID"),
    background_tasks: BackgroundTasks = None,
    use_async: bool = Query(True, description="Process asynchronously via Celery"),
):
    """
    Upload a clinical transcript for HIPAA compliance analysis.

    Performs:
    1. PHI detection (Presidio)
    2. Compliance analysis (LLM)
    3. Graph ingestion (Pointer-based)
    4. Audit logging

    If use_async=True (default), returns a job_id for tracking.
    """
    try:
        content = await file.read()
        text = content.decode("utf-8")
        filename = file.filename or "unknown.txt"
        # project_id from query param
        job_id = str(uuid.uuid4())

        logger.info(
            f"Received transcript upload: {filename} ({len(text)} chars), async={use_async}"
        )

        if use_async:
            # Trigger Celery task
            task = analyze_clinical_transcript.delay(
                job_id=job_id,
                text=text,
                filename=filename,
                project_id=project_id,
            )
            return TranscriptJobResponse(
                job_id=job_id,
                status="pending",
                message="Transcript analysis started in background",
            )
        else:
            # Run synchronously (blocking) - only for small files/testing
            # We call the async implementation directly
            from app.workers.transcript_tasks import _analyze_transcript_async

            result = await _analyze_transcript_async(
                job_id, text, filename, project_id
            )

            if result.get("status") == "failed":
                raise HTTPException(status_code=500, detail=result.get("error"))

            return TranscriptUploadResponse(
                transcript_id=result.get("transcript_id"),
                filename=filename,
                phi_detected=result.get("phi_detected", 0),
                processing_time_ms=result.get("processing_time_ms", 0),
                message="Analysis complete",
                compliance_report=result.get("compliance_report"),
            )

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/clinical-transcripts/job/{job_id}",
    response_model=TranscriptJobStatus,
    summary="Get transcript analysis job status",
)
async def get_transcript_job_status(job_id: str):
    """Get the status of an async transcript analysis job."""
    ledger = JobLedgerService()
    job = ledger.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Extract transcript_id and report_id from result_artifacts if available
    transcript_id = None
    report_id = None
    result_artifacts = job.get("result_artifacts")
    if result_artifacts:
        # Handle both list format (from decorator) and dict format
        if isinstance(result_artifacts, list) and len(result_artifacts) > 0:
            result_artifacts = result_artifacts[0]
        if isinstance(result_artifacts, dict):
            transcript_id = result_artifacts.get("transcript_id")
            report_id = result_artifacts.get("report_id")

    result = None
    if job["status"] == "completed":
        result = TranscriptUploadResponse(
            transcript_id=transcript_id or "unknown",
            filename=job.get("document_type") or "transcript",
            phi_detected=job.get("items_indexed", 0),
            processing_time_ms=0,
            message="Job completed",
        )

    return TranscriptJobStatus(
        job_id=job_id,
        status=job["status"],
        transcript_id=transcript_id,
        report_id=report_id,
        result=result,
        error=job.get("error"),
    )


@router.get(
    "/clinical-transcripts/{transcript_id}/report",
    response_model=ComplianceReportResponse,
    summary="Get compliance report",
)
async def get_compliance_report_endpoint(transcript_id: str):
    """
    Get the generated compliance report for a transcript.
    
    Returns the persisted compliance report with risk assessment,
    PHI counts, findings, and recommendations. Does not include raw PHI.
    """
    repo = get_report_repository()
    report = repo.get_by_transcript_id(transcript_id)

    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No compliance report found for transcript {transcript_id}"
        )

    # Build response from stored data
    report_json = report.get("report_json", {})
    sections = report_json.get("sections", [])
    
    generated_at = report.get("generated_at")
    if hasattr(generated_at, "isoformat"):
        generated_at = generated_at.isoformat()
    else:
        generated_at = str(generated_at) if generated_at else ""

    return ComplianceReportResponse(
        report_id=report["report_id"],
        transcript_id=report["transcript_id"],
        overall_risk_level=report["overall_risk_level"] or "UNKNOWN",
        total_phi_detected=report["total_phi_detected"] or 0,
        total_violations=report["total_violations"] or 0,
        sections=sections,
        generated_at=generated_at,
    )


# ==============================================================================
# AUDIT LOG ENDPOINTS
# ==============================================================================


@router.get(
    "/audit-log",
    response_model=AuditLogResponse,
    summary="Query HIPAA audit entry logs",
)
async def query_audit_log(
    event_type: AuditEventType | None = None,
    limit: int = 100,
):
    """
    Query the HIPAA audit trail.

    Returns a list of tamper-evident audit events handling PHI access/detection.
    """
    audit_logger = get_audit_logger()
    events = await audit_logger.query_events(event_type=event_type, limit=limit)

    return AuditLogResponse(
        events=events,
        total=len(events),
    )


# ==============================================================================
# HIPAA REGULATIONS ENDPOINTS
# ==============================================================================


@router.get(
    "/hipaa-regulations/stats",
    response_model=RegulationCollectionStats,
    summary="Get HIPAA regulation collection stats",
)
async def get_regulation_stats():
    """
    Get statistics about the HIPAA regulations collection.

    Returns:
        RegulationCollectionStats: Collection statistics
    """
    # Direct service usage (admin/setup feature)
    service = HIPAARegulationService()
    stats = service.get_collection_stats()

    return RegulationCollectionStats(
        exists=stats.get("exists", False),
        points_count=stats.get("points_count", 0),
        message="HIPAA regulations collection ready"
        if stats.get("exists")
        else "Collection not initialized",
    )
