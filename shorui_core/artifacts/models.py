"""
Domain models for artifacts and job status.

These models provide type-safe representations of artifacts stored in the
canonical artifacts registry and standardized job status semantics.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    """
    Canonical artifact types across all modules.
    
    Each artifact type represents a specific kind of input or output
    that can be stored and tracked in the artifacts registry.
    """
    # Ingestion artifacts
    RAW_UPLOAD = "raw_upload"
    INGESTION_RESULT = "ingestion_result"
    PROCESSED_DOCUMENT = "processed_document"
    
    # Compliance artifacts
    TRANSCRIPT = "transcript"
    COMPLIANCE_REPORT = "compliance_report"
    REDACTED_TEXT = "redacted_text"
    
    # RAG artifacts
    RAG_RETRIEVAL_RESULT = "rag_retrieval_result"
    INDEX_SUMMARY = "index_summary"


class JobStatus(str, Enum):
    """
    Canonical job status values.
    
    All async jobs must use these statuses for consistent tracking
    and observability.
    """
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # Idempotent short-circuit


class StorageBackend(str, Enum):
    """Storage backends for artifacts."""
    MINIO = "minio"
    LOCAL = "local"
    POSTGRES = "postgres"  # For small artifacts stored as JSONB


class Artifact(BaseModel):
    """
    Domain model for an artifact in the registry.
    
    Artifacts are immutable outputs/inputs referenced by ID and stored
    in an artifact store (object storage, DB blob, etc.).
    """
    artifact_id: str = Field(..., description="UUID primary key")
    tenant_id: str = Field(..., description="Tenant namespace")
    project_id: str = Field(..., description="Project identifier")
    artifact_type: ArtifactType = Field(..., description="Type of artifact")
    storage_backend: StorageBackend = Field(..., description="Where the artifact is stored")
    storage_pointer: str = Field(..., description="Backend-specific location string")
    content_type: Optional[str] = Field(None, description="MIME type (e.g., application/json)")
    byte_size: Optional[int] = Field(None, description="Size in bytes")
    sha256: Optional[str] = Field(None, description="Content hash for dedupe/integrity")
    schema_version: Optional[str] = Field(None, description="For JSON artifacts")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    created_by_job_id: Optional[str] = Field(None, description="Job that created this artifact")

    class Config:
        use_enum_values = True

    @classmethod
    def from_db_row(cls, row: tuple) -> "Artifact":
        """Construct Artifact from a database row tuple."""
        return cls(
            artifact_id=str(row[0]),
            tenant_id=row[1],
            project_id=row[2],
            artifact_type=row[3],
            storage_backend=row[4],
            storage_pointer=row[5],
            content_type=row[6],
            byte_size=row[7],
            sha256=row[8],
            schema_version=row[9],
            created_at=row[10],
            created_by_job_id=str(row[11]) if row[11] else None,
        )
