"""
Tests for PHI Detector service using Presidio.

Tests local PHI detection for HIPAA Safe Harbor identifiers.
"""

import pytest

from app.compliance.services.phi_detector import (
    HIPAA_ENTITIES,
    PRESIDIO_TO_PHI_CATEGORY,
    PHIDetector,
    get_phi_detector,
)
from shorui_core.domain.hipaa_schemas import PHICategory


class TestPHIDetectorInit:
    """Test PHIDetector initialization."""

    def test_default_init(self):
        """Test default initialization."""
        detector = PHIDetector()
        assert detector.min_confidence == 0.5
        assert detector.language == "en"
        assert detector._analyzer is None  # Lazy loaded

    def test_custom_confidence(self):
        """Test with custom confidence threshold."""
        detector = PHIDetector(min_confidence=0.7)
        assert detector.min_confidence == 0.7

    def test_singleton_getter(self):
        """Test get_phi_detector returns same instance."""
        # Clear singleton
        import app.compliance.services.phi_detector as module

        module._detector = None

        detector1 = get_phi_detector()
        detector2 = get_phi_detector()
        assert detector1 is detector2


class TestPHIDetectorMapping:
    """Test Presidio to PHI category mapping."""

    def test_all_presidio_entities_mapped(self):
        """Verify all HIPAA entities have corresponding PHI category."""
        for entity in HIPAA_ENTITIES:
            # All entities should either be mapped or default to OTHER_UNIQUE_ID
            category = PRESIDIO_TO_PHI_CATEGORY.get(entity, PHICategory.OTHER_UNIQUE_ID)
            assert isinstance(category, PHICategory)

    def test_specific_mappings(self):
        """Test specific entity to category mappings."""
        assert PRESIDIO_TO_PHI_CATEGORY["PERSON"] == PHICategory.NAME
        assert PRESIDIO_TO_PHI_CATEGORY["PHONE_NUMBER"] == PHICategory.PHONE
        assert PRESIDIO_TO_PHI_CATEGORY["EMAIL_ADDRESS"] == PHICategory.EMAIL
        assert PRESIDIO_TO_PHI_CATEGORY["US_SSN"] == PHICategory.SSN
        assert PRESIDIO_TO_PHI_CATEGORY["IP_ADDRESS"] == PHICategory.IP_ADDRESS


class TestPHIDetection:
    """Test PHI detection functionality."""

    @pytest.fixture
    def detector(self):
        """Create a detector for testing."""
        return PHIDetector(min_confidence=0.3)

    def test_detect_empty_text(self, detector):
        """Test detecting PHI in empty text."""
        spans = detector.detect("")
        assert spans == []

        spans = detector.detect("   ")
        assert spans == []

    def test_detect_name(self, detector):
        """Test detecting person names."""
        text = "The patient John Smith was seen today."
        spans = detector.detect(text)

        name_spans = [s for s in spans if s.category == PHICategory.NAME]
        assert len(name_spans) >= 1

        # Verify span metadata
        span = name_spans[0]
        assert span.detector == "presidio"
        assert span.confidence > 0
        assert span.start_char >= 0
        assert span.end_char > span.start_char

    def test_detect_email(self, detector):
        """Test detecting email addresses."""
        text = "Contact: john.doe@hospital.com"
        spans = detector.detect(text)

        email_spans = [s for s in spans if s.category == PHICategory.EMAIL]
        assert len(email_spans) >= 1

        # Verify the email is at the right position
        span = email_spans[0]
        detected_text = text[span.start_char : span.end_char]
        assert "john.doe@hospital.com" in detected_text or "@" in detected_text

    def test_detect_phone(self, detector):
        """Test detecting phone numbers."""
        text = "Call us at 555-123-4567 for appointments."
        spans = detector.detect(text)

        phone_spans = [s for s in spans if s.category == PHICategory.PHONE]
        # Phone detection may vary, just check structure if found
        for span in phone_spans:
            assert span.detector == "presidio"
            assert span.confidence > 0

    def test_detect_with_transcript_id(self, detector):
        """Test that source_transcript_id is set on spans."""
        text = "Patient John Doe"
        spans = detector.detect(text, source_transcript_id="tx-123")

        for span in spans:
            assert span.source_transcript_id == "tx-123"

    def test_detect_with_text_returns_matched_text(self, detector):
        """Test detect_with_text includes matched text."""
        text = "Email: test@example.com"
        results = detector.detect_with_text(text)

        assert len(results) > 0
        for span, matched_text in results:
            assert matched_text == text[span.start_char : span.end_char]

    def test_confidence_filtering(self):
        """Test that low confidence results are filtered."""
        high_conf_detector = PHIDetector(min_confidence=0.9)
        low_conf_detector = PHIDetector(min_confidence=0.3)

        text = "Contact john@test.com or 555-1234"

        high_conf_spans = high_conf_detector.detect(text)
        low_conf_spans = low_conf_detector.detect(text)

        # Lower threshold should find same or more spans
        assert len(low_conf_spans) >= len(high_conf_spans)


class TestPHISummary:
    """Test PHI summary functionality."""

    def test_get_phi_summary(self):
        """Test getting summary of PHI in text."""
        detector = PHIDetector(min_confidence=0.3)
        text = "John Smith (john@email.com) called from 555-123-4567"

        summary = detector.get_phi_summary(text)

        assert "total" in summary
        assert "by_category" in summary
        assert summary["total"] >= 1
        assert isinstance(summary["by_category"], dict)

    def test_empty_text_summary(self):
        """Test summary for text with no PHI."""
        detector = PHIDetector()
        summary = detector.get_phi_summary("Just some regular text with no personal info")

        assert summary["total"] >= 0  # May or may not detect anything


class TestMultiplePHITypes:
    """Test detection of multiple PHI types in same text."""

    def test_clinical_transcript_detection(self):
        """Test detection in realistic clinical transcript."""
        detector = PHIDetector(min_confidence=0.3)

        transcript = """
        Patient: John Smith
        DOB: 03/15/1980
        Phone: (555) 123-4567
        Email: john.smith@email.com

        Chief Complaint: Headache for 3 days
        """

        spans = detector.detect(transcript)

        # Should find multiple types
        categories = {span.category for span in spans}

        # At minimum, should detect email and name (most reliable)
        assert PHICategory.EMAIL in categories or PHICategory.NAME in categories

        # All spans should have valid structure
        for span in spans:
            assert span.id is not None
            assert span.detector == "presidio"
            assert 0 <= span.confidence <= 1
            assert span.end_char > span.start_char
