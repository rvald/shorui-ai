# Ingestion services

from .chunking import ChunkingService
from .document_ingestion_service import DocumentIngestionService
from .embedding import EmbeddingService
from .indexing import IndexingService
from .job_ledger import JobLedgerService
from .local_storage import LocalStorage
from .pipeline import (
    Chunker,
    Embedder,
    IngestionPipeline,
    PipelineContext,
    PipelineStage,
    QdrantIndexer,
    TextExtractor,
    create_document_pipeline,
)
from .storage import MinIOStorage, StorageService, get_storage_backend
from .storage_protocol import StorageBackend

__all__ = [
    # Core services
    "ChunkingService",
    "DocumentIngestionService",
    "EmbeddingService",
    "IndexingService",
    "JobLedgerService",
    # Storage backends
    "StorageBackend",
    "StorageService",  # Backward compatibility alias
    "MinIOStorage",
    "LocalStorage",
    "get_storage_backend",
    # Pipeline components
    "PipelineContext",
    "PipelineStage",
    "TextExtractor",
    "Chunker",
    "Embedder",
    "QdrantIndexer",
    "IngestionPipeline",
    "create_document_pipeline",
]
