"""
Document Ingestion Service for indexing general documents into Qdrant.

This service handles:
1. Ingesting general documents (TXT, PDF)
2. Chunking with project metadata
3. Embedding and indexing to Qdrant
4. Project-specific collection management
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

from loguru import logger

from app.ingestion.services.chunking import ChunkingService
from app.ingestion.services.embedding import EmbeddingService
from app.ingestion.services.indexing import IndexingService


class DocumentIngestionService:
    """
    Service for ingesting general documents into Qdrant.

    Creates project-specific collections for document storage, enabling
    RAG-based retrieval for general document queries.

    Usage:
        service = DocumentIngestionService()
        stats = service.ingest_document(
            content=b"document bytes",
            filename="report.txt",
            content_type="text/plain",
            project_id="my-project"
        )
    """

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ):
        """
        Initialize the document ingestion service.

        Args:
            chunk_size: Maximum characters per chunk
            chunk_overlap: Overlap between chunks
        """
        self._chunking = ChunkingService(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self._embedding = EmbeddingService()
        self._indexing = IndexingService()

    def ingest_document(
        self,
        content: bytes | str,
        filename: str,
        content_type: str,
        project_id: str,
        collection_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Ingest a document into the vector database.

        Args:
            content: Document content (bytes or string)
            filename: Original filename
            content_type: MIME type of the document
            project_id: Project identifier for multi-tenancy
            collection_name: Optional custom collection name (defaults to project_{project_id})

        Returns:
            dict: Ingestion statistics including chunks_created, collection_name
        """
        logger.info(f"Ingesting document for project {project_id}")

        # Determine target collection
        target_collection = collection_name or f"project_{project_id}"

        # Extract text content
        text = self._extract_text(content, filename, content_type)

        if not text or not text.strip():
            logger.warning("No text content extracted from document")
            return {
                "chunks_created": 0,
                "collection_name": target_collection,
                "success": False,
                "message": "No text content found",
            }

        # Chunk the text
        chunks = self._chunking.chunk(text)

        if not chunks:
            logger.warning("No chunks created from document")
            return {
                "chunks_created": 0,
                "collection_name": target_collection,
                "success": False,
            }

        logger.info(f"Created {len(chunks)} chunks from document")

        # Build metadata for each chunk
        metadata_list = [
            {
                "project_id": project_id,
                "filename": filename,
                "content_type": content_type,
                "chunk_index": i,
                "doc_type": "general",
            }
            for i in range(len(chunks))
        ]

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(chunks)} chunks")
        embeddings = self._embedding.embed(chunks)

        # Index to Qdrant
        self._indexing.index(
            chunks=chunks,
            embeddings=embeddings,
            metadata=metadata_list,
            collection_name=target_collection,
        )

        logger.info(f"Indexed {len(chunks)} chunks to collection '{target_collection}'")

        return {
            "chunks_created": len(chunks),
            "collection_name": target_collection,
            "filename": filename,
            "success": True,
        }

    def _extract_text(
        self,
        content: bytes | str,
        filename: str,
        content_type: str,
    ) -> str:
        """
        Extract text content from document bytes or string.

        Handles:
        - Plain text (bytes or string)
        - PDF documents

        Args:
            content: Document content
            filename: Original filename
            content_type: MIME type

        Returns:
            str: Extracted text content
        """
        # If already a string, return as-is
        if isinstance(content, str):
            return content

        # Check if it's a text file
        is_text = content_type == "text/plain" or filename.lower().endswith(".txt")

        if is_text:
            try:
                return content.decode("utf-8")
            except UnicodeDecodeError:
                return content.decode("utf-8", errors="ignore")

        # Check if it's a PDF
        is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")

        if is_pdf:
            return self._extract_pdf_text(content)

        # Unsupported file type
        logger.warning(f"Unsupported file type: {content_type}")
        return ""

    def _extract_pdf_text(self, content: bytes) -> str:
        """
        Extract text from PDF bytes.

        Args:
            content: PDF file bytes

        Returns:
            str: Extracted text
        """
        try:
            import fitz  # PyMuPDF

            # Write to temp file for processing
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                with fitz.open(tmp_path) as doc:
                    text = "".join(page.get_text() for page in doc)
                return text
            finally:
                os.unlink(tmp_path)

        except ImportError:
            logger.error("PyMuPDF (fitz) not installed. Cannot extract PDF text.")
            return ""
        except Exception as e:
            logger.error(f"Failed to extract PDF text: {e}")
            return ""

    def get_collection_stats(self, project_id: str) -> dict[str, Any]:
        """
        Get statistics about a project's document collection.

        Args:
            project_id: Project identifier

        Returns:
            dict: Collection statistics
        """
        collection_name = f"project_{project_id}"
        try:
            client = self._indexing._get_client()

            if not client.collection_exists(collection_name):
                return {"exists": False, "points_count": 0}

            info = client.get_collection(collection_name)
            return {
                "exists": True,
                "collection_name": collection_name,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"error": str(e)}
