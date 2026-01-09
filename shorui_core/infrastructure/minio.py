"""
MinIO client connector for shorui-ai.

This module provides a singleton MinIO client that can be shared
across all services that need object storage access.
"""

from loguru import logger
from minio import Minio

from shorui_core.config import settings


class MinioClientConnector:
    """
    Singleton connector for MinIO object storage.

    Usage:
        client = MinioClientConnector.get_instance()
        client.put_object(bucket_name="raw", ...)
    """

    _instance: Minio | None = None

    @classmethod
    def get_instance(cls) -> Minio:
        """
        Get or create the MinIO client instance.

        Returns:
            Minio: The MinIO client instance.
        """
        if cls._instance is None:
            try:
                cls._instance = Minio(
                    endpoint=settings.MINIO_ENDPOINT,
                    access_key=settings.MINIO_ACCESS_KEY,
                    secret_key=settings.MINIO_SECRET_KEY,
                    secure=settings.MINIO_SECURE,
                )
                logger.info(f"Connected to MinIO at '{settings.MINIO_ENDPOINT}'")
            except Exception as e:
                logger.error(f"Failed to connect to MinIO at '{settings.MINIO_ENDPOINT}': {e}")
                raise

        return cls._instance


def get_minio_client() -> Minio:
    """
    Convenience function to get the MinIO client.

    Returns:
        Minio: The MinIO client instance.
    """
    return MinioClientConnector.get_instance()
