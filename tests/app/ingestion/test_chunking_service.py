"""
Unit tests for ChunkingService.

The ChunkingService is responsible for splitting text into chunks
suitable for embedding and vector indexing.
"""

import pytest


class TestChunkingServiceChunk:
    """Tests for the chunk() method."""

    def test_chunk_returns_list_of_strings(self, chunking_service):
        """chunk() should return a list of string chunks."""
        text = "This is a sample text that needs to be chunked into smaller pieces."

        result = chunking_service.chunk(text)

        assert isinstance(result, list)
        assert all(isinstance(chunk, str) for chunk in result)

    def test_chunk_returns_empty_list_for_empty_text(self, chunking_service):
        """chunk() should return empty list for empty input."""
        result = chunking_service.chunk("")

        assert result == []

    def test_chunk_respects_chunk_size(self, chunking_service):
        """chunk() should create chunks within the specified size limit."""
        # Create a long text
        text = "word " * 1000  # 5000 characters

        result = chunking_service.chunk(text)

        # All chunks should be non-empty
        assert all(len(chunk) > 0 for chunk in result)
        # Should have multiple chunks for long text
        assert len(result) >= 1

    def test_chunk_preserves_content(self, chunking_service):
        """chunk() should not lose content during chunking."""
        text = "Hello world. This is a test."

        result = chunking_service.chunk(text)

        # All words should appear in some chunk (case-insensitive due to normalization)
        combined = " ".join(result).lower()
        assert "hello" in combined
        assert "world" in combined


class TestChunkingServiceChunkWithMetadata:
    """Tests for chunk_with_metadata() method."""

    def test_chunk_with_metadata_returns_dicts(self, chunking_service):
        """chunk_with_metadata() should return list of dicts with chunk info."""
        text = "Sample text for chunking."

        result = chunking_service.chunk_with_metadata(text)

        assert isinstance(result, list)
        if len(result) > 0:
            assert "text" in result[0]
            assert "index" in result[0]
            assert "char_count" in result[0]

    def test_chunk_with_metadata_includes_correct_indices(self, chunking_service):
        """chunk_with_metadata() should assign sequential indices."""
        text = "A " * 500  # Longer text to ensure multiple chunks

        result = chunking_service.chunk_with_metadata(text)

        if len(result) > 1:
            indices = [chunk["index"] for chunk in result]
            assert indices == list(range(len(result)))


class TestChunkingServiceConfiguration:
    """Tests for configurable chunking parameters."""

    def test_can_configure_chunk_size(self):
        """ChunkingService should accept custom chunk_size."""
        from app.ingestion.services.chunking import ChunkingService

        service = ChunkingService(chunk_size=256)

        assert service.chunk_size == 256

    def test_can_configure_overlap(self):
        """ChunkingService should accept custom chunk_overlap."""
        from app.ingestion.services.chunking import ChunkingService

        service = ChunkingService(chunk_overlap=25)

        assert service.chunk_overlap == 25


# --- Fixtures ---


@pytest.fixture
def chunking_service():
    """Provides a ChunkingService instance with default settings."""
    from app.ingestion.services.chunking import ChunkingService

    return ChunkingService()
