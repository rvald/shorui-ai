"""
Celery task for async clinical transcript analysis.

Moves long-running HIPAA compliance analysis to background workers
to prevent API timeouts on large transcripts.
"""

import asyncio

from loguru import logger

from app.ingestion.services.job_ledger import JobLedgerService
from app.workers.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="app.workers.transcript_tasks.analyze_clinical_transcript",
    max_retries=2,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    time_limit=300,  # 5 minute hard limit
    soft_time_limit=240,  # 4 minute soft limit
)
def analyze_clinical_transcript(
    self,
    job_id: str,
    text: str,
    filename: str,
    project_id: str,
) -> dict:
    """
    Celery task to analyze a clinical transcript for HIPAA compliance.

    Pipeline:
    1. PHI detection using Presidio
    2. LLM compliance analysis with RAG-grounded regulations
    3. Generate compliance report
    4. Store in Neo4j graph (pointer-based)
    5. Log audit event

    Args:
        self: Celery task instance (for retries).
        job_id: Unique job identifier.
        text: Transcript text content.
        filename: Original filename.
        project_id: Project for multi-tenancy.

    Returns:
        dict: Complete analysis result with compliance report.
    """
    logger.info(f"[{job_id}] Starting transcript analysis for {filename}")

    # Initialize ledger for audit trail
    ledger_service = JobLedgerService()

    # Record job start in ledger (for audit/posterity)
    try:
        content_hash = ledger_service.compute_content_hash(text.encode("utf-8"))
        ledger_service.create_job(
            project_id=project_id,
            filename=filename,
            storage_path=f"transcript:{job_id}",  # Virtual path for transcripts
            content_hash=content_hash,
            job_id=job_id,
        )
        ledger_service.update_status(job_id, "processing", progress=10)
    except Exception as e:
        logger.warning(f"[{job_id}] Ledger create failed (continuing): {e}")

    # Run async code in sync context
    result = asyncio.get_event_loop().run_until_complete(
        _analyze_transcript_async(job_id, text, filename, project_id)
    )

    # Record completion/failure in ledger (for audit/posterity)
    try:
        if result.get("status") == "completed":
            ledger_service.complete_job(
                job_id,
                items_indexed=result.get("phi_detected", 0),
            )
        else:
            ledger_service.fail_job(
                job_id,
                error=result.get("error", "Unknown error"),
            )
    except Exception as e:
        logger.warning(f"[{job_id}] Ledger update failed: {e}")

    return result


async def _analyze_transcript_async(
    job_id: str,
    text: str,
    filename: str,
    project_id: str,
) -> dict:
    """Async implementation of transcript analysis."""
    import uuid

    from app.compliance.factory import (
        get_compliance_reporter,
        get_graph_ingestor,
        get_privacy_extraction_service,
    )

    try:
        # 1. PHI detection and compliance analysis
        logger.info(f"[{job_id}] Starting PHI detection and LLM analysis")
        extraction_service = get_privacy_extraction_service()
        result = await extraction_service.extract(text, skip_llm=False)

        logger.info(f"[{job_id}] Detected {len(result.phi_spans)} PHI spans")

        # 2. Generate Compliance Report
        report_data = None
        try:
            report_service = get_compliance_reporter()
            report = report_service.generate_report(
                transcript_id=result.transcript_id, extraction_result=result
            )

            report_data = {
                "report_id": report.id,
                "transcript_id": report.transcript_ids[0]
                if report.transcript_ids
                else "unknown",
                "overall_risk_level": report.overall_risk_level,
                "total_phi_detected": report.total_phi_detected,
                "total_violations": report.total_violations,
                "sections": [
                    {
                        "title": s.title,
                        "findings": s.findings,
                        "recommendations": s.recommendations,
                        "severity": s.severity,
                    }
                    for s in report.sections
                ],
                "generated_at": report.generated_at.isoformat(),
            }
            logger.info(
                f"[{job_id}] Generated compliance report: {report.overall_risk_level}"
            )
        except Exception as e:
            logger.warning(f"[{job_id}] Failed to generate compliance report: {e}")

        # 3. Graph ingestion (pointer-based storage)
        transcript_id = result.transcript_id or str(uuid.uuid4())
        try:
            graph_service = get_graph_ingestor()
            await graph_service.ingest_transcript(
                text=text,
                extraction_result=result,
                filename=filename,
                project_id=project_id,
            )
            logger.info(f"[{job_id}] Graph ingestion complete")
        except Exception as e:
            logger.warning(f"[{job_id}] Graph ingestion failed: {e}")

        # Build result
        analysis_result = {
            "status": "completed",
            "job_id": job_id,
            "transcript_id": transcript_id,
            "filename": filename,
            "phi_detected": len(result.phi_spans),
            "processing_time_ms": result.processing_time_ms,
            "compliance_report": report_data,
        }

        logger.info(f"[{job_id}] Transcript analysis complete")
        return analysis_result

    except Exception as e:
        logger.exception(f"[{job_id}] Transcript analysis failed: {e}")
        return {
            "status": "failed",
            "job_id": job_id,
            "error": str(e),
        }
