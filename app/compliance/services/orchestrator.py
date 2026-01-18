import uuid
from typing import Dict, Any
from loguru import logger

from app.compliance.factory import (
    get_compliance_reporter,
    get_graph_ingestor,
    get_privacy_extraction_service,
)

class ComplianceOrchestrator:
    """
    Orchestrates the HIPAA compliance analysis flow:
    1. PHI Detection (Presidio)
    2. Compliance Reporting (LLM)
    3. Graph Ingestion (Neo4j)
    """

    async def analyze_transcript(
        self,
        job_id: str,
        text: str,
        filename: str,
        project_id: str,
    ) -> Dict[str, Any]:
        """
        Execute the analysis flow.
        """
        logger.info(f"[{job_id}] Orchestrating transcript analysis for {filename}")

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

        return analysis_result

def get_compliance_orchestrator() -> ComplianceOrchestrator:
    return ComplianceOrchestrator()
