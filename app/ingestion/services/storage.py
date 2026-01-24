"""
Storage backends for document persistence.

This module provides:
- MinIOStorage: Production storage using MinIO object storage
- get_storage_backend: Factory function to get the appropriate backend

The storage backend is selected based on the USE_LOCAL_STORAGE setting.
"""

from __future__ import annotations

import io
import uuid

from loguru import logger

from shorui_core.config import settings
from shorui_core.infrastructure.minio import get_minio_client

from .storage_protocol import StorageBackend


class MinIOStorage:
    """
    MinIO-based storage for production deployments.

    Stores documents in MinIO object storage with bucket organization.
    Implements the StorageBackend protocol.

    Usage:
        storage = MinIOStorage()
        path = storage.upload(content, "doc.pdf", "project-1")
        content = storage.download(path)
    """

    def __init__(self):
        """Initialize the MinIO storage service."""
        self._client = get_minio_client()
        self.raw_bucket = settings.MINIO_BUCKET_RAW
        self.processed_bucket = settings.MINIO_BUCKET_PROCESSED

        # Ensure buckets exist
        self.ensure_bucket_exists(self.raw_bucket)
        self.ensure_bucket_exists(self.processed_bucket)

    def ensure_bucket_exists(self, bucket_name: str) -> None:
        """Create bucket if it doesn't exist."""
        try:
            if not self._client.bucket_exists(bucket_name):
                self._client.make_bucket(bucket_name)
                logger.info(f"Created MinIO bucket '{bucket_name}'")
        except Exception as e:
            logger.warning(f"Could not ensure bucket '{bucket_name}' exists: {e}")

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
        Upload content to MinIO.

        Args:
            content: The file content as bytes.
            filename: Original filename.
            tenant_id: Tenant namespace.
            project_id: Project identifier.
            bucket: Target bucket (defaults to raw bucket).
            prefix: Optional prefix inside the bucket (e.g., "raw", "results").

        Returns:
            str: The storage path (bucket/prefix/tenant/project/uuid_filename).
        """
        bucket = bucket or self.raw_bucket

        unique_id = str(uuid.uuid4())[:8]
        components = [prefix, tenant_id, project_id, f"{unique_id}_{filename}"]
        object_name = "/".join([c for c in components if c])

        # Upload to MinIO
        content_stream = io.BytesIO(content)
        content_length = len(content)

        logger.info(f"Uploading document to {bucket}/{object_name}")

        self._client.put_object(
            bucket_name=bucket,
            object_name=object_name,
            data=content_stream,
            length=content_length,
        )

        # Return the full path
        storage_path = f"{bucket}/{object_name}"
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
        """Upload JSON payload as bytes."""
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
        Download a document from MinIO.

        Args:
            storage_path: The path returned from upload() (bucket/object_name).

        Returns:
            bytes: The file content.

        Raises:
            Exception: If the file is not found.
        """
        # Parse bucket and object_name from path
        parts = storage_path.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid storage path: {storage_path}")

        bucket_name, object_name = parts

        logger.info(f"Downloading {storage_path}")

        response = self._client.get_object(bucket_name, object_name)
        try:
            content = response.read()
        finally:
            response.close()
            response.release_conn()

        return content

    def delete(self, storage_path: str) -> None:
        """
        Delete a document from MinIO.

        Args:
            storage_path: The path to delete.
        """
        parts = storage_path.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid storage path: {storage_path}")

        bucket_name, object_name = parts

        logger.info(f"Deleting {storage_path}")
        self._client.remove_object(bucket_name, object_name)


# Backward compatibility alias
StorageService = MinIOStorage


def get_storage_backend() -> StorageBackend:
    """
    Factory function to get the appropriate storage backend.

    Uses LOCAL_STORAGE setting to determine which backend to use.
    Defaults to MinIO for production.

    Returns:
        StorageBackend: The configured storage backend instance.
    """
    use_local = getattr(settings, "USE_LOCAL_STORAGE", False)

    if use_local:
        from .local_storage import LocalStorage

        logger.info("Using LocalStorage backend")
        return LocalStorage()
    else:
        logger.info("Using MinIOStorage backend")
        return MinIOStorage()
