"""
Tests for PrivacyAwareExtractionService.

Tests the HIPAA-compliant extraction pipeline that combines
Presidio PHI detection with RunPod LLM compliance reasoning.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.compliance.services.privacy_extraction import (
    PrivacyAwareExtractionService,
    compute_phi_hash,
)
from shorui_core.domain.hipaa_schemas import (
    AuditEventType,
    PHICategory,
    PHIComplianceAnalysis,
    TranscriptComplianceResult,
)


class TestPrivacyAwareExtractionServiceInit:
    """Test service initialization."""

    def test_default_init(self):
        """Test default initialization loads from settings."""
        service = PrivacyAwareExtractionService()

        # Model name comes from settings.MODEL_INFERENCE or default
        assert service.model_name is not None
        assert service.phi_detector is not None
        assert service.phi_detector is not None
        # _pending_audit_events removed, checks usage of _audit_service
        assert hasattr(service, "_audit_service")

    def test_custom_model(self):
        """Test with custom model name."""
        service = PrivacyAwareExtractionService(model_name="meta-llama/Llama-3.2-8B-Instruct")
        assert service.model_name == "meta-llama/Llama-3.2-8B-Instruct"

    def test_custom_runpod_url(self):
        """Test with custom RunPod URL."""
        service = PrivacyAwareExtractionService(runpod_base_url="https://test.runpod.ai/v1")
        assert service.runpod_base_url == "https://test.runpod.ai/v1"


class TestPHIDetectionFlow:
    """Test PHI detection without LLM (skip_llm=True)."""

    @pytest.fixture
    def service(self):
        """Create service for testing."""
        return PrivacyAwareExtractionService(phi_confidence_threshold=0.3)

    @pytest.mark.asyncio
    async def test_extract_with_phi(self, service):
        """Test extracting from text with PHI."""
        text = "Patient John Smith can be reached at john@email.com"

        result = await service.extract(text, transcript_id="test-001", skip_llm=True)

        assert result.transcript_id == "test-001"
        assert result.processing_time_ms > 0
        assert len(result.phi_spans) > 0

        # Check we found email
        categories = {span.category for span in result.phi_spans}
        assert PHICategory.EMAIL in categories or PHICategory.NAME in categories

    @pytest.mark.asyncio
    async def test_extract_empty_text(self, service):
        """Test extracting from empty text."""
        result = await service.extract("", transcript_id="empty", skip_llm=True)

        assert result.transcript_id == "empty"
        assert len(result.phi_spans) == 0

    @pytest.mark.asyncio
    async def test_extract_no_phi(self, service):
        """Test extracting from text without obvious PHI."""
        text = "The weather is nice today. Patient reports feeling better."

        result = await service.extract(text, skip_llm=True)

        # May or may not find PHI depending on NLP model
        assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_audit_event_logged(self, service):
        """Test that PHI detection logs audit event via AuditService."""
        text = "Contact john@test.com"

        # Mock the audit service
        service._audit_service = AsyncMock()

        await service.extract(text, transcript_id="audit-test", skip_llm=True)

        # Verify log_event called
        assert service._audit_service.log_event.called
        call_args = service._audit_service.log_event.call_args
        assert call_args.kwargs["event_type"] == AuditEventType.PHI_DETECTED
        assert call_args.kwargs["resource_id"] == "audit-test"


class TestBatchExtraction:
    """Test batch extraction functionality."""

    @pytest.fixture
    def service(self):
        return PrivacyAwareExtractionService(phi_confidence_threshold=0.3)

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

        results = await service.extract_batch(transcripts)

        assert len(results) == 3
        assert results[0].transcript_id == "t1"
        assert results[1].transcript_id == "t2"
        assert results[2].transcript_id == "t3"


class TestLLMComplianceAnalysis:
    """Test LLM compliance analysis (mocked)."""

    @pytest.fixture
    def service(self):
        return PrivacyAwareExtractionService(runpod_base_url="https://mock.runpod.ai/v1")

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

        with patch.object(
            service, "_analyze_compliance", new_callable=AsyncMock, return_value=mock_response
        ) as mock_analyze:
            text = "Patient John Smith visited today"
            result = await service.extract(text, skip_llm=False)

            # Should call LLM since skip_llm=False and we have a runpod_url
            # and PHI was detected
            if len(result.phi_spans) > 0:
                mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_not_called_when_explicitly_disabled(self):
        """Test that LLM is not called when skip_llm=True."""
        service = PrivacyAwareExtractionService(
            runpod_base_url="https://test.runpod.ai/v1",
        )

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


class TestServiceCleanup:
    """Test service cleanup."""

    @pytest.mark.asyncio
    async def test_close_client(self):
        """Test closing the HTTP client."""
        service = PrivacyAwareExtractionService()

        # Create client
        await service._get_client()
        assert service._client is not None

        # Close client
        await service.close()
        assert service._client is None

    @pytest.mark.asyncio
    async def test_get_pending_audit_events_legacy(self):
        """Test that legacy method returns empty list."""
        service = PrivacyAwareExtractionService()
        assert service.get_pending_audit_events() == []
