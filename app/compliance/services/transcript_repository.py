"""
TranscriptRepository: CRUD operations for transcript records.

Stores transcript metadata and pointer to encrypted storage.
No PHI is stored in this table - raw text is in MinIO.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from shorui_core.infrastructure.postgres import get_db_connection


class TranscriptRepository:
    """
    Repository for transcript records in PostgreSQL.
    
    Stores metadata only - raw transcript text is encrypted in MinIO
    and referenced via storage_pointer.
    """

    def create(
        self,
        *,
        tenant_id: str,
        project_id: str,
        filename: str,
        storage_pointer: str,
        byte_size: Optional[int] = None,
        text_length: Optional[int] = None,
        file_hash: Optional[str] = None,
        job_id: Optional[str] = None,
        transcript_id: Optional[str] = None,
    ) -> str:
        """
        Create a new transcript record.
        
        Args:
            tenant_id: Tenant namespace
            project_id: Project identifier
            filename: Original filename (for display only)
            storage_pointer: MinIO path to encrypted text
            byte_size: Size of raw file in bytes
            text_length: Character count of text
            file_hash: SHA-256 of content
            job_id: Job that created this transcript
            transcript_id: Optional pre-generated ID
            
        Returns:
            transcript_id (UUID string)
        """
        tid = transcript_id or str(uuid.uuid4())

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO transcripts (
                    transcript_id, tenant_id, project_id, filename,
                    storage_pointer, byte_size, text_length, file_hash,
                    created_at, created_by_job_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    tid,
                    tenant_id,
                    project_id,
                    filename,
                    storage_pointer,
                    byte_size,
                    text_length,
                    file_hash,
                    datetime.utcnow(),
                    job_id,
                ),
            )
            conn.commit()

        logger.info(f"Created transcript {tid} for project={project_id}")
        return tid

    def get_by_id(self, transcript_id: str) -> dict[str, Any] | None:
        """Get transcript by ID."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT transcript_id, tenant_id, project_id, filename,
                       storage_pointer, byte_size, text_length, file_hash,
                       created_at, created_by_job_id
                FROM transcripts
                WHERE transcript_id = %s
                """,
                (transcript_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "transcript_id": str(row[0]),
            "tenant_id": row[1],
            "project_id": row[2],
            "filename": row[3],
            "storage_pointer": row[4],
            "byte_size": row[5],
            "text_length": row[6],
            "file_hash": row[7],
            "created_at": row[8],
            "created_by_job_id": str(row[9]) if row[9] else None,
        }

    def get_by_job_id(self, job_id: str) -> dict[str, Any] | None:
        """Get transcript created by a specific job."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT transcript_id, tenant_id, project_id, filename,
                       storage_pointer, byte_size, text_length, file_hash,
                       created_at, created_by_job_id
                FROM transcripts
                WHERE created_by_job_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (job_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "transcript_id": str(row[0]),
            "tenant_id": row[1],
            "project_id": row[2],
            "filename": row[3],
            "storage_pointer": row[4],
            "byte_size": row[5],
            "text_length": row[6],
            "file_hash": row[7],
            "created_at": row[8],
            "created_by_job_id": str(row[9]) if row[9] else None,
        }


def get_transcript_repository() -> TranscriptRepository:
    """Factory function for TranscriptRepository."""
    return TranscriptRepository()
