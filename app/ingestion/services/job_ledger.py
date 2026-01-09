"""
JobLedgerService: Service layer for job tracking and idempotency.

This service handles:
- Creating and tracking document processing jobs
- Idempotency checking (prevent duplicate processing)
- Dead Letter Queue for failed jobs
"""

import hashlib
import uuid
from datetime import datetime
from typing import Any

from loguru import logger

from shorui_core.infrastructure.postgres import get_db_connection


class JobLedgerService:
    """
    Service for tracking document processing jobs in PostgreSQL.

    This service:
    - Creates job records with status tracking
    - Provides idempotency via content hashing
    - Manages the Dead Letter Queue for failures

    Usage:
        service = JobLedgerService()
        job_id = service.create_job("project-1", "doc.pdf", "raw/...")
        service.update_status(job_id, "processing", progress=50)
        service.complete_job(job_id, items_indexed=1759)
    """

    def create_job(
        self,
        project_id: str,
        filename: str,
        storage_path: str,
        content_hash: str | None = None,
        job_id: str | None = None,
    ) -> str:
        """
        Create a new job record.

        Args:
            project_id: Project identifier.
            filename: Original filename.
            storage_path: MinIO storage path.
            content_hash: Optional hash for idempotency.
            job_id: Optional job ID (generates one if not provided).

        Returns:
            str: The job ID (provided or generated).
        """
        if job_id is None:
            job_id = str(uuid.uuid4())

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO ingestion_jobs
                (job_id, project_id, filename, storage_path, content_hash, status, progress, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job_id,
                    project_id,
                    filename,
                    storage_path,
                    content_hash,
                    "pending",
                    0,
                    datetime.utcnow(),
                ),
            )
            conn.commit()

        logger.info(f"Created job {job_id} for {filename}")
        return job_id

    def update_status(
        self, job_id: str, status: str, progress: int | None = None, error: str | None = None
    ) -> None:
        """
        Update the status of a job.

        Args:
            job_id: The job ID.
            status: New status (pending, processing, completed, failed).
            progress: Optional progress percentage (0-100).
            error: Optional error message.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE ingestion_jobs
                SET status = %s, progress = COALESCE(%s, progress),
                    error = COALESCE(%s, error), updated_at = %s
                WHERE job_id = %s
                """,
                (status, progress, error, datetime.utcnow(), job_id),
            )
            conn.commit()

        logger.debug(f"Updated job {job_id}: status={status}, progress={progress}")

    def complete_job(self, job_id: str, items_indexed: int) -> None:
        """
        Mark a job as completed.

        Args:
            job_id: The job ID.
            items_indexed: Number of items indexed.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'completed', progress = 100,
                    items_indexed = %s, completed_at = %s
                WHERE job_id = %s
                """,
                (items_indexed, datetime.utcnow(), job_id),
            )
            conn.commit()

        logger.info(f"Completed job {job_id} with {items_indexed} items indexed")

    def fail_job(self, job_id: str, error: str) -> None:
        """
        Mark a job as failed.

        Args:
            job_id: The job ID.
            error: Error message.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'failed', error = %s, failed_at = %s
                WHERE job_id = %s
                """,
                (error, datetime.utcnow(), job_id),
            )
            conn.commit()

        logger.error(f"Failed job {job_id}: {error}")

    def check_idempotency(
        self, project_id: str, filename: str, content_hash: str
    ) -> dict[str, Any] | None:
        """
        Check if a document has already been processed.

        Args:
            project_id: Project identifier.
            filename: Original filename.
            content_hash: Hash of the file content.

        Returns:
            dict: Existing job info if found, None otherwise.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT job_id, status, completed_at
                FROM ingestion_jobs
                WHERE project_id = %s AND content_hash = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (project_id, content_hash),
            )
            row = cursor.fetchone()

        if row:
            logger.info(f"Found existing job {row[0]} for content hash {content_hash[:8]}...")
            return {"job_id": row[0], "status": row[1], "completed_at": row[2]}

        return None

    def add_to_dlq(self, job_id: str, error: str, traceback: str | None = None) -> None:
        """
        Add a failed job to the Dead Letter Queue.

        Args:
            job_id: The job ID.
            error: Error message.
            traceback: Optional stack trace.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO dead_letter_queue
                (job_id, error, traceback, failed_at)
                VALUES (%s, %s, %s, %s)
                """,
                (job_id, error, traceback, datetime.utcnow()),
            )
            conn.commit()

        logger.warning(f"Added job {job_id} to DLQ: {error}")

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """
        Get job details by ID.

        Args:
            job_id: The job ID.

        Returns:
            dict: Job details if found, None otherwise.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT job_id, project_id, filename, storage_path,
                       status, progress, error, items_indexed,
                       created_at, completed_at, failed_at
                FROM ingestion_jobs
                WHERE job_id = %s
                """,
                (job_id,),
            )
            row = cursor.fetchone()

        if row:
            return {
                "job_id": row[0],
                "project_id": row[1],
                "filename": row[2],
                "storage_path": row[3],
                "status": row[4],
                "progress": row[5],
                "error": row[6],
                "items_indexed": row[7],
                "created_at": row[8],
                "completed_at": row[9],
                "failed_at": row[10],
            }

        return None

    @staticmethod
    def compute_content_hash(content: bytes) -> str:
        """
        Compute a hash of file content for idempotency.

        Args:
            content: File content as bytes.

        Returns:
            str: SHA-256 hash of the content.
        """
        return hashlib.sha256(content).hexdigest()
