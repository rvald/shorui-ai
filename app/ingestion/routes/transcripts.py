"""
Clinical transcript processing and compliance routes.

This module handles HIPAA compliance endpoints:
- Upload clinical transcripts for PHI detection
- Check transcript analysis job status
- Get compliance reports
- Query audit logs
"""

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from loguru import logger

from app.ingestion.schemas import (
    AuditLogEntry,
    AuditLogResponse,
    ComplianceReportResponse,
    TranscriptJobResponse,
    TranscriptJobStatus,
    TranscriptUploadResponse,
)
from app.workers.transcript_tasks import analyze_clinical_transcript

router = APIRouter()


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
