"""
ChunkingService: Service layer for text chunking.

This service handles splitting text into chunks suitable for embedding
and vector indexing. Supports configurable chunk sizes and overlap.
"""

from typing import Any

from loguru import logger


class SimpleTextSplitter:
    """Simple character-based text splitter with overlap."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks."""
        if not text:
            return []

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]

            if chunk.strip():  # Only add non-empty chunks
                chunks.append(chunk)

            start = end - self.chunk_overlap
            if start < 0:
                start = 0
            if start >= len(text):
                break

        return chunks


class ChunkingService:
    """
    Service for splitting text into chunks.

    This service:
    - Splits text into character-based chunks
    - Supports configurable chunk size and overlap
    - Provides metadata-enriched chunking

    Usage:
        service = ChunkingService(chunk_size=1000, chunk_overlap=100)
        chunks = service.chunk("Long text content...")
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        """
        Initialize the chunking service.

        Args:
            chunk_size: Maximum characters per chunk.
            chunk_overlap: Number of overlapping characters between chunks.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = SimpleTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def chunk(self, text: str) -> list[str]:
        """
        Split text into chunks.

        Args:
            text: The text to chunk.

        Returns:
            list: List of text chunk strings.
        """
        if not text or not text.strip():
            return []

        logger.debug(f"Chunking text of length {len(text)}")

        chunks = self._splitter.split_text(text)

        logger.debug(f"Created {len(chunks)} chunks")

        return chunks

    def chunk_with_metadata(self, text: str) -> list[dict[str, Any]]:
        """
        Split text into chunks with metadata.

        Args:
            text: The text to chunk.

        Returns:
            list: List of dicts with keys:
                - text: The chunk text
                - index: Chunk index (0-based)
                - char_count: Number of characters in chunk
        """
        chunks = self.chunk(text)

        return [
            {"text": chunk, "index": i, "char_count": len(chunk)} for i, chunk in enumerate(chunks)
        ]
