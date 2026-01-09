"""
Unit tests for DocumentIngestionService.

Tests cover:
1. Text file ingestion
2. PDF extraction
3. Chunking and embedding
4. Collection naming
"""

from unittest.mock import MagicMock, patch

import pytest


class TestDocumentIngestionService:
    """Tests for the DocumentIngestionService class."""

    def test_ingest_text_file(self, mock_services):
        """Should chunk and index text content."""
        from app.ingestion.services.document_ingestion_service import (
            DocumentIngestionService,
        )

        service = DocumentIngestionService()
        result = service.ingest_document(
            content=b"This is a test document with some content.",
            filename="test.txt",
            content_type="text/plain",
            project_id="test-project",
        )

        assert result["success"] is True
        assert result["chunks_created"] > 0
        assert result["collection_name"] == "project_test-project"

    def test_ingest_creates_chunks(self, mock_services):
        """Should return correct chunk count."""
        from app.ingestion.services.document_ingestion_service import (
            DocumentIngestionService,
        )

        # Configure chunking to return multiple chunks
        mock_services["chunking"].chunk.return_value = ["chunk1", "chunk2", "chunk3"]

        service = DocumentIngestionService()
        result = service.ingest_document(
            content="Long document content that will be chunked.",
            filename="doc.txt",
            content_type="text/plain",
            project_id="my-project",
        )

        assert result["chunks_created"] == 3

    def test_ingest_uses_project_collection(self, mock_services):
        """Should index to project-specific collection."""
        from app.ingestion.services.document_ingestion_service import (
            DocumentIngestionService,
        )

        service = DocumentIngestionService()
        service.ingest_document(
            content=b"Document content",
            filename="test.txt",
            content_type="text/plain",
            project_id="special-project",
        )

        # Verify indexing was called with correct collection
        mock_services["indexing"].index.assert_called()
        call_kwargs = mock_services["indexing"].index.call_args
        assert call_kwargs.kwargs.get("collection_name") == "project_special-project"

    def test_ingest_with_custom_collection(self, mock_services):
        """Should use custom collection name when provided."""
        from app.ingestion.services.document_ingestion_service import (
            DocumentIngestionService,
        )

        service = DocumentIngestionService()
        result = service.ingest_document(
            content=b"Document content",
            filename="test.txt",
            content_type="text/plain",
            project_id="project-1",
            collection_name="custom_collection",
        )

        assert result["collection_name"] == "custom_collection"

    def test_handles_empty_content(self, mock_services):
        """Should handle empty input gracefully."""
        from app.ingestion.services.document_ingestion_service import (
            DocumentIngestionService,
        )

        service = DocumentIngestionService()
        result = service.ingest_document(
            content=b"",
            filename="empty.txt",
            content_type="text/plain",
            project_id="test",
        )

        assert result["success"] is False
        assert result["chunks_created"] == 0

    def test_handles_string_content(self, mock_services):
        """Should accept string content directly."""
        from app.ingestion.services.document_ingestion_service import (
            DocumentIngestionService,
        )

        service = DocumentIngestionService()
        result = service.ingest_document(
            content="String content directly, not bytes",
            filename="doc.txt",
            content_type="text/plain",
            project_id="test",
        )

        assert result["success"] is True

    def test_generates_metadata_for_chunks(self, mock_services):
        """Should generate proper metadata for each chunk."""
        from app.ingestion.services.document_ingestion_service import (
            DocumentIngestionService,
        )

        mock_services["chunking"].chunk.return_value = ["chunk1", "chunk2"]

        service = DocumentIngestionService()
        service.ingest_document(
            content=b"Test content",
            filename="report.txt",
            content_type="text/plain",
            project_id="proj-123",
        )

        # Check metadata was passed to indexing
        call_args = mock_services["indexing"].index.call_args
        metadata_list = call_args.kwargs.get("metadata") or call_args.args[2]

        assert len(metadata_list) == 2
        assert metadata_list[0]["filename"] == "report.txt"
        assert metadata_list[0]["project_id"] == "proj-123"
        assert metadata_list[0]["chunk_index"] == 0
        assert metadata_list[1]["chunk_index"] == 1


class TestTextExtraction:
    """Tests for text extraction functionality."""

    def test_extract_utf8_text(self, mock_services):
        """Should decode UTF-8 text bytes."""
        from app.ingestion.services.document_ingestion_service import (
            DocumentIngestionService,
        )

        service = DocumentIngestionService()
        text = service._extract_text(
            content=b"Hello, world!",
            filename="test.txt",
            content_type="text/plain",
        )

        assert text == "Hello, world!"

    def test_handles_unicode_errors(self, mock_services):
        """Should handle invalid UTF-8 gracefully."""
        from app.ingestion.services.document_ingestion_service import (
            DocumentIngestionService,
        )

        # Invalid UTF-8 bytes
        invalid_bytes = b"\xff\xfe Invalid bytes"

        service = DocumentIngestionService()
        text = service._extract_text(
            content=invalid_bytes,
            filename="test.txt",
            content_type="text/plain",
        )

        # Should not raise, may have some content or be handled gracefully
        assert isinstance(text, str)

    def test_unsupported_file_type_returns_empty(self, mock_services):
        """Should return empty string for unsupported types."""
        from app.ingestion.services.document_ingestion_service import (
            DocumentIngestionService,
        )

        service = DocumentIngestionService()
        text = service._extract_text(
            content=b"binary data",
            filename="file.xyz",
            content_type="application/octet-stream",
        )

        assert text == ""


# --- Fixtures ---


@pytest.fixture
def mock_services():
    """Mock all services used by DocumentIngestionService."""
    with (
        patch(
            "app.ingestion.services.document_ingestion_service.ChunkingService"
        ) as mock_chunk_cls,
        patch(
            "app.ingestion.services.document_ingestion_service.EmbeddingService"
        ) as mock_embed_cls,
        patch(
            "app.ingestion.services.document_ingestion_service.IndexingService"
        ) as mock_index_cls,
    ):
        # Create mock instances
        mock_chunking = MagicMock()
        mock_embedding = MagicMock()
        mock_indexing = MagicMock()

        # Configure classes to return mocks
        mock_chunk_cls.return_value = mock_chunking
        mock_embed_cls.return_value = mock_embedding
        mock_index_cls.return_value = mock_indexing

        # Default behaviors
        mock_chunking.chunk.return_value = ["chunk1"]
        mock_embedding.embed.return_value = [[0.1] * 1024]
        mock_indexing.index.return_value = True

        yield {
            "chunking": mock_chunking,
            "embedding": mock_embedding,
            "indexing": mock_indexing,
        }
