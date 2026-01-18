"""
Tests for PrivacyAwareExtractionService.

Tests the HIPAA-compliant extraction pipeline that combines
Presidio PHI detection with OpenAI LLM compliance reasoning.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.compliance.services.privacy_extraction import (
    PrivacyAwareExtractionService,
    compute_phi_hash,
)
from shorui_core.domain.hipaa_schemas import (
    AuditEventType,
    PHICategory,
    PHIComplianceAnalysis,
    PHISpan,
    TranscriptComplianceResult,
)


class TestPrivacyAwareExtractionServiceInit:
    """Test service initialization."""

    def test_init_with_dependencies(self):
        """Test initialization with explicit dependencies."""
        mock_detector = Mock()
        mock_retriever = Mock()
        mock_audit = Mock()

        service = PrivacyAwareExtractionService(
            phi_detector=mock_detector,
            regulation_retriever=mock_retriever,
            audit_logger=mock_audit,
        )

        assert service.phi_detector is mock_detector
        assert service._regulation_retriever is mock_retriever
        assert service._audit_logger is mock_audit


class TestPHIDetectionFlow:
    """Test PHI detection without LLM (skip_llm=True)."""

    @pytest.fixture
    def mock_detector(self):
        detector = Mock()
        detector.detect.return_value = []
        return detector

    @pytest.fixture
    def mock_retriever(self):
        return Mock()

    @pytest.fixture
    def mock_audit(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_detector, mock_retriever, mock_audit):
        """Create service for testing."""
        return PrivacyAwareExtractionService(
            phi_detector=mock_detector,
            regulation_retriever=mock_retriever,
            audit_logger=mock_audit,
        )

    @pytest.mark.asyncio
    async def test_extract_with_phi(self, service, mock_detector):
        """Test extracting from text with PHI."""
        text = "Patient John Smith can be reached at john@email.com"
        
        # Mock detection result
        mock_detector.detect.return_value = [
            PHISpan(
                id="1", 
                category=PHICategory.EMAIL, 
                start_char=37, 
                end_char=51,
                detector="presidio",
                confidence=0.9
            )
        ]

        result = await service.extract(text, transcript_id="test-001", skip_llm=True)

        assert result.transcript_id == "test-001"
        assert result.processing_time_ms >= 0
        assert len(result.phi_spans) == 1
        assert result.phi_spans[0].category == PHICategory.EMAIL

    @pytest.mark.asyncio
    async def test_extract_empty_text(self, service, mock_detector):
        """Test extracting from empty text."""
        result = await service.extract("", transcript_id="empty", skip_llm=True)

        assert result.transcript_id == "empty"
        assert len(result.phi_spans) == 0
        mock_detector.detect.assert_called_with("", source_transcript_id="empty")

    @pytest.mark.asyncio
    async def test_audit_event_logged(self, service, mock_audit, mock_detector):
        """Test that PHI detection logs audit event via AuditService."""
        text = "Contact john@test.com"
        
        await service.extract(text, transcript_id="audit-test", skip_llm=True)

        # Verify log_event called
        assert mock_audit.log.called
        call_args = mock_audit.log.call_args
        assert call_args.kwargs["event_type"] == AuditEventType.PHI_DETECTED
        assert call_args.kwargs["resource_id"] == "audit-test"


class TestBatchExtraction:
    """Test batch extraction functionality."""

    @pytest.fixture
    def service(self):
        return PrivacyAwareExtractionService(
            phi_detector=Mock(),
            regulation_retriever=Mock(),
            audit_logger=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_extract_batch_empty(self, service):
        """Test batch extraction with empty list."""
        results = await service.extract_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_extract_batch_multiple(self, service):
        """Test batch extraction with multiple transcripts."""
        transcripts = [
            {"id": "t1", "text": "Patient John Smith"},
            {"id": "t2", "text": "Email: test@example.com"},
            {"id": "t3", "text": "No PHI here"},
        ]
        
        service.extract = AsyncMock()
        service.extract.side_effect = [
            Mock(transcript_id="t1"),
            Mock(transcript_id="t2"),
            Mock(transcript_id="t3"),
        ]

        results = await service.extract_batch(transcripts)

        assert len(results) == 3
        assert service.extract.call_count == 3


class TestLLMComplianceAnalysis:
    """Test LLM compliance analysis (mocked)."""

    @pytest.fixture
    def service(self):
        return PrivacyAwareExtractionService(
            phi_detector=Mock(),
            regulation_retriever=Mock(),
            audit_logger=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_llm_called_when_phi_found(self, service):
        """Test that LLM is called when PHI is detected (not skipped)."""
        mock_response = TranscriptComplianceResult(
            overall_assessment="Minor compliance concerns",
            phi_analyses=[
                PHIComplianceAnalysis(
                    phi_span_index=0,
                    is_violation=False,
                    reasoning="Name appears in clinical context",
                    recommended_action="No action required",
                )
            ],
            requires_immediate_action=False,
        )
        
        # Mock detector to find PHI
        service.phi_detector.detect.return_value = [
            PHISpan(
                id="1",
                category=PHICategory.NAME,
                start_char=0,
                end_char=10,
                detector="presidio",
                confidence=0.9
            )
        ]

        with patch.object(
            service, "_analyze_compliance", new_callable=AsyncMock, return_value=mock_response
        ) as mock_analyze:
            text = "Patient John Smith visited today"
            result = await service.extract(text, skip_llm=False)

            # Should call LLM since skip_llm=False and PHI was detected
            mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_not_called_when_explicitly_disabled(self, service):
        """Test that LLM is not called when skip_llm=True."""
        # Fix mock to return empty list or valid spans so it doesn't crash on len()
        service.phi_detector.detect.return_value = []
        
        with patch.object(service, "_analyze_compliance", new_callable=AsyncMock) as mock_analyze:
            text = "Patient John Smith"
            await service.extract(text, skip_llm=True)  # Explicitly skip LLM

            # Should not call LLM since skip_llm=True
            mock_analyze.assert_not_called()


class TestComplianceResult:
    """Test TranscriptComplianceResult model."""

    def test_create_compliance_result(self):
        """Test creating a compliance result."""
        result = TranscriptComplianceResult(
            overall_assessment="No violations found",
            phi_analyses=[],
            requires_immediate_action=False,
        )

        assert result.overall_assessment == "No violations found"
        assert len(result.phi_analyses) == 0
        assert not result.requires_immediate_action

    def test_compliance_with_violations(self):
        """Test compliance result with violations."""
        result = TranscriptComplianceResult(
            overall_assessment="Critical violations detected",
            phi_analyses=[
                PHIComplianceAnalysis(
                    phi_span_index=0,
                    is_violation=True,
                    severity="CRITICAL",
                    reasoning="SSN exposed without encryption",
                    regulation_citation="164.502",
                    recommended_action="Immediately encrypt or remove SSN",
                )
            ],
            requires_immediate_action=True,
        )

        assert result.requires_immediate_action
        assert result.phi_analyses[0].severity == "CRITICAL"


class TestPHIHash:
    """Test PHI hash computation for deduplication."""

    def test_compute_hash(self):
        """Test computing PHI hash."""
        hash1 = compute_phi_hash("123-45-6789")
        hash2 = compute_phi_hash("123-45-6789")
        hash3 = compute_phi_hash("987-65-4321")

        # Same input = same hash
        assert hash1 == hash2

        # Different input = different hash
        assert hash1 != hash3

        # Hash is truncated to 16 chars
        assert len(hash1) == 16

    def test_hash_is_deterministic(self):
        """Test that hash is deterministic across calls."""
        text = "John Smith DOB 01/01/1980"

        hashes = [compute_phi_hash(text) for _ in range(10)]
        assert len(set(hashes)) == 1  # All hashes are the same
