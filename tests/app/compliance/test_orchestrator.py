import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from app.compliance.services.orchestrator import ComplianceOrchestrator

@pytest.fixture
def mock_privacy_service():
    with patch("app.compliance.services.orchestrator.get_privacy_extraction_service") as factory_mock:
        service_mock = AsyncMock()
        factory_mock.return_value = service_mock
        yield service_mock

@pytest.fixture
def mock_report_service():
    with patch("app.compliance.services.orchestrator.get_compliance_reporter") as factory_mock:
        service_mock = MagicMock()
        factory_mock.return_value = service_mock
        yield service_mock

@pytest.fixture
def mock_graph_service():
    with patch("app.compliance.services.orchestrator.get_graph_ingestor") as factory_mock:
        service_mock = AsyncMock()
        factory_mock.return_value = service_mock
        yield service_mock

@pytest.mark.asyncio
async def test_analyze_transcript_flow(mock_privacy_service, mock_report_service, mock_graph_service):
    # Setup Mocks
    mock_privacy_result = MagicMock()
    mock_privacy_result.phi_spans = ["span1", "span2"]
    mock_privacy_result.transcript_id = "trans-123"
    mock_privacy_result.processing_time_ms = 100
    mock_privacy_service.extract.return_value = mock_privacy_result

    mock_report = MagicMock()
    mock_report.id = "rep-1"
    mock_report.transcript_ids = ["trans-123"]
    mock_report.overall_risk_level = "HIGH"
    mock_report.total_phi_detected = 2
    mock_report.total_violations = 1
    mock_report.sections = []
    from datetime import datetime
    mock_report.generated_at = datetime.now()
    mock_report_service.generate_report.return_value = mock_report
    
    # Run Orchestrator
    orchestrator = ComplianceOrchestrator()
    result = await orchestrator.analyze_transcript(
        job_id="job-1",
        text="Clnical text",
        filename="notes.txt",
        project_id="proj-1"
    )
    
    # Verify PHI Extraction
    mock_privacy_service.extract.assert_called_once_with("Clnical text", skip_llm=False)
    
    # Verify Report Generation
    mock_report_service.generate_report.assert_called_once_with(
        transcript_id="trans-123", extraction_result=mock_privacy_result
    )
    
    # Verify Graph Ingestion
    mock_graph_service.ingest_transcript.assert_called_once_with(
        text="Clnical text",
        extraction_result=mock_privacy_result,
        filename="notes.txt",
        project_id="proj-1"
    )
    
    # Verify Result
    assert result["status"] == "completed"
    assert result["job_id"] == "job-1"
    assert result["transcript_id"] == "trans-123"
    assert result["phi_detected"] == 2
    assert result["compliance_report"]["overall_risk_level"] == "HIGH"
