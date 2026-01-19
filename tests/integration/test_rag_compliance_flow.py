"""
Integration test for RAG and Compliance workflow.
Verifies that:
1. ComplianceOrchestrator ingests transcripts into Neo4j (Graph).
2. ComplianceOrchestrator redacts PHI and indexes text into Qdrant (Vector).
3. RAG Retriever uses the correct collection to find the data.
"""

from unittest.mock import MagicMock, patch, AsyncMock, ANY
import pytest

from app.compliance.services.orchestrator import ComplianceOrchestrator
from shorui_core.domain.hipaa_schemas import PHIExtractionResult, PHISpan, PHICategory

@pytest.fixture
def mock_dependencies():
    """Mock external services for orchestrator."""
    with patch("app.compliance.services.orchestrator.get_privacy_extraction_service") as mock_extract, \
         patch("app.compliance.services.orchestrator.get_compliance_reporter") as mock_report, \
         patch("app.compliance.services.orchestrator.get_graph_ingestor") as mock_graph, \
         patch("app.compliance.services.orchestrator.create_document_pipeline") as mock_pipeline_factory:

        # Setup Extraction Service
        extract_svc = AsyncMock()
        mock_extract.return_value = extract_svc
        
        # Setup real redaction logic (important for this test)
        from app.compliance.services.privacy_extraction import PrivacyAwareExtractionService
        extract_svc.redact_text.side_effect = PrivacyAwareExtractionService.redact_text

        # Setup Reporter
        report_svc = MagicMock()
        mock_report.return_value = report_svc
        report = MagicMock()
        report.id = "report-123"
        report.transcript_ids = ["txn-123"]
        report_svc.generate_report.return_value = report

        # Setup Graph Ingestor
        graph_svc = AsyncMock()
        mock_graph.return_value = graph_svc

        # Setup Qdrant Pipeline
        pipeline_instance = MagicMock()
        pipeline_instance.run.side_effect = lambda ctx: ctx
        mock_pipeline_factory.return_value = pipeline_instance

        yield {
            "extract_svc": extract_svc,
            "report_svc": report_svc,
            "graph_svc": graph_svc,
            "pipeline_factory": mock_pipeline_factory,
            "pipeline": pipeline_instance
        }


@pytest.mark.asyncio
async def test_compliance_orchestrator_indexes_redacted_text(mock_dependencies):
    """
    Test that analyze_transcript:
    1. Detects PHI
    2. Redacts text
    3. Triggers vector ingestion with redacted text (Qdrant pipeline)
    """
    orchestrator = ComplianceOrchestrator()
    deps = mock_dependencies
    
    # Input data
    original_text = "Patient John Doe has severe diabetes."
    project_id = "test-project"
    job_id = "job-123"
    
    # Mock PHI detection result
    phi_spans = [
        PHISpan(
            id="span-1",
            category=PHICategory.NAME,
            confidence=0.9,
            start_char=8,
            end_char=16,
            detector="presidio",
        ),
    ]
    deps["extract_svc"].extract.return_value = PHIExtractionResult(
        transcript_id="txn-123",
        phi_spans=phi_spans,
        processing_time_ms=100,
    )

    # ACTION
    result = await orchestrator.analyze_transcript(
        job_id=job_id,
        text=original_text,
        filename="medical_record.txt",
        project_id=project_id
    )

    # VERIFICATION
    
    # 0. Verify extraction call includes transcript_id
    deps["extract_svc"].extract.assert_called_once_with(
        original_text, transcript_id=ANY, skip_llm=False
    )

    # 1. Verify Redaction Call
    deps["extract_svc"].redact_text.assert_called_once()
    
    # 2. Verify Pipeline Creation
    # Should use project-specific collection name
    deps["pipeline_factory"].assert_called_once_with(
        collection_name=f"project_{project_id}"
    )
    
    # 3. Verify Pipeline Execution with Redacted Text
    pipeline = deps["pipeline"]
    pipeline.run.assert_called_once()
    
    # Check the context passed to run()
    ctx = pipeline.run.call_args[0][0]
    assert ctx.text == "Patient [NAME] has severe diabetes."
    assert ctx.metadata["project_id"] == project_id
    assert ctx.metadata["is_redacted"] is True
    
    # 4. Verify Graph Ingestion (still happens)
    deps["graph_svc"].ingest_transcript.assert_called_once()
