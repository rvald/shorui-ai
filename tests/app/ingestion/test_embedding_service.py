"""
Unit tests for EmbeddingService.

The EmbeddingService is responsible for generating embeddings
for text chunks using a configured embedding model.
"""

import pytest


class TestEmbeddingServiceEmbed:
    """Tests for the embed() method."""

    def test_embed_returns_list_of_vectors(self, embedding_service):
        """embed() should return a list of embedding vectors."""
        texts = ["Hello world", "This is a test"]

        result = embedding_service.embed(texts)

        assert isinstance(result, list)
        assert len(result) == len(texts)

    def test_embed_returns_correct_dimension(self, embedding_service):
        """embed() should return vectors of the expected dimension."""
        texts = ["Test text"]

        result = embedding_service.embed(texts)

        # Embedding dimension should be> 0
        assert len(result[0]) > 0

    def test_embed_handles_empty_list(self, embedding_service):
        """embed() should handle empty input list."""
        result = embedding_service.embed([])

        assert result == []

    def test_embed_handles_single_text(self, embedding_service):
        """embed() should handle a single text input."""
        texts = ["Single text to embed"]

        result = embedding_service.embed(texts)

        assert len(result) == 1
        assert isinstance(result[0], list)


class TestEmbeddingServiceBatching:
    """Tests for batch processing."""

    def test_embed_batch_processes_large_lists(self, embedding_service):
        """embed() should handle large batches efficiently."""
        texts = ["Text " + str(i) for i in range(100)]

        result = embedding_service.embed(texts)

        assert len(result) == 100


class TestEmbeddingServiceConfiguration:
    """Tests for configurable embedding parameters."""

    def test_can_get_model_id(self, embedding_service):
        """EmbeddingService should expose the model ID."""
        model_id = embedding_service.model_id

        assert model_id is not None
        assert isinstance(model_id, str)

    def test_can_get_embedding_dimension(self, embedding_service):
        """EmbeddingService should expose the embedding dimension."""
        dimension = embedding_service.embedding_dimension

        assert dimension > 0


# --- Fixtures ---


@pytest.fixture
def embedding_service():
    """Provides an EmbeddingService instance."""
    from app.ingestion.services.embedding import EmbeddingService

    return EmbeddingService()
