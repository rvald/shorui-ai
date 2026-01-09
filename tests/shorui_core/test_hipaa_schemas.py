"""
Tests for HIPAA domain schemas.

Tests the Pydantic models used for PHI detection, compliance decisions,
and audit trail tracking.
"""

import pytest
from pydantic import ValidationError

from shorui_core.domain.hipaa_schemas import (
    AuditEvent,
    AuditEventType,
    ComplianceDecision,
    PHICategory,
    PHIExtractionResult,
    PHISpan,
    Transcript,
    ViolationSeverity,
)


class TestPHICategory:
    """Test PHICategory enum covers all 18 Safe Harbor identifiers."""

    def test_all_safe_harbor_categories_exist(self):
        """Verify all 18 Safe Harbor PHI categories are defined."""
        expected_categories = [
            "NAME",
            "GEOGRAPHIC",
            "DATE",
            "PHONE",
            "FAX",
            "EMAIL",
            "SSN",
            "MRN",
            "HEALTH_PLAN_ID",
            "ACCOUNT_NUMBER",
            "LICENSE_NUMBER",
            "VEHICLE_ID",
            "DEVICE_ID",
            "URL",
            "IP_ADDRESS",
            "BIOMETRIC",
            "PHOTO",
            "OTHER_UNIQUE_ID",
        ]

        actual_categories = [c.value for c in PHICategory]

        for expected in expected_categories:
            assert expected in actual_categories, f"Missing category: {expected}"

    def test_category_count(self):
        """Verify we have exactly 18 categories."""
        assert len(PHICategory) == 18


class TestPHISpan:
    """Test PHISpan model for detected PHI instances."""

    def test_create_valid_span(self):
        """Test creating a valid PHI span."""
        span = PHISpan(
            category=PHICategory.NAME,
            confidence=0.95,
            detector="presidio",
            start_char=0,
            end_char=10,
        )

        assert span.category == PHICategory.NAME
        assert span.confidence == 0.95
        assert span.detector == "presidio"
        assert span.start_char == 0
        assert span.end_char == 10
        assert span.id is not None  # Auto-generated UUID

    def test_confidence_bounds(self):
        """Test that confidence must be between 0 and 1."""
        # Valid confidence
        span = PHISpan(
            category=PHICategory.EMAIL,
            confidence=0.5,
            detector="test",
            start_char=0,
            end_char=5,
        )
        assert span.confidence == 0.5

        # Invalid: too high
        with pytest.raises(ValidationError):
            PHISpan(
                category=PHICategory.EMAIL,
                confidence=1.5,
                detector="test",
                start_char=0,
                end_char=5,
            )

        # Invalid: negative
        with pytest.raises(ValidationError):
            PHISpan(
                category=PHICategory.EMAIL,
                confidence=-0.1,
                detector="test",
                start_char=0,
                end_char=5,
            )

    def test_char_position_validation(self):
        """Test character position constraints."""
        # Valid positions
        span = PHISpan(
            category=PHICategory.PHONE,
            confidence=0.8,
            detector="test",
            start_char=0,
            end_char=12,
        )
        assert span.start_char == 0
        assert span.end_char == 12

        # Invalid: negative start
        with pytest.raises(ValidationError):
            PHISpan(
                category=PHICategory.PHONE,
                confidence=0.8,
                detector="test",
                start_char=-1,
                end_char=12,
            )

        # Invalid: zero end (must be > 0)
        with pytest.raises(ValidationError):
            PHISpan(
                category=PHICategory.PHONE,
                confidence=0.8,
                detector="test",
                start_char=0,
                end_char=0,
            )

    def test_storage_pointer_optional(self):
        """Test that storage_pointer is optional."""
        span = PHISpan(
            category=PHICategory.SSN,
            confidence=1.0,
            detector="manual",
            start_char=5,
            end_char=16,
        )
        assert span.storage_pointer is None

        span_with_pointer = PHISpan(
            category=PHICategory.SSN,
            confidence=1.0,
            detector="manual",
            start_char=5,
            end_char=16,
            storage_pointer="minio://phi-bucket/abc123",
        )
        assert span_with_pointer.storage_pointer == "minio://phi-bucket/abc123"


class TestTranscript:
    """Test Transcript graph node model."""

    def test_create_transcript(self):
        """Test creating a transcript node."""
        transcript = Transcript(
            filename="clinical_notes_001.txt",
            file_hash="sha256:abc123...",
            storage_pointer="minio://transcripts/001.enc",
        )

        assert transcript.filename == "clinical_notes_001.txt"
        assert not transcript.phi_extraction_complete
        assert not transcript.compliance_review_complete
        assert transcript.phi_count == 0
        assert transcript.violation_count == 0

    def test_transcript_has_auto_id(self):
        """Test that transcript gets auto-generated ID."""
        transcript = Transcript(
            filename="test.txt",
            file_hash="hash123",
            storage_pointer="minio://test",
        )
        assert transcript.id is not None
        assert len(transcript.id) == 36  # UUID format


class TestAuditEvent:
    """Test AuditEvent model for compliance logging."""

    def test_create_audit_event(self):
        """Test creating an audit event."""
        event = AuditEvent(
            event_type=AuditEventType.PHI_DETECTED,
            description="Detected 5 PHI spans in transcript",
            resource_type="Transcript",
            resource_id="tx-123",
            metadata={"phi_count": 5},
        )

        assert event.event_type == AuditEventType.PHI_DETECTED
        assert event.description == "Detected 5 PHI spans in transcript"
        assert event.metadata["phi_count"] == 5
        assert event.timestamp is not None

    def test_all_event_types_exist(self):
        """Verify all expected audit event types exist."""
        expected_types = [
            "PHI_DETECTED",
            "PHI_ACCESSED",
            "PHI_EXPORTED",
            "COMPLIANCE_DECISION",
            "REPORT_GENERATED",
            "USER_LOGIN",
        ]

        actual_types = [t.value for t in AuditEventType]
        for expected in expected_types:
            assert expected in actual_types


class TestComplianceDecision:
    """Test ComplianceDecision model."""

    def test_create_violation(self):
        """Test creating a violation decision."""
        decision = ComplianceDecision(
            is_violation=True,
            severity=ViolationSeverity.HIGH.value,
            reasoning="SSN exposed in plaintext without encryption",
            recommended_action="Encrypt or remove SSN from transcript",
            phi_span_id="span-123",
            regulation_section_id="164.502",
        )

        assert decision.is_violation
        assert decision.severity == "HIGH"
        assert "SSN" in decision.reasoning

    def test_create_non_violation(self):
        """Test creating a non-violation decision."""
        decision = ComplianceDecision(
            is_violation=False,
            reasoning="Date is properly generalized to year only",
            recommended_action="No action required",
            phi_span_id="span-456",
        )

        assert not decision.is_violation
        assert decision.severity is None


class TestPHIExtractionResult:
    """Test PHIExtractionResult model."""

    def test_create_extraction_result(self):
        """Test creating an extraction result."""
        spans = [
            PHISpan(
                category=PHICategory.NAME,
                confidence=0.9,
                detector="presidio",
                start_char=0,
                end_char=10,
            ),
            PHISpan(
                category=PHICategory.PHONE,
                confidence=0.8,
                detector="presidio",
                start_char=20,
                end_char=32,
            ),
        ]

        result = PHIExtractionResult(
            transcript_id="tx-001",
            phi_spans=spans,
            processing_time_ms=150,
            detector_versions={"presidio": "2.2.0"},
        )

        assert result.transcript_id == "tx-001"
        assert len(result.phi_spans) == 2
        assert result.processing_time_ms == 150
        assert result.detector_versions["presidio"] == "2.2.0"
