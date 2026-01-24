"""
JobLedgerService: Canonical job/artifact ledger with idempotency.

Aligned with specs/component_pointer_based_ingestion.md and
specs/component_artifacts_and_jobs.md.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from shorui_core.config import settings
from shorui_core.infrastructure.postgres import get_db_connection

STORAGE_BACKEND = "local" if getattr(settings, "USE_LOCAL_STORAGE", False) else "minio"


class JobLedgerService:
    """
    Service for tracking jobs and artifacts in PostgreSQL.

    - Canonical jobs table with tenant/project scoping
    - Idempotency by SHA-256 of content + context
    - Artifact registry for raw and result pointers
    - DLQ integration for failures
    """

    # ---------------------------------------------------------------------
    # Job lifecycle
    # ---------------------------------------------------------------------
    def create_job(
        self,
        *,
        tenant_id: str,
        project_id: str,
        job_type: str,
        job_id: Optional[str] = None,
        status: str = "pending",
        progress: int = 0,
        idempotency_key: Optional[str] = None,
        request_id: Optional[str] = None,
        raw_pointer: Optional[str] = None,
        content_type: Optional[str] = None,
        document_type: Optional[str] = None,
        byte_size: Optional[int] = None,
        input_artifacts: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        job_uuid = job_id or str(uuid.uuid4())

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO jobs (
                    job_id, tenant_id, project_id, job_type, status, progress,
                    idempotency_key, request_id, raw_pointer, content_type,
                    document_type, byte_size, input_artifacts, created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    job_uuid,
                    tenant_id,
                    project_id,
                    job_type,
                    status,
                    progress,
                    idempotency_key,
                    request_id,
                    raw_pointer,
                    content_type,
                    document_type,
                    byte_size,
                    json.dumps(input_artifacts) if input_artifacts else None,
                    datetime.utcnow(),
                ),
            )
            conn.commit()

        logger.info(f"Created job {job_uuid} (type={job_type}) for project={project_id}")
        return job_uuid

    def update_status(
        self,
        job_id: str,
        status: str,
        progress: int | None = None,
        error_message: str | None = None,
        error_code: str | None = None,
    ) -> None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE jobs
                SET status = %s,
                    progress = COALESCE(%s, progress),
                    error_message_safe = COALESCE(%s, error_message_safe),
                    error_code = COALESCE(%s, error_code),
                    updated_at = %s
                WHERE job_id = %s
                """,
                (status, progress, error_message, error_code, datetime.utcnow(), job_id),
            )
            conn.commit()

        logger.debug(f"Updated job {job_id}: status={status}, progress={progress}")

    def complete_job(
        self,
        job_id: str,
        *,
        items_indexed: int = 0,
        result_pointer: Optional[str] = None,
        processed_pointer: Optional[str] = None,
        result_artifacts: Optional[list[dict[str, Any]]] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        result_json = json.dumps(result_artifacts) if result_artifacts else None

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE jobs
                SET status = 'completed',
                    progress = 100,
                    items_indexed = %s,
                    result_pointer = COALESCE(%s, result_pointer),
                    processed_pointer = COALESCE(%s, processed_pointer),
                    result_artifacts = COALESCE(%s, result_artifacts),
                    updated_at = %s,
                    completed_at = %s
                WHERE job_id = %s
                """,
                (
                    items_indexed,
                    result_pointer,
                    processed_pointer,
                    result_json,
                    datetime.utcnow(),
                    datetime.utcnow(),
                    job_id,
                ),
            )
            conn.commit()

        logger.info(f"Completed job {job_id} with {items_indexed} items indexed")

    def fail_job(
        self,
        job_id: str,
        *,
        error: str,
        error_code: str | None = None,
    ) -> None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE jobs
                SET status = 'failed',
                    error_message_safe = %s,
                    error_code = COALESCE(%s, error_code),
                    failed_at = %s,
                    updated_at = %s
                WHERE job_id = %s
                """,
                (error, error_code, datetime.utcnow(), datetime.utcnow(), job_id),
            )
            conn.commit()

        logger.error(f"Failed job {job_id}: {error}")

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT job_id, tenant_id, project_id, job_type, status,
                       progress, error_message_safe, items_indexed,
                       created_at, completed_at, failed_at,
                       raw_pointer, result_pointer, processed_pointer,
                       content_type, document_type, byte_size, result_artifacts,
                       input_artifacts
                FROM jobs
                WHERE job_id = %s
                """,
                (job_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        result_artifacts = row[17]
        if isinstance(result_artifacts, str):
            try:
                result_artifacts = json.loads(result_artifacts)
            except Exception:
                pass

        input_artifacts = row[18]
        if isinstance(input_artifacts, str):
            try:
                input_artifacts = json.loads(input_artifacts)
            except Exception:
                pass

        return {
            "job_id": row[0],
            "tenant_id": row[1],
            "project_id": row[2],
            "job_type": row[3],
            "status": row[4],
            "progress": row[5],
            "error": row[6],
            "items_indexed": row[7],
            "created_at": row[8],
            "completed_at": row[9],
            "failed_at": row[10],
            "raw_pointer": row[11],
            "result_pointer": row[12],
            "processed_pointer": row[13],
            "content_type": row[14],
            "document_type": row[15],
            "byte_size": row[16],
            "result_artifacts": result_artifacts,
            "input_artifacts": input_artifacts,
        }

    # ---------------------------------------------------------------------
    # Artifacts
    # ---------------------------------------------------------------------
    def register_artifact(
        self,
        *,
        tenant_id: str,
        project_id: str,
        artifact_type: str,
        storage_pointer: str,
        content_type: Optional[str] = None,
        byte_size: Optional[int] = None,
        sha256: Optional[str] = None,
        schema_version: Optional[str] = None,
        created_by_job_id: Optional[str] = None,
        storage_backend: Optional[str] = None,
    ) -> str:
        artifact_id = str(uuid.uuid4())

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO artifacts (
                    artifact_id, tenant_id, project_id, artifact_type,
                    storage_backend, storage_pointer, content_type,
                    byte_size, sha256, schema_version, created_at, created_by_job_id
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                """,
                (
                    artifact_id,
                    tenant_id,
                    project_id,
                    artifact_type,
                    storage_backend or STORAGE_BACKEND,
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

        return artifact_id

    # ---------------------------------------------------------------------
    # Idempotency helpers
    # ---------------------------------------------------------------------
    def check_idempotency(
        self,
        *,
        idempotency_key: str,
        job_type: str,
        tenant_id: str,
        project_id: str,
    ) -> dict[str, Any] | None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT job_id, status, result_pointer
                FROM jobs
                WHERE idempotency_key = %s
                  AND job_type = %s
                  AND tenant_id = %s
                  AND project_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (idempotency_key, job_type, tenant_id, project_id),
            )
            row = cursor.fetchone()

        if row:
            return {"job_id": row[0], "status": row[1], "result_pointer": row[2]}

        return None

    @staticmethod
    def compute_content_hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def build_idempotency_key(
        *,
        content_hash: str,
        tenant_id: str,
        project_id: str,
        document_type: str,
        content_type: str | None = None,
    ) -> str:
        base = f"{content_hash}:{tenant_id}:{project_id}:{document_type}"
        if content_type:
            base = f"{base}:{content_type}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    # ---------------------------------------------------------------------
    # DLQ
    # ---------------------------------------------------------------------
    def add_to_dlq(
        self,
        job_id: str,
        error: str,
        traceback: str | None = None,
    ) -> None:
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
