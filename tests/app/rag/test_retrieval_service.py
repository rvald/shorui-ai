"""
Unit tests for RetrievalService.

The RetrievalService should:
1. Search documents by query
2. Support configurable top-k results
3. Filter by project_id for multi-tenancy
4. Return structured results with metadata
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestRetrievalServiceSearch:
    """Tests for vector search functionality."""

    @pytest.mark.asyncio
    async def test_search_returns_documents(self, mock_qdrant):
        """Search should return matching documents."""
        from app.rag.services.retrieval import RetrievalService

        # Mock collection exists - use SimpleNamespace for proper .name attribute
        mock_collections = MagicMock()
        mock_collections.collections = [SimpleNamespace(name="project_test-project")]
        mock_qdrant.get_collections.return_value = mock_collections

        # Mock query_points results
        mock_result = MagicMock()
        mock_result.points = [
            MagicMock(
                id="doc1",
                score=0.95,
                payload={
                    "content": "Foundation specs",
                    "filename": "construction.pdf",
                    "page_num": 3,
                },
            ),
            MagicMock(
                id="doc2",
                score=0.85,
                payload={"content": "Material list", "filename": "construction.pdf", "page_num": 5},
            ),
        ]
        mock_qdrant.query_points.return_value = mock_result

        service = RetrievalService(mock=True)
        results = await service.search(query="foundation materials", project_id="test-project", k=5)

        assert len(results) == 2
        assert results[0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_search_respects_k_parameter(self, mock_qdrant):
        """Search should limit results to k."""
        from app.rag.services.retrieval import RetrievalService

        # Mock collection exists
        mock_collections = MagicMock()
        mock_collections.collections = [SimpleNamespace(name="project_test")]
        mock_qdrant.get_collections.return_value = mock_collections

        # Mock query_points result
        mock_result = MagicMock()
        mock_result.points = [
            MagicMock(id=f"doc{i}", score=0.9 - i * 0.1, payload={"content": f"doc {i}"})
            for i in range(3)
        ]
        mock_qdrant.query_points.return_value = mock_result

        service = RetrievalService(mock=True)  # Skip LLM calls
        await service.search("test query", project_id="test", k=3)

        # Verify query_points was called with limit
        mock_qdrant.query_points.assert_called()
        call_args = mock_qdrant.query_points.call_args
        assert call_args.kwargs.get("limit") == 3

    @pytest.mark.asyncio
    async def test_search_uses_correct_collection(self, mock_qdrant):
        """Search should use project-specific collection."""
        from app.rag.services.retrieval import RetrievalService

        # Mock collection exists
        mock_collections = MagicMock()
        mock_collections.collections = [SimpleNamespace(name="project_my-project")]
        mock_qdrant.get_collections.return_value = mock_collections

        mock_result = MagicMock()
        mock_result.points = []
        mock_qdrant.query_points.return_value = mock_result

        service = RetrievalService(mock=True)
        await service.search("query", project_id="my-project", k=5)

        # Should search in project_{project_id} collection
        mock_qdrant.query_points.assert_called()
        call_args = mock_qdrant.query_points.call_args
        collection_name = call_args.kwargs.get("collection_name")
        assert collection_name == "project_my-project"


class TestRetrievalServiceResults:
    """Tests for result formatting."""

    @pytest.mark.asyncio
    async def test_results_include_metadata(self, mock_qdrant):
        """Results should include document metadata."""
        from app.rag.services.retrieval import RetrievalService

        # Mock collection exists
        mock_collections = MagicMock()
        mock_collections.collections = [SimpleNamespace(name="project_test-project")]
        mock_qdrant.get_collections.return_value = mock_collections

        # Mock query_points result with metadata
        mock_result = MagicMock()
        mock_result.points = [
            MagicMock(
                id="doc1",
                score=0.9,
                payload={
                    "content": "Test content",
                    "filename": "test.pdf",
                    "page_num": 1,
                    "project_id": "test-project",
                },
            )
        ]
        mock_qdrant.query_points.return_value = mock_result

        service = RetrievalService(mock=True)
        results = await service.search("query", project_id="test-project", k=5)

        assert len(results) == 1
        result = results[0]
        assert "content" in result
        assert "filename" in result
        assert "score" in result

    @pytest.mark.asyncio
    async def test_empty_results_handled_gracefully(self, mock_qdrant):
        """Empty search results should return empty list."""
        from app.rag.services.retrieval import RetrievalService

        mock_qdrant.search.return_value = []

        service = RetrievalService()
        results = await service.search("nonexistent query", project_id="test", k=5)

        assert results == []


class TestRetrievalServiceEmbedding:
    """Tests for query embedding."""

    @pytest.mark.asyncio
    async def test_search_embeds_query(self, mock_qdrant, mock_embedding):
        """Search should embed the query before searching."""
        from app.rag.services.retrieval import RetrievalService

        mock_embedding.embed.return_value = [[0.1] * 1024]
        mock_qdrant.search.return_value = []

        service = RetrievalService()
        await service.search("test query", project_id="test", k=5)

        # Embedding service should have been called
        mock_embedding.embed.assert_called_once()
        call_args = mock_embedding.embed.call_args[0][0]
        assert "test query" in call_args


# --- Fixtures ---


@pytest.fixture
def mock_qdrant():
    """Mock Qdrant client for testing."""
    with patch("app.rag.services.retrieval.QdrantDatabaseConnector") as mock_cls:
        mock_client = MagicMock()
        mock_cls.get_instance.return_value = mock_client
        
        # Mock get_collections to return empty list by default
        mock_collections = MagicMock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections
        
        # Mock query_points (the actual method used by RetrievalService)
        mock_result = MagicMock()
        mock_result.points = []
        mock_client.query_points.return_value = mock_result
        
        yield mock_client


@pytest.fixture
def mock_embedding():
    """Mock embedding service for testing."""
    with patch("app.rag.services.retrieval.EmbeddingService") as mock_cls:
        mock_service = MagicMock()
        mock_cls.return_value = mock_service
        mock_service.embed.return_value = [[0.1] * 1024]
        yield mock_service
