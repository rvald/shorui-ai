"""
Unit tests for QueryProcessor (SelfQuery + QueryExpansion).

The QueryProcessor should:
1. Extract keywords from queries (SelfQuery)
2. Detect intent (general vs gap_analysis)
3. Expand queries into multiple search queries

Uses OpenAI client singleton for LLM calls.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestSelfQueryExtraction:
    """Tests for keyword and intent extraction."""

    def test_extract_keywords_from_query(self, mock_openai_client):
        """Should extract relevant keywords from the query."""
        from app.rag.services.query_processor import QueryProcessor

        # Mock OpenAI response
        mock_openai_client.chat.completions.create.return_value = MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content='{"keywords": ["foundation", "concrete", "materials"], "intent": "general"}'
                    )
                )
            ]
        )

        processor = QueryProcessor()
        result = processor.extract_keywords("What materials are used for the foundation?")

        assert "keywords" in result
        assert "foundation" in result["keywords"]

    def test_detect_gap_analysis_intent(self, mock_openai_client):
        """Should detect gap analysis queries."""
        from app.rag.services.query_processor import QueryProcessor

        mock_openai_client.chat.completions.create.return_value = MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content='{"keywords": ["missing", "gaps"], "intent": "gap_analysis"}'
                    )
                )
            ]
        )

        processor = QueryProcessor()
        result = processor.extract_keywords("What information is missing from the drawings?")

        assert result["intent"] == "gap_analysis"
        assert result["is_gap_query"]

    def test_general_intent_default(self, mock_openai_client):
        """Default intent should be general."""
        from app.rag.services.query_processor import QueryProcessor

        mock_openai_client.chat.completions.create.return_value = MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(content='{"keywords": ["cost"], "intent": "general"}')
                )
            ]
        )

        processor = QueryProcessor()
        result = processor.extract_keywords("What is the project cost?")

        assert result["intent"] == "general"
        assert not result["is_gap_query"]


class TestQueryExpansion:
    """Tests for query expansion."""

    def test_expand_query_returns_multiple(self, mock_openai_client):
        """Should return multiple expanded queries."""
        from app.rag.services.query_processor import QueryProcessor

        mock_openai_client.chat.completions.create.return_value = MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content="What materials for foundation?\n#\nFoundation material specifications\n#\nConcrete requirements for foundation"
                    )
                )
            ]
        )

        processor = QueryProcessor()
        expanded = processor.expand_query("foundation materials", n=3)

        assert len(expanded) >= 3
        assert "foundation materials" in expanded  # Original included

    def test_expand_includes_original_query(self, mock_openai_client):
        """Expanded queries should include the original."""
        from app.rag.services.query_processor import QueryProcessor

        mock_openai_client.chat.completions.create.return_value = MagicMock(
            choices=[
                MagicMock(message=MagicMock(content="Alternative 1\n#\nAlternative 2"))
            ]
        )

        processor = QueryProcessor()
        original = "test query"
        expanded = processor.expand_query(original, n=3)

        assert original in expanded

    def test_mock_mode_returns_duplicates(self):
        """In mock mode, should return N copies of original."""
        from app.rag.services.query_processor import QueryProcessor

        processor = QueryProcessor(mock=True)
        expanded = processor.expand_query("test", n=3)

        assert len(expanded) == 3
        assert all(q == "test" for q in expanded)


class TestFullProcessing:
    """Tests for combined processing."""

    def test_process_returns_keywords_and_expanded(self, mock_openai_client):
        """Full processing should return both keywords and expanded queries."""
        from app.rag.services.query_processor import QueryProcessor

        # First call for keywords, second for expansion
        mock_openai_client.chat.completions.create.side_effect = [
            MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"keywords": ["materials"], "intent": "general"}'
                        )
                    )
                ]
            ),
            MagicMock(
                choices=[MagicMock(message=MagicMock(content="Alt 1\n#\nAlt 2"))]
            ),
        ]

        processor = QueryProcessor()
        result = processor.process("What materials?", expand_to_n=3)

        assert "keywords" in result
        assert "expanded_queries" in result
        assert len(result["expanded_queries"]) >= 2


# --- Fixtures ---


@pytest.fixture
def mock_openai_client():
    """Mock the OpenAI client singleton."""
    with patch(
        "app.rag.services.query_processor.get_openai_client"
    ) as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        yield mock_client
