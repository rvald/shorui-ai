"""
PHI Detector Service using Microsoft Presidio.

Local PHI detection for HIPAA compliance. Detects the 18 Safe Harbor
PHI identifiers without sending data to external services.

This service is for DETECTION and AUDIT only - it tags PHI locations
but does not mask or redact (since we're using a self-hosted LLM).
"""

from loguru import logger
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider

from shorui_core.domain.hipaa_schemas import PHICategory, PHISpan

# Mapping from Presidio entity types to our PHI categories
PRESIDIO_TO_PHI_CATEGORY = {
    "PERSON": PHICategory.NAME,
    "PHONE_NUMBER": PHICategory.PHONE,
    "EMAIL_ADDRESS": PHICategory.EMAIL,
    "US_SSN": PHICategory.SSN,
    "US_DRIVER_LICENSE": PHICategory.LICENSE_NUMBER,
    "CREDIT_CARD": PHICategory.ACCOUNT_NUMBER,
    "IP_ADDRESS": PHICategory.IP_ADDRESS,
    "URL": PHICategory.URL,
    "DATE_TIME": PHICategory.DATE,
    "LOCATION": PHICategory.GEOGRAPHIC,
    "MEDICAL_LICENSE": PHICategory.LICENSE_NUMBER,
    "US_PASSPORT": PHICategory.OTHER_UNIQUE_ID,
    "US_BANK_NUMBER": PHICategory.ACCOUNT_NUMBER,
    "US_ITIN": PHICategory.SSN,  # Individual Taxpayer ID
    "NRP": PHICategory.OTHER_UNIQUE_ID,  # Nationality/Religion/Political group
    "IBAN_CODE": PHICategory.ACCOUNT_NUMBER,
}

# Presidio entities we want to detect for HIPAA
HIPAA_ENTITIES = [
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "US_SSN",
    "US_DRIVER_LICENSE",
    "CREDIT_CARD",
    "IP_ADDRESS",
    "URL",
    "DATE_TIME",
    "LOCATION",
    "MEDICAL_LICENSE",
    "US_PASSPORT",
    "US_BANK_NUMBER",
    "US_ITIN",
    "IBAN_CODE",
]


class PHIDetector:
    """
    Local PHI detection using Microsoft Presidio.

    Detects PHI in text without sending data externally.
    Thread-safe and reusable across requests.

    Example:
        detector = PHIDetector()
        spans = detector.detect("Call John Doe at 555-123-4567")
        # Returns PHISpan objects for "John Doe" (NAME) and "555-123-4567" (PHONE)
    """

    def __init__(self, min_confidence: float = 0.5, language: str = "en"):
        """
        Initialize the PHI detector.

        Args:
            min_confidence: Minimum confidence threshold (0.0-1.0)
            language: Language code for NLP processing
        """
        self.min_confidence = min_confidence
        self.language = language
        self._analyzer: AnalyzerEngine | None = None

    @property
    def analyzer(self) -> AnalyzerEngine:
        """Lazy-load the analyzer engine."""
        if self._analyzer is None:
            logger.info("Initializing Presidio AnalyzerEngine...")

            # Use spaCy for NLP (already in dependencies)
            configuration = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            }

            try:
                provider = NlpEngineProvider(nlp_configuration=configuration)
                nlp_engine = provider.create_engine()
                self._analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
            except Exception as e:
                logger.warning(f"Failed to load spaCy model: {e}. Using default engine.")
                self._analyzer = AnalyzerEngine()

            logger.info("Presidio AnalyzerEngine initialized")

        return self._analyzer

    def detect(self, text: str, source_transcript_id: str | None = None) -> list[PHISpan]:
        """
        Detect PHI in text.

        Args:
            text: The text to analyze
            source_transcript_id: Optional ID of parent transcript for linking

        Returns:
            List of PHISpan objects for each detected PHI instance
        """
        if not text or not text.strip():
            return []

        # Run Presidio analysis
        results: list[RecognizerResult] = self.analyzer.analyze(
            text=text, entities=HIPAA_ENTITIES, language=self.language
        )

        # Convert to PHISpan objects
        phi_spans: list[PHISpan] = []

        for result in results:
            # Skip low confidence detections
            if result.score < self.min_confidence:
                continue

            # Map Presidio entity to PHI category
            category = PRESIDIO_TO_PHI_CATEGORY.get(result.entity_type, PHICategory.OTHER_UNIQUE_ID)

            span = PHISpan(
                category=category,
                confidence=result.score,
                detector="presidio",
                start_char=result.start,
                end_char=result.end,
                source_transcript_id=source_transcript_id,
            )

            phi_spans.append(span)

        logger.debug(f"Detected {len(phi_spans)} PHI spans in text ({len(text)} chars)")
        return phi_spans

    def detect_with_text(
        self, text: str, source_transcript_id: str | None = None
    ) -> list[tuple[PHISpan, str]]:
        """
        Detect PHI and return spans with the matched text.

        This is useful for debugging/audit but should NOT be used
        to store the actual PHI text in non-secure locations.

        Args:
            text: The text to analyze
            source_transcript_id: Optional ID of parent transcript

        Returns:
            List of (PHISpan, matched_text) tuples
        """
        spans = self.detect(text, source_transcript_id)

        return [(span, text[span.start_char : span.end_char]) for span in spans]

    def get_phi_summary(self, text: str) -> dict:
        """
        Get a summary of PHI detected in text.

        Useful for quick analysis without full span details.

        Returns:
            Dict with category counts and total
        """
        spans = self.detect(text)

        summary = {"total": len(spans), "by_category": {}}
        for span in spans:
            cat_name = span.category.value
            summary["by_category"][cat_name] = summary["by_category"].get(cat_name, 0) + 1

        return summary


# Singleton instance for reuse
_detector: PHIDetector | None = None


def get_phi_detector(min_confidence: float = 0.5) -> PHIDetector:
    """
    Get the shared PHI detector instance.

    Args:
        min_confidence: Minimum confidence threshold

    Returns:
        PHIDetector instance
    """
    global _detector
    if _detector is None:
        _detector = PHIDetector(min_confidence=min_confidence)
    return _detector
