"""
Ingestion Pipeline: Composable document processing stages.

This module provides a pipeline architecture for document ingestion,
allowing flexible composition of processing stages.

Usage:
    pipeline = IngestionPipeline([
        TextExtractor(),
        Chunker(chunk_size=800),
        Embedder(),
        QdrantIndexer(collection_name="my_collection"),
    ])
    result = pipeline.run(PipelineContext(raw_content=doc_bytes))
"""

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field


class PipelineContext(BaseModel):
    """
    Carries data through pipeline stages.

    Each stage can read and modify the context to pass data
    to subsequent stages.
    """

    raw_content: bytes | None = None
    filename: str = ""
    content_type: str = ""
    text: str | None = None
    chunks: list[str] = Field(default_factory=list)
    embeddings: list[list[float]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class PipelineStage(ABC):
    """
    Base class for pipeline stages.

    Each stage processes the context and returns an updated context.
    Stages should be idempotent where possible.
    """

    @property
    def name(self) -> str:
        """Return the stage name for logging."""
        return self.__class__.__name__

    @abstractmethod
    def process(self, ctx: PipelineContext) -> PipelineContext:
        """
        Process context and return updated context.

        Args:
            ctx: The current pipeline context.

        Returns:
            PipelineContext: Updated context for next stage.
        """
        ...


class TextExtractor(PipelineStage):
    """Extract text from raw document content."""

    def process(self, ctx: PipelineContext) -> PipelineContext:
        """Extract text based on content type."""
        if ctx.text is not None:
            logger.debug("Text already extracted, skipping")
            return ctx

        if ctx.raw_content is None:
            logger.warning("No raw content to extract")
            return ctx

        content = ctx.raw_content
        content_type = ctx.content_type
        filename = ctx.filename

        # Check if it's a text file
        is_text = content_type == "text/plain" or filename.lower().endswith(".txt")
        if is_text:
            try:
                ctx.text = content.decode("utf-8")
            except UnicodeDecodeError:
                ctx.text = content.decode("utf-8", errors="ignore")
            logger.debug(f"Extracted {len(ctx.text)} chars from text file")
            return ctx

        # Check if it's a PDF
        is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")
        if is_pdf:
            ctx.text = self._extract_pdf(content)
            logger.debug(f"Extracted {len(ctx.text or '')} chars from PDF")
            return ctx

        logger.warning(f"Unsupported content type: {content_type}")
        ctx.text = ""
        return ctx

    def _extract_pdf(self, content: bytes) -> str:
        """Extract text from PDF bytes."""
        try:
            import tempfile
            import fitz  # PyMuPDF

            with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp:
                tmp.write(content)
                tmp.flush()
                with fitz.open(tmp.name) as doc:
                    return "".join(page.get_text() for page in doc)
        except ImportError:
            logger.error("PyMuPDF not installed. Cannot extract PDF text.")
            return ""
        except Exception as e:
            logger.error(f"Failed to extract PDF text: {e}")
            return ""


class Chunker(PipelineStage):
    """Split text into overlapping chunks."""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 100):
        """
        Initialize the chunker.

        Args:
            chunk_size: Maximum characters per chunk.
            chunk_overlap: Overlap between chunks.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def process(self, ctx: PipelineContext) -> PipelineContext:
        """Split text into chunks."""
        if not ctx.text:
            logger.warning("No text to chunk")
            return ctx

        from shorui_core.domain.interfaces import ChunkerProtocol
        from app.ingestion.services.chunking import ChunkingService

        service = ChunkingService(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        ctx.chunks = service.chunk(ctx.text)
        logger.debug(f"Created {len(ctx.chunks)} chunks")
        return ctx


class Embedder(PipelineStage):
    """Generate embeddings for chunks."""

    def process(self, ctx: PipelineContext) -> PipelineContext:
        """Generate embeddings for all chunks."""
        if not ctx.chunks:
            logger.warning("No chunks to embed")
            return ctx

        from app.ingestion.services.embedding import EmbeddingService

        service = EmbeddingService()
        ctx.embeddings = service.embed(ctx.chunks)
        logger.debug(f"Generated {len(ctx.embeddings)} embeddings")
        return ctx


class QdrantIndexer(PipelineStage):
    """Index chunks and embeddings to Qdrant."""

    def __init__(self, collection_name: str):
        """
        Initialize the indexer.

        Args:
            collection_name: Target Qdrant collection.
        """
        self.collection_name = collection_name

    def process(self, ctx: PipelineContext) -> PipelineContext:
        """Index chunks and embeddings to Qdrant."""
        if not ctx.chunks or not ctx.embeddings:
            logger.warning("Missing chunks or embeddings for indexing")
            return ctx

        from app.ingestion.services.indexing import IndexingService

        # Build metadata for each chunk
        base_metadata = ctx.metadata.copy()
        if ctx.filename and "filename" not in base_metadata:
            base_metadata["filename"] = ctx.filename
        if ctx.content_type and "content_type" not in base_metadata:
            base_metadata["content_type"] = ctx.content_type
        metadata_list = [
            {**base_metadata, "chunk_index": i}
            for i in range(len(ctx.chunks))
        ]

        service = IndexingService()
        service.index(
            chunks=ctx.chunks,
            embeddings=ctx.embeddings,
            metadata=metadata_list,
            collection_name=self.collection_name,
        )

        ctx.result["chunks_indexed"] = len(ctx.chunks)
        ctx.result["collection_name"] = self.collection_name
        logger.debug(f"Indexed {len(ctx.chunks)} chunks to '{self.collection_name}'")
        return ctx


class IngestionPipeline:
    """
    Composable document processing pipeline.

    Chains multiple stages together, passing context through each.
    Supports logging and error handling.

    Usage:
        pipeline = IngestionPipeline([
            TextExtractor(),
            Chunker(chunk_size=800),
            Embedder(),
            QdrantIndexer(collection_name="documents"),
        ])
        ctx = pipeline.run(PipelineContext(raw_content=b"..."))
    """

    def __init__(self, stages: list[PipelineStage]):
        """
        Initialize the pipeline.

        Args:
            stages: Ordered list of processing stages.
        """
        self.stages = stages

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """
        Execute all pipeline stages.

        Args:
            ctx: Initial pipeline context.

        Returns:
            PipelineContext: Final context after all stages.
        """
        logger.info(f"Starting pipeline with {len(self.stages)} stages")

        for stage in self.stages:
            logger.debug(f"Executing stage: {stage.name}")
            try:
                ctx = stage.process(ctx)
            except Exception as e:
                logger.error(f"Stage {stage.name} failed: {e}")
                ctx.result["error"] = str(e)
                ctx.result["failed_stage"] = stage.name
                raise

        logger.info("Pipeline completed successfully")
        return ctx


# Pre-configured pipeline factories

def create_document_pipeline(
    collection_name: str = "general_documents",
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> IngestionPipeline:
    """
    Create a standard document ingestion pipeline.

    Args:
        collection_name: Target Qdrant collection.
        chunk_size: Characters per chunk.
        chunk_overlap: Overlap between chunks.

    Returns:
        IngestionPipeline: Configured pipeline.
    """
    return IngestionPipeline([
        TextExtractor(),
        Chunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap),
        Embedder(),
        QdrantIndexer(collection_name=collection_name),
    ])
