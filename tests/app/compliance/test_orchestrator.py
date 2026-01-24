import pytest
from unittest.mock import MagicMock, patch, AsyncMock, ANY

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

@pytest.fixture
def mock_transcript_repo():
    with patch("app.compliance.services.orchestrator.get_transcript_repository") as factory_mock:
        repo_mock = MagicMock()
        factory_mock.return_value = repo_mock
        yield repo_mock

@pytest.fixture
def mock_report_repo():
    with patch("app.compliance.services.orchestrator.get_report_repository") as factory_mock:
        repo_mock = MagicMock()
        repo_mock.create.return_value = "report-uuid-123"
        factory_mock.return_value = repo_mock
        yield repo_mock

@pytest.fixture
def mock_storage():
    with patch("app.compliance.services.orchestrator.get_storage_backend") as factory_mock:
        storage_mock = MagicMock()
        storage_mock.upload.return_value = "raw/tenant/project/uuid_file.txt"
        storage_mock.raw_bucket = "raw"
        factory_mock.return_value = storage_mock
        yield storage_mock

@pytest.fixture
def mock_pipeline():
    with patch("app.compliance.services.orchestrator.create_document_pipeline") as factory_mock:
        pipeline_mock = MagicMock()
        pipeline_mock.run.return_value = MagicMock(result={"chunks_indexed": 5})
        factory_mock.return_value = pipeline_mock
        yield pipeline_mock

@pytest.mark.asyncio
async def test_analyze_transcript_flow(
    mock_privacy_service, 
    mock_report_service, 
    mock_graph_service,
    mock_transcript_repo,
    mock_report_repo,
    mock_storage,
    mock_pipeline,
):
    # Setup Mocks
    mock_privacy_result = MagicMock()
    mock_privacy_result.phi_spans = ["span1", "span2"]
    mock_privacy_result.transcript_id = "trans-123"
    mock_privacy_result.processing_time_ms = 100
    mock_privacy_service.extract.return_value = mock_privacy_result
    mock_privacy_service.redact_text.return_value = "Redacted text"

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
        text="Clinical text",
        filename="notes.txt",
        project_id="proj-1"
    )
    
    # Verify PHI Extraction
    mock_privacy_service.extract.assert_called_once_with(
        "Clinical text", 
        transcript_id=ANY, 
        filename="notes.txt",
        project_id="proj-1",
        skip_llm=False
    )
    
    # Verify Report Generation
    mock_report_service.generate_report.assert_called_once_with(
        transcript_id="trans-123", extraction_result=mock_privacy_result
    )
    
    # Verify Transcript was persisted
    mock_transcript_repo.create.assert_called_once()
    
    # Verify Report was persisted  
    mock_report_repo.create.assert_called_once()
    
    # Verify Result
    assert result["status"] == "completed"
    assert result["job_id"] == "job-1"
    assert result["transcript_id"] == "trans-123"
    assert result["report_id"] == "report-uuid-123"
    assert result["phi_detected"] == 2
    assert result["compliance_report"]["overall_risk_level"] == "HIGH"

