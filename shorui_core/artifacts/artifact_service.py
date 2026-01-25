"""
ArtifactService: Canonical CRUD operations for the artifacts registry.

Provides a unified interface for registering and retrieving artifacts
across all modules (ingestion, compliance, RAG).

See specs/component_artifacts_and_jobs.md for the full specification.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from loguru import logger

from shorui_core.artifacts.models import Artifact, ArtifactType, StorageBackend
from shorui_core.config import settings
from shorui_core.infrastructure.postgres import get_db_connection


def _get_default_storage_backend() -> str:
    """Determine default storage backend from settings."""
    if getattr(settings, "USE_LOCAL_STORAGE", False):
        return StorageBackend.LOCAL.value
    return StorageBackend.MINIO.value


class ArtifactService:
    """
    Service for managing artifacts in the canonical registry.
    
    All artifacts (uploads, results, reports) should be registered here
    for cross-module queryability and lineage tracking.
    """

    def register(
        self,
        *,
        tenant_id: str,
        project_id: str,
        artifact_type: ArtifactType | str,
        storage_pointer: str,
        content_type: Optional[str] = None,
        byte_size: Optional[int] = None,
        sha256: Optional[str] = None,
        schema_version: Optional[str] = None,
        created_by_job_id: Optional[str] = None,
        storage_backend: Optional[str] = None,
        artifact_id: Optional[str] = None,
    ) -> str:
        """
        Register a new artifact in the registry.
        
        Args:
            tenant_id: Tenant namespace
            project_id: Project identifier
            artifact_type: Type of artifact (enum or string)
            storage_pointer: Backend-specific storage path
            content_type: MIME type (e.g., application/pdf)
            byte_size: Size in bytes
            sha256: Content hash for dedupe/integrity
            schema_version: Version for JSON artifacts
            created_by_job_id: Job that created this artifact
            storage_backend: Storage backend (defaults based on settings)
            artifact_id: Optional pre-generated artifact ID
            
        Returns:
            artifact_id (UUID string)
        """
        aid = artifact_id or str(uuid.uuid4())
        backend = storage_backend or _get_default_storage_backend()
        
        # Normalize artifact_type to string
        atype = artifact_type.value if isinstance(artifact_type, ArtifactType) else artifact_type

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO artifacts (
                    artifact_id, tenant_id, project_id, artifact_type,
                    storage_backend, storage_pointer, content_type,
                    byte_size, sha256, schema_version, created_at,
                    created_by_job_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (artifact_id) DO NOTHING
                """,
                (
                    aid,
                    tenant_id,
                    project_id,
                    atype,
                    backend,
                    storage_pointer,
                    content_type,
                    byte_size,
                    sha256,
                    schema_version,
                    datetime.utcnow(),
                    created_by_job_id,
                ),
            )
            conn.commit()

        logger.debug(
            f"Registered artifact {aid} (type={atype}, job={created_by_job_id})"
        )
        return aid

    def get_by_id(self, artifact_id: str) -> Artifact | None:
        """
        Retrieve an artifact by its ID.
        
        Args:
            artifact_id: UUID of the artifact
            
        Returns:
            Artifact model or None if not found
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT artifact_id, tenant_id, project_id, artifact_type,
                       storage_backend, storage_pointer, content_type,
                       byte_size, sha256, schema_version, created_at,
                       created_by_job_id
                FROM artifacts
                WHERE artifact_id = %s
                """,
                (artifact_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return Artifact.from_db_row(row)

    def get_by_job_id(self, job_id: str) -> list[Artifact]:
        """
        Retrieve all artifacts created by a specific job.
        
        Args:
            job_id: UUID of the job
            
        Returns:
            List of Artifact models (may be empty)
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT artifact_id, tenant_id, project_id, artifact_type,
                       storage_backend, storage_pointer, content_type,
                       byte_size, sha256, schema_version, created_at,
                       created_by_job_id
                FROM artifacts
                WHERE created_by_job_id = %s
                ORDER BY created_at ASC
                """,
                (job_id,),
            )
            rows = cursor.fetchall()

        return [Artifact.from_db_row(row) for row in rows]

    def get_by_type(
        self,
        artifact_type: ArtifactType | str,
        tenant_id: str,
        project_id: str,
        limit: int = 100,
    ) -> list[Artifact]:
        """
        Retrieve artifacts by type within a tenant/project scope.
        
        Args:
            artifact_type: Type to filter by
            tenant_id: Tenant namespace
            project_id: Project identifier
            limit: Max results to return
            
        Returns:
            List of Artifact models
        """
        atype = artifact_type.value if isinstance(artifact_type, ArtifactType) else artifact_type

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT artifact_id, tenant_id, project_id, artifact_type,
                       storage_backend, storage_pointer, content_type,
                       byte_size, sha256, schema_version, created_at,
                       created_by_job_id
                FROM artifacts
                WHERE artifact_type = %s
                  AND tenant_id = %s
                  AND project_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (atype, tenant_id, project_id, limit),
            )
            rows = cursor.fetchall()

        return [Artifact.from_db_row(row) for row in rows]

    def delete_by_job_id(self, job_id: str) -> int:
        """
        Delete all artifacts created by a specific job.
        
        Use with caution - typically for cleanup of failed jobs.
        
        Args:
            job_id: UUID of the job
            
        Returns:
            Number of artifacts deleted
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM artifacts WHERE created_by_job_id = %s",
                (job_id,),
            )
            deleted = cursor.rowcount
            conn.commit()

        if deleted > 0:
            logger.info(f"Deleted {deleted} artifacts for job {job_id}")
        return deleted


# Singleton instance
_artifact_service: ArtifactService | None = None


def get_artifact_service() -> ArtifactService:
    """Factory function for ArtifactService singleton."""
    global _artifact_service
    if _artifact_service is None:
        _artifact_service = ArtifactService()
    return _artifact_service
