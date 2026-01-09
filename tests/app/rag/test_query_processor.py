"""
Unit tests for QueryProcessor (SelfQuery + QueryExpansion).

The QueryProcessor should:
1. Extract keywords from queries (SelfQuery)
2. Detect intent (general vs gap_analysis)
3. Expand queries into multiple search queries
"""

from unittest.mock import MagicMock, patch

import pytest


class TestSelfQueryExtraction:
    """Tests for keyword and intent extraction."""

    def test_extract_keywords_from_query(self, mock_openai_chain):
        """Should extract relevant keywords from the query."""
        from app.rag.services.query_processor import QueryProcessor

        mock_openai_chain.invoke.return_value = MagicMock(
            content='{"keywords": ["foundation", "concrete", "materials"], "intent": "general"}'
        )

        processor = QueryProcessor()
        result = processor.extract_keywords("What materials are used for the foundation?")

        assert "keywords" in result
        assert "foundation" in result["keywords"]

    def test_detect_gap_analysis_intent(self, mock_openai_chain):
        """Should detect gap analysis queries."""
        from app.rag.services.query_processor import QueryProcessor

        mock_openai_chain.invoke.return_value = MagicMock(
            content='{"keywords": ["missing", "gaps"], "intent": "gap_analysis"}'
        )

        processor = QueryProcessor()
        result = processor.extract_keywords("What information is missing from the drawings?")

        assert result["intent"] == "gap_analysis"
        assert result["is_gap_query"]

    def test_general_intent_default(self, mock_openai_chain):
        """Default intent should be general."""
        from app.rag.services.query_processor import QueryProcessor

        mock_openai_chain.invoke.return_value = MagicMock(
            content='{"keywords": ["cost"], "intent": "general"}'
        )

        processor = QueryProcessor()
        result = processor.extract_keywords("What is the project cost?")

        assert result["intent"] == "general"
        assert not result["is_gap_query"]


class TestQueryExpansion:
    """Tests for query expansion."""

    def test_expand_query_returns_multiple(self, mock_openai_chain):
        """Should return multiple expanded queries."""
        from app.rag.services.query_processor import QueryProcessor

        mock_openai_chain.invoke.return_value = MagicMock(
            content="What materials for foundation?\n#\nFoundation material specifications\n#\nConcrete requirements for foundation"
        )

        processor = QueryProcessor()
        expanded = processor.expand_query("foundation materials", n=3)

        assert len(expanded) >= 3
        assert "foundation materials" in expanded  # Original included

    def test_expand_includes_original_query(self, mock_openai_chain):
        """Expanded queries should include the original."""
        from app.rag.services.query_processor import QueryProcessor

        mock_openai_chain.invoke.return_value = MagicMock(content="Alternative 1\n#\nAlternative 2")

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

    def test_process_returns_keywords_and_expanded(self, mock_openai_chain):
        """Full processing should return both keywords and expanded queries."""
        from app.rag.services.query_processor import QueryProcessor

        # First call for keywords, second for expansion
        mock_openai_chain.invoke.side_effect = [
            MagicMock(content='{"keywords": ["materials"], "intent": "general"}'),
            MagicMock(content="Alt 1\n#\nAlt 2"),
        ]

        processor = QueryProcessor()
        result = processor.process("What materials?", expand_to_n=3)

        assert "keywords" in result
        assert "expanded_queries" in result
        assert len(result["expanded_queries"]) >= 2


# --- Fixtures ---


@pytest.fixture
def mock_openai_chain():
    """Mock the OpenAI LangChain components."""
    with (
        patch("app.rag.services.query_processor.ChatOpenAI") as mock_chat,
        patch("app.rag.services.query_processor.ChatPromptTemplate") as mock_template,
    ):
        # Create mock model
        mock_model = MagicMock()
        mock_chat.return_value = mock_model

        # Create mock prompt
        mock_prompt = MagicMock()
        mock_template.from_messages.return_value = mock_prompt

        # Create a mock chain that is returned when prompt | model
        mock_chain = MagicMock()
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)

        yield mock_chain
