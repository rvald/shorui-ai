from app.compliance.services.privacy_extraction import PrivacyAwareExtractionService
from shorui_core.domain.hipaa_schemas import PHISpan, PHICategory

class TestRedaction:
    """Test PHI redaction logic."""

    def test_redact_simple(self):
        """Test simple redaction of a single span."""
        text = "Hello John Doe"
        spans = [
            PHISpan(
                id="1",
                category=PHICategory.NAME,
                start_char=6,
                end_char=14,
                detector="test",
                confidence=1.0,
            )
        ]
        
        redacted = PrivacyAwareExtractionService.redact_text(text, spans)
        assert redacted == "Hello [NAME]"

    def test_redact_multiple(self):
        """Test redaction of multiple spans."""
        text = "Call John at 555-0199"
        spans = [
            PHISpan(
                id="1",
                category=PHICategory.NAME,
                start_char=5,
                end_char=9,
                detector="test",
                confidence=1.0,
            ),
            PHISpan(
                id="2",
                category=PHICategory.PHONE,
                start_char=13,
                end_char=21,
                detector="test",
                confidence=1.0,
            )
        ]
        
        redacted = PrivacyAwareExtractionService.redact_text(text, spans)
        assert redacted == "Call [NAME] at [PHONE]"

    def test_redact_overlapping_start_desc(self):
        """Test redaction logic sorts spans (reverse start_char) correctly."""
        text = "A B C"
        # Spans provided in ascending order (should be handled by sorting)
        spans = [
            PHISpan(id="1", category=PHICategory.NAME, start_char=0, end_char=1, detector="t", confidence=1.0),
            PHISpan(id="2", category=PHICategory.GEOGRAPHIC, start_char=2, end_char=3, detector="t", confidence=1.0),
            PHISpan(id="3", category=PHICategory.DATE, start_char=4, end_char=5, detector="t", confidence=1.0),
        ]
        
        redacted = PrivacyAwareExtractionService.redact_text(text, spans)
        assert redacted == "[NAME] [GEOGRAPHIC] [DATE]"

    def test_redact_out_of_bounds(self):
        """Test redaction handles out of bounds gracefully."""
        text = "Hi"
        spans = [
             PHISpan(id="1", category=PHICategory.NAME, start_char=0, end_char=10, detector="t", confidence=1.0)
        ]
        # Should truncate to text length
        redacted = PrivacyAwareExtractionService.redact_text(text, spans)
        assert redacted == "[NAME]"
