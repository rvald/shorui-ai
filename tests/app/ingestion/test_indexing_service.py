"""
Unit tests for IndexingService.

The IndexingService is responsible for indexing embedded chunks
into the Qdrant vector database.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestIndexingServiceIndex:
    """Tests for the index() method."""

    def test_index_accepts_chunks_and_embeddings(self, indexing_service, mock_qdrant_client):
        """index() should accept chunks, embeddings, and metadata."""
        chunks = ["chunk1", "chunk2"]
        embeddings = [[0.1, 0.2], [0.3, 0.4]]
        metadata = [{"doc_id": "1"}, {"doc_id": "1"}]

        with patch.object(indexing_service, "_get_client", return_value=mock_qdrant_client):
            result = indexing_service.index(
                chunks=chunks,
                embeddings=embeddings,
                metadata=metadata,
                collection_name="test_collection",
            )

        assert result is True

    def test_index_creates_collection_if_not_exists(self, indexing_service, mock_qdrant_client):
        """index() should create the collection if it doesn't exist."""
        mock_qdrant_client.collection_exists.return_value = False

        with patch.object(indexing_service, "_get_client", return_value=mock_qdrant_client):
            indexing_service.index(
                chunks=["test"], embeddings=[[0.1]], metadata=[{}], collection_name="new_collection"
            )

        mock_qdrant_client.create_collection.assert_called_once()

    def test_index_upserts_points(self, indexing_service, mock_qdrant_client):
        """index() should upsert points to the collection."""
        mock_qdrant_client.collection_exists.return_value = True

        with patch.object(indexing_service, "_get_client", return_value=mock_qdrant_client):
            indexing_service.index(
                chunks=["test1", "test2"],
                embeddings=[[0.1], [0.2]],
                metadata=[{}, {}],
                collection_name="test_collection",
            )

        mock_qdrant_client.upsert.assert_called_once()


class TestIndexingServiceCollectionManagement:
    """Tests for collection management."""

    def test_collection_exists_checks_qdrant(self, indexing_service, mock_qdrant_client):
        """collection_exists() should check Qdrant."""
        mock_qdrant_client.collection_exists.return_value = True

        with patch.object(indexing_service, "_get_client", return_value=mock_qdrant_client):
            result = indexing_service.collection_exists("my_collection")

        assert result is True
        mock_qdrant_client.collection_exists.assert_called_once_with("my_collection")

    def test_create_collection_creates_with_correct_dimension(
        self, indexing_service, mock_qdrant_client
    ):
        """create_collection() should use the correct vector dimension."""
        with patch.object(indexing_service, "_get_client", return_value=mock_qdrant_client):
            indexing_service.create_collection("new_col", vector_size=1024)

        mock_qdrant_client.create_collection.assert_called_once()


class TestIndexingServiceConfiguration:
    """Tests for configuration."""

    def test_default_collection_name(self, indexing_service):
        """IndexingService should have a default collection name."""
        assert indexing_service.default_collection_name is not None

    def test_can_override_default_collection(self):
        """IndexingService should accept custom default collection."""
        from app.ingestion.services.indexing import IndexingService

        service = IndexingService(default_collection="custom_collection")

        assert service.default_collection_name == "custom_collection"


# --- Fixtures ---


@pytest.fixture
def indexing_service():
    """Provides an IndexingService instance."""
    from app.ingestion.services.indexing import IndexingService

    return IndexingService()


@pytest.fixture
def mock_qdrant_client():
    """Provides a mock Qdrant client."""
    mock = MagicMock()
    mock.collection_exists.return_value = True
    mock.upsert.return_value = None
    mock.create_collection.return_value = None
    return mock
