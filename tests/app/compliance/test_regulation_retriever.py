"""
Tests for HIPAA Regulation Retrieval Services.

Tests the regulation ingestion and retrieval functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.compliance.services.hipaa_regulation_service import (
    HIPAA_SECTIONS,
    SECTION_PATTERN,
    HIPAARegulationService,
)
from app.compliance.services.regulation_retriever import (
    PHI_CATEGORY_QUERIES,
    RegulationRetriever,
)
from shorui_core.domain.hipaa_schemas import PHICategory, PHISpan


class TestHIPAARegulationService:
    """Test the regulation ingestion service."""

    @pytest.fixture
    def service(self):
        """Create a service for testing."""
        # Mock the dependent services
        with (
            patch("app.compliance.services.hipaa_regulation_service.ChunkingService") as mock_chunk,
            patch("app.compliance.services.hipaa_regulation_service.EmbeddingService") as mock_embed,
            patch("app.compliance.services.hipaa_regulation_service.IndexingService") as mock_index,
        ):
            mock_chunk.return_value.chunk_with_metadata.return_value = [
                {"text": "Sample chunk 1", "index": 0, "char_count": 14},
                {"text": "Sample chunk 2", "index": 1, "char_count": 14},
            ]
            mock_embed.return_value.embed.return_value = [[0.1] * 1024, [0.2] * 1024]

            service = HIPAARegulationService()
            service._chunking = mock_chunk.return_value
            service._embedding = mock_embed.return_value
            service._indexing = mock_index.return_value

            yield service

    def test_service_initialization(self):
        """Test service initializes correctly."""
        with (
            patch("app.compliance.services.hipaa_regulation_service.ChunkingService"),
            patch("app.compliance.services.hipaa_regulation_service.EmbeddingService"),
            patch("app.compliance.services.hipaa_regulation_service.IndexingService"),
        ):
            service = HIPAARegulationService()
            assert service.COLLECTION_NAME == "hipaa_regulations"

    def test_section_extraction(self, service):
        """Test extraction of HIPAA section references."""
        text = "According to §164.514(b)(2), identifiers must be removed. See also 164.502."
        sections = service._extract_sections(text)

        assert "164.514(b)(2)" in sections
        assert "164.502" in sections

    def test_section_title_lookup(self, service):
        """Test looking up section titles."""
        title = service._get_section_title("164.514")
        assert title == "De-identification Standard"

        title = service._get_section_title("164.514(b)(2)")
        assert title == "De-identification Standard"  # Base section match

        title = service._get_section_title("999.999")
        assert title is None

    def test_ingest_regulation(self, service):
        """Test ingesting a regulation document."""
        text = "§164.514 requires de-identification of protected health information."

        result = service.ingest_regulation(
            text=text,
            source="45 CFR 164.514",
            title="De-identification Standard",
        )

        assert result["success"] is True
        assert result["chunks_created"] == 2
        assert "164.514" in result["sections_found"]

        # Verify indexing was called
        service._indexing.index.assert_called_once()




class TestRegulationRetriever:
    """Test the regulation retriever service."""

    def test_phi_category_queries_exist(self):
        """Test that all PHI categories have search queries."""
        for category in PHICategory:
            assert category in PHI_CATEGORY_QUERIES, f"Missing query for {category}"

    def test_retriever_initialization(self):
        """Test retriever initializes correctly."""
        with patch.object(RegulationRetriever, "_get_client", return_value=MagicMock()):
            retriever = RegulationRetriever()
            assert retriever.COLLECTION_NAME == "hipaa_regulations"

    @pytest.fixture
    def retriever_with_mock(self):
        """Create retriever with mocked Qdrant client."""
        with (
            patch(
                "app.compliance.services.regulation_retriever.QdrantDatabaseConnector"
            ) as mock_qdrant,
            patch("app.compliance.services.regulation_retriever.EmbeddingService") as mock_embed,
        ):
            # Mock embedding
            mock_embed.return_value.embed.return_value = [[0.1] * 1024]

            # Mock Qdrant client
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = True
            
            # Mock query_points result
            mock_result = MagicMock()
            mock_result.points = [
                MagicMock(
                    payload={
                        "section_id": "164.514(b)(2)",
                        "title": "Safe Harbor",
                        "content": "The 18 identifiers must be removed...",
                        "source": "45 CFR 164.514",
                        "category": "privacy_rule",
                    },
                    score=0.95,
                ),
            ]
            mock_client.query_points.return_value = mock_result
            mock_qdrant.get_instance.return_value = mock_client

            retriever = RegulationRetriever()
            retriever._client = mock_client
            retriever._embedding = mock_embed.return_value

            yield retriever

    def test_retrieve_for_phi_category(self, retriever_with_mock):
        """Test retrieving regulations for a PHI category."""
        results = retriever_with_mock.retrieve_for_phi_category(PHICategory.SSN)

        assert len(results) == 1
        assert results[0]["section_id"] == "164.514(b)(2)"
        assert results[0]["relevance_score"] == 0.95

    def test_retrieve_for_context(self, retriever_with_mock):
        """Test retrieving regulations for multiple PHI spans."""
        spans = [
            PHISpan(
                category=PHICategory.SSN,
                confidence=0.9,
                detector="presidio",
                start_char=0,
                end_char=11,
            ),
            PHISpan(
                category=PHICategory.NAME,
                confidence=0.85,
                detector="presidio",
                start_char=20,
                end_char=30,
            ),
        ]

        results = retriever_with_mock.retrieve_for_context(spans)

        assert len(results) >= 1

    def test_format_for_prompt(self, retriever_with_mock):
        """Test formatting regulations for LLM prompt."""
        regulations = [
            {
                "section_id": "164.514(b)(2)",
                "title": "Safe Harbor",
                "text": "The identifiers must be removed...",
                "source": "45 CFR 164.514",
            }
        ]

        formatted = retriever_with_mock.format_for_prompt(regulations)

        assert "RELEVANT HIPAA REGULATIONS" in formatted
        assert "164.514(b)(2)" in formatted
        assert "Safe Harbor" in formatted


class TestSectionPattern:
    """Test the section pattern regex."""

    def test_matches_standard_section(self):
        """Test matching standard section format."""
        matches = SECTION_PATTERN.findall("164.514")
        assert "164.514" in matches

    def test_matches_subsection(self):
        """Test matching subsection format."""
        matches = SECTION_PATTERN.findall("164.514(b)(2)")
        assert "164.514(b)(2)" in matches

    def test_matches_with_section_symbol(self):
        """Test matching with § symbol."""
        matches = SECTION_PATTERN.findall("§164.502(a)")
        assert "164.502(a)" in matches


class TestHIPAASectionsDict:
    """Test the HIPAA sections dictionary."""

    def test_common_sections_present(self):
        """Test that common HIPAA sections are defined."""
        assert "164.514" in HIPAA_SECTIONS
        assert "164.502" in HIPAA_SECTIONS
        assert "164.524" in HIPAA_SECTIONS

    def test_section_titles_are_strings(self):
        """Test that all section titles are strings."""
        for section, title in HIPAA_SECTIONS.items():
            assert isinstance(section, str)
            assert isinstance(title, str)
            assert len(title) > 0
