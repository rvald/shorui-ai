"""
Service interfaces (Protocols) for shorui-ai.

This module defines the abstract interfaces (using Python Protocols)
for all ingestion services. These protocols enable:
- Type hinting and static analysis
- Dependency Injection
- Easy mocking for testing
- Clear service contracts
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExtractorProtocol(Protocol):
    """Interface for document content extraction."""

    def extract(self, file_path: str, content_type: str) -> dict[str, Any]:
        """
        Extract content from a document.

        Args:
            file_path: Path to the document file.
            content_type: MIME type of the document.

        Returns:
            dict: Extracted content with 'text' and 'metadata' keys.
        """
        ...

    def process_pdf(self, file_path: str) -> list[dict[str, Any]]:
        """
        Process a PDF with layout awareness.

        Args:
            file_path: Path to the PDF file.

        Returns:
            list: List of hit dictionaries with text and spatial info.
        """
        ...


@runtime_checkable
class ChunkerProtocol(Protocol):
    """Interface for text chunking."""

    chunk_size: int
    chunk_overlap: int

    def chunk(self, text: str) -> list[str]:
        """
        Split text into chunks.

        Args:
            text: The text to chunk.

        Returns:
            list: List of text chunks.
        """
        ...

    def chunk_with_metadata(self, text: str) -> list[dict[str, Any]]:
        """
        Split text into chunks with metadata.

        Args:
            text: The text to chunk.

        Returns:
            list: List of dicts with 'text', 'index', 'char_count'.
        """
        ...


@runtime_checkable
class EmbedderProtocol(Protocol):
    """Interface for embedding generation."""

    model_id: str
    embedding_dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for texts.

        Args:
            texts: List of text strings.

        Returns:
            list: List of embedding vectors.
        """
        ...


@runtime_checkable
class IndexerProtocol(Protocol):
    """Interface for vector database indexing."""

    default_collection_name: str

    def index(
        self,
        chunks: list[str],
        embeddings: list[list[float]],
        metadata: list[dict[str, Any]],
        collection_name: str | None = None,
    ) -> bool:
        """
        Index chunks with embeddings.

        Args:
            chunks: List of text chunks.
            embeddings: List of embedding vectors.
            metadata: List of metadata dicts.
            collection_name: Target collection.

        Returns:
            bool: True if successful.
        """
        ...

    def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists."""
        ...

    def create_collection(self, collection_name: str, vector_size: int) -> None:
        """Create a new collection."""
        ...


@runtime_checkable
class StorageBackend(Protocol):
    """
    Abstract storage interface for document persistence.

    All storage backends must implement these methods to be compatible
    with the ingestion services.
    """

    def upload(
        self,
        content: bytes,
        filename: str,
        project_id: str,
        bucket: str | None = None,
    ) -> str:
        """
        Upload content and return storage path.

        Args:
            content: The file content as bytes.
            filename: Original filename.
            project_id: Project identifier for organization.
            bucket: Optional target bucket/container.

        Returns:
            str: The storage path for retrieval.
        """
        ...

    def download(self, storage_path: str) -> bytes:
        """
        Download content by path.

        Args:
            storage_path: The path returned from upload().

        Returns:
            bytes: The file content.
        """
        ...

    def delete(self, storage_path: str) -> None:
        """
        Delete content by path.

        Args:
            storage_path: The path to delete.
        """
        ...
