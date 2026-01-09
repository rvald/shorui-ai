"""
Unit tests for Reranker service.

The Reranker should:
1. Score query-document pairs using CrossEncoder
2. Return top-k documents sorted by score
"""

from unittest.mock import MagicMock, patch

import pytest


class TestRerankerScoring:
    """Tests for reranking functionality."""

    def test_rerank_returns_sorted_documents(self, mock_cross_encoder):
        """Should return documents sorted by relevance score."""
        from app.rag.services.reranker import RerankerService

        # Mock scores: doc2 > doc0 > doc1
        mock_cross_encoder.return_value = [0.5, 0.3, 0.9]

        documents = [
            {"id": "doc0", "content": "Document 0"},
            {"id": "doc1", "content": "Document 1"},
            {"id": "doc2", "content": "Document 2"},
        ]

        service = RerankerService()
        reranked = service.rerank("test query", documents, top_k=3)

        # doc2 should be first (highest score)
        assert reranked[0]["id"] == "doc2"
        assert reranked[1]["id"] == "doc0"
        assert reranked[2]["id"] == "doc1"

    def test_rerank_respects_top_k(self, mock_cross_encoder):
        """Should return only top_k documents."""
        from app.rag.services.reranker import RerankerService

        mock_cross_encoder.return_value = [0.9, 0.8, 0.7, 0.6, 0.5]

        documents = [{"id": f"doc{i}", "content": f"Doc {i}"} for i in range(5)]

        service = RerankerService()
        reranked = service.rerank("query", documents, top_k=3)

        assert len(reranked) == 3

    def test_rerank_adds_scores(self, mock_cross_encoder):
        """Reranked documents should include rerank_score."""
        from app.rag.services.reranker import RerankerService

        mock_cross_encoder.return_value = [0.8]

        documents = [{"id": "doc0", "content": "Content"}]

        service = RerankerService()
        reranked = service.rerank("query", documents, top_k=1)

        assert "rerank_score" in reranked[0]
        assert isinstance(reranked[0]["rerank_score"], float)


class TestRerankerEdgeCases:
    """Tests for edge cases."""

    def test_empty_documents_returns_empty(self, mock_cross_encoder):
        """Empty document list should return empty."""
        from app.rag.services.reranker import RerankerService

        service = RerankerService()
        reranked = service.rerank("query", [], top_k=5)

        assert reranked == []

    def test_mock_mode_preserves_order(self):
        """In mock mode, should return documents without reordering."""
        from app.rag.services.reranker import RerankerService

        documents = [
            {"id": "doc0", "content": "First"},
            {"id": "doc1", "content": "Second"},
        ]

        service = RerankerService(mock=True)
        reranked = service.rerank("query", documents, top_k=2)

        assert len(reranked) == 2
        assert reranked[0]["id"] == "doc0"  # Order preserved


# --- Fixtures ---


@pytest.fixture
def mock_cross_encoder():
    """Mock the CrossEncoder model."""
    with patch("app.rag.services.reranker.CrossEncoder") as mock_cls:
        mock_model = MagicMock()
        mock_cls.return_value = mock_model

        # model.predict returns list of scores
        yield mock_model.predict
