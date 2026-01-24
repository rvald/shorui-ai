"""
Local filesystem storage backend.

This implementation stores files on the local filesystem,
useful for development and testing without MinIO.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from loguru import logger


class LocalStorage:
    """
    File-system based storage for local development.

    Stores files in a configurable base directory, organized
    by project_id. Provides the same interface as MinIO storage.

    Usage:
        storage = LocalStorage(base_path="/tmp/shorui-storage")
        path = storage.upload(content, "doc.pdf", "project-1")
        content = storage.download(path)
    """

    def __init__(self, base_path: str = "/tmp/shorui-storage"):
        """
        Initialize local storage.

        Args:
            base_path: Root directory for all stored files.
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.raw_bucket = "raw"
        self.processed_bucket = "processed"
        logger.info(f"LocalStorage initialized at {self.base_path}")

    def upload(
        self,
        content: bytes,
        filename: str,
        tenant_id: str,
        project_id: str,
        bucket: str | None = None,
        prefix: str | None = None,
    ) -> str:
        """
        Upload content to local filesystem.

        Args:
            content: The file content as bytes.
            filename: Original filename.
            tenant_id: Tenant namespace.
            project_id: Project identifier for organization.
            bucket: Optional bucket name (used as subdirectory).
            prefix: Optional prefix (e.g., "raw", "results").

        Returns:
            str: The storage path (bucket/prefix/tenant/project/uuid_filename).
        """
        bucket = bucket or "raw"

        # Create directory structure
        target_dir = self.base_path / bucket
        if prefix:
            target_dir = target_dir / prefix
        target_dir = target_dir / tenant_id / project_id
        target_dir.mkdir(parents=True, exist_ok=True)

        unique_id = str(uuid.uuid4())[:8]
        target_file = target_dir / f"{unique_id}_{filename}"

        target_file.write_bytes(content)

        components = [bucket, prefix, tenant_id, project_id, f"{unique_id}_{filename}"]
        storage_path = "/".join([c for c in components if c])
        logger.info(f"Uploaded to {storage_path}")

        return storage_path

    def upload_json(
        self,
        payload: dict,
        filename: str,
        tenant_id: str,
        project_id: str,
        bucket: str | None = None,
        prefix: str | None = None,
    ) -> str:
        import json

        content = json.dumps(payload).encode("utf-8")
        return self.upload(
            content=content,
            filename=filename,
            tenant_id=tenant_id,
            project_id=project_id,
            bucket=bucket,
            prefix=prefix,
        )

    def download(self, storage_path: str) -> bytes:
        """
        Download content from local filesystem.

        Args:
            storage_path: The path returned from upload().

        Returns:
            bytes: The file content.

        Raises:
            FileNotFoundError: If the file doesn't exist.
        """
        target_file = self.base_path / storage_path

        if not target_file.exists():
            raise FileNotFoundError(f"File not found: {storage_path}")

        logger.info(f"Downloaded from {storage_path}")
        return target_file.read_bytes()

    def delete(self, storage_path: str) -> None:
        """
        Delete content from local filesystem.

        Args:
            storage_path: The path to delete.
        """
        target_file = self.base_path / storage_path

        if target_file.exists():
            target_file.unlink()
            logger.info(f"Deleted {storage_path}")
        else:
            logger.warning(f"File not found for deletion: {storage_path}")
