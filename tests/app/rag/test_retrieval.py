from __future__ import annotations
"""
Tests for PipelineRetriever using Fakes.
"""

import pytest

from app.rag.services.retrieval import PipelineRetriever
from tests.app.rag.fakes import FakeGraphRetriever, FakeQueryAnalyzer, FakeReranker


@pytest.fixture
def fake_query_analyzer():
    return FakeQueryAnalyzer(keywords=["test", "rag"])


@pytest.fixture
def fake_reranker():
    return FakeReranker()


@pytest.fixture
def fake_graph_retriever():
    return FakeGraphRetriever()


@pytest.fixture
def retriever(fake_query_analyzer, fake_reranker, fake_graph_retriever):
    # Depending on how we test, we might still need to mock Qdrant/Embeddings inside PipelineRetriever
    # because PipelineRetriever instantiates them lazily in _get_client/_get_embedding_service.
    # To test purely logically without hitting Qdrant, we'd need to mock those private methods or inject them too.
    # But PipelineRetriever doesn't accept them in __init__ in our current design (it lazy loads).
    # Option 1: Mock `_get_client` and `_get_embedding_service`.
    # Option 2: Update PipelineRetriever to allow injection of client/embedder (better).
    
    # For now, let's use unittest.mock to patch the lazy loaders on the instance or class.
    service = PipelineRetriever(
        query_analyzer=fake_query_analyzer,
        reranker=fake_reranker,
        graph_retriever=fake_graph_retriever,
    )
    return service


@pytest.mark.asyncio
async def test_retrieve_flow(retriever, mocker):
    # Mock internal Qdrant client and embedding service to avoid external calls
    mock_client = mocker.Mock()
    mock_embedding = mocker.Mock()
    
    # Mock retrieval results
    mock_point = mocker.Mock()
    mock_point.id = "uuid-1"
    mock_point.score = 0.9
    mock_point.payload = {
        "content": "Doc 1 content",
        "filename": "doc1.pdf",
        "page_num": 1,
        "project_id": "proj-1"
    }
    mock_client.query_points.return_value.points = [mock_point]
    mock_client.get_collections.return_value.collections = [mocker.Mock(name="proj-1")]
    
    mock_embedding.embed.return_value = [[0.1, 0.2]] # Dummy embedding
    
    # Patch the private getters
    mocker.patch.object(retriever, '_get_client', return_value=mock_client)
    mocker.patch.object(retriever, '_get_embedding_service', return_value=mock_embedding)

    # Act
    result = await retriever.retrieve(
        query="test query",
        project_id="proj-1",
        k=2
    )

    # Assert
    assert len(result["documents"]) == 1
    assert result["documents"][0]["id"] == "uuid-1"
    assert result["keywords"] == ["test", "rag"]
    
    # Verify interaction with dependencies
    assert retriever._query_analyzer.process_calls == ["test query"]
