import uuid
import hashlib
import inspect
from typing import Dict, Any
from loguru import logger

from app.compliance.factory import (
    get_compliance_reporter,
    get_graph_ingestor,
    get_privacy_extraction_service,
)
from app.compliance.services.transcript_repository import get_transcript_repository
from app.compliance.services.report_repository import get_report_repository
from app.ingestion.services.pipeline import create_document_pipeline, PipelineContext
from app.ingestion.services.storage import get_storage_backend


class ComplianceOrchestrator:
    """
    Orchestrates the HIPAA compliance analysis flow:
    1. PHI Detection (Presidio)
    2. Compliance Reporting (LLM)
    3. Artifact Persistence (Postgres)
    4. Vector Ingestion (Qdrant)
    """

    def __init__(self):
        self.transcript_repo = get_transcript_repository()
        self.report_repo = get_report_repository()
        self.storage = get_storage_backend()

    async def analyze_transcript(
        self,
        job_id: str,
        text: str,
        filename: str,
        project_id: str,
        tenant_id: str = "default",
    ) -> Dict[str, Any]:
        """
        Execute the analysis flow with persistence.
        
        Returns dict with transcript_id, report_id, and analysis results.
        """
        logger.info(f"[{job_id}] Orchestrating transcript analysis")

        # Generate IDs upfront
        transcript_id = str(uuid.uuid4())
        report_id = None
        
        # Compute content hash for deduplication
        content_bytes = text.encode("utf-8")
        file_hash = hashlib.sha256(content_bytes).hexdigest()

        # 0. Persist transcript to storage and create record
        try:
            storage_pointer = self.storage.upload(
                content=content_bytes,
                filename=filename,
                tenant_id=tenant_id,
                project_id=project_id,
                bucket=self.storage.raw_bucket,
                prefix="transcripts",
            )
            
            self.transcript_repo.create(
                tenant_id=tenant_id,
                project_id=project_id,
                filename=filename,
                storage_pointer=storage_pointer,
                byte_size=len(content_bytes),
                text_length=len(text),
                file_hash=file_hash,
                job_id=job_id,
                transcript_id=transcript_id,
            )
            logger.info(f"[{job_id}] Persisted transcript {transcript_id}")
        except Exception as e:
            logger.error(f"[{job_id}] Failed to persist transcript: {e}")
            # Continue with in-memory processing even if persistence fails

        # 1. PHI detection and compliance analysis
        logger.info(f"[{job_id}] Starting PHI detection and LLM analysis")
        extraction_service = get_privacy_extraction_service()
        result = await extraction_service.extract(
            text,
            transcript_id=transcript_id,
            filename=filename,
            project_id=project_id,
            skip_llm=False,
        )
        # Use the transcript_id from extraction if provided
        transcript_id = result.transcript_id or transcript_id

        logger.info(f"[{job_id}] Detected {len(result.phi_spans)} PHI spans")

        # 2. Generate and persist Compliance Report
        report_data = None
        try:
            report_service = get_compliance_reporter()
            report = report_service.generate_report(
                transcript_id=result.transcript_id, extraction_result=result
            )

            # Persist to database
            report_id = self.report_repo.create(
                tenant_id=tenant_id,
                project_id=project_id,
                transcript_id=transcript_id,
                report=report,
                job_id=job_id,
            )
            logger.info(f"[{job_id}] Persisted compliance report {report_id}")

            report_data = {
                "report_id": report_id,
                "transcript_id": transcript_id,
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
            logger.warning(f"[{job_id}] Failed to generate/persist compliance report: {e}")

        # 3. Vector Ingestion (Redacted Text)
        try:
            logger.info(f"[{job_id}] Starting vector ingestion for RAG (Redacted)")
            
            # Redact PHI
            maybe_redacted = extraction_service.redact_text(text, result.phi_spans)
            redacted_text = (
                await maybe_redacted if inspect.isawaitable(maybe_redacted) else maybe_redacted
            )
            
            # Run ingestion pipeline
            # Note: We use project_{project_id} as the collection name
            collection_name = f"project_{project_id}"
            pipeline = create_document_pipeline(collection_name=collection_name)
            
            ctx = PipelineContext(
                text=redacted_text,
                filename=filename,
                metadata={
                    "project_id": project_id,
                    "job_id": job_id,
                    "transcript_id": transcript_id,
                    "source": "compliance_orchestrator",
                    "is_redacted": True,
                    "original_phi_count": len(result.phi_spans)
                }
            )
            
            ctx = pipeline.run(ctx)
            logger.info(
                f"[{job_id}] Vector ingestion complete (Collection: {collection_name}, Chunks: {ctx.result.get('chunks_indexed', 0)})"
            )
            
        except Exception as e:
            logger.error(f"[{job_id}] Vector ingestion failed: {e}")

        # Build result with stable IDs
        analysis_result = {
            "status": "completed",
            "job_id": job_id,
            "transcript_id": transcript_id,
            "report_id": report_id,
            "filename": filename,
            "phi_detected": len(result.phi_spans),
            "processing_time_ms": result.processing_time_ms,
            "compliance_report": report_data,
        }

        return analysis_result


def get_compliance_orchestrator() -> ComplianceOrchestrator:
    return ComplianceOrchestrator()

