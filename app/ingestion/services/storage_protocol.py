"""
Storage backend protocol for document persistence.

This module defines the abstract interface for storage backends,
enabling different implementations (MinIO, local filesystem, S3)
to be used interchangeably.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """
    Abstract storage interface for document persistence.

    All storage backends must implement these methods to be compatible
    with the ingestion services.
    """

    def upload(
        self,
        content: bytes,
        filename: str,
        project_id: str,
        bucket: str | None = None,
    ) -> str:
        """
        Upload content and return storage path.

        Args:
            content: The file content as bytes.
            filename: Original filename.
            project_id: Project identifier for organization.
            bucket: Optional target bucket/container.

        Returns:
            str: The storage path for retrieval.
        """
        ...

    def download(self, storage_path: str) -> bytes:
        """
        Download content by path.

        Args:
            storage_path: The path returned from upload().

        Returns:
            bytes: The file content.
        """
        ...

    def delete(self, storage_path: str) -> None:
        """
        Delete content by path.

        Args:
            storage_path: The path to delete.
        """
        ...
