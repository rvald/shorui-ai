"""
Cleanup utilities for ingestion artifacts.

Removes raw upload artifacts older than a configured TTL from storage
and the artifacts registry.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from shorui_core.config import settings
from shorui_core.infrastructure.postgres import get_db_connection
from app.ingestion.services.storage import get_storage_backend


def cleanup_raw_uploads(ttl_days: Optional[int] = None, storage=None) -> dict:
    """
    Delete raw upload artifacts older than the TTL.

    Args:
        ttl_days: Override TTL in days (defaults to RAW_UPLOAD_TTL_DAYS setting).
        storage: Optional storage backend (for testing).

    Returns:
        dict: Summary of deleted artifacts.
    """
    ttl = ttl_days if ttl_days is not None else settings.RAW_UPLOAD_TTL_DAYS
    cutoff = datetime.utcnow() - timedelta(days=ttl)
    storage_backend = storage or get_storage_backend()

    deleted = 0
    failed = 0

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT artifact_id, storage_pointer
            FROM artifacts
            WHERE artifact_type = 'raw_upload'
              AND created_at < %s
            """,
            (cutoff,),
        )
        rows = cursor.fetchall()

        for artifact_id, storage_pointer in rows:
            try:
                storage_backend.delete(storage_pointer)
            except Exception as e:
                failed += 1
                logger.warning(f"Failed to delete storage object {storage_pointer}: {e}")
                continue

            cursor.execute(
                "DELETE FROM artifacts WHERE artifact_id = %s",
                (artifact_id,),
            )
            deleted += 1

        conn.commit()

    logger.info(f"Cleanup complete: deleted={deleted}, failed={failed}, cutoff={cutoff.isoformat()}")
    return {"deleted": deleted, "failed": failed, "cutoff": cutoff.isoformat()}
