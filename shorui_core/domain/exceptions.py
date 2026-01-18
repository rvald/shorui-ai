"""
Standard exceptions for shorui-ai.

This module defines the hierarchy of exceptions used across the platform.
"""


class ShoruiError(Exception):
    """Base exception for all shorui-ai errors."""
    pass


class IngestionError(ShoruiError):
    """Base exception for ingestion errors."""
    pass


class ExtractionError(IngestionError):
    """Error during text extraction."""
    pass


class ChunkingError(IngestionError):
    """Error during text chunking."""
    pass


class EmbeddingError(IngestionError):
    """Error during embedding generation."""
    pass


class IndexingError(IngestionError):
    """Error during vector indexing."""
    pass


class StorageError(IngestionError):
    """Error during storage operations."""
    pass


class ComplianceError(ShoruiError):
    """Base exception for compliance errors."""
    pass


class PHIDetectionError(ComplianceError):
    """Error during PHI detection."""
    pass
