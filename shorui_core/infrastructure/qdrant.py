"""
Qdrant client connector for shorui-ai.

This module provides a singleton Qdrant client that can be shared
across all services. It supports both local and cloud Qdrant deployments.
"""

from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

from shorui_core.config import settings


class QdrantDatabaseConnector:
    """
    Singleton connector for Qdrant vector database.

    Supports both local and cloud deployments based on settings.

    Usage:
        client = QdrantDatabaseConnector.get_instance()
        client.search(collection_name="my_collection", ...)
    """

    _instance: QdrantClient | None = None

    @classmethod
    def get_instance(cls) -> QdrantClient:
        """
        Get or create the Qdrant client instance.

        Returns:
            QdrantClient: The Qdrant client instance.

        Raises:
            UnexpectedResponse: If connection to Qdrant fails.
        """
        if cls._instance is None:
            try:
                if settings.USE_QDRANT_CLOUD:
                    cls._instance = QdrantClient(
                        url=settings.QDRANT_CLOUD_URL,
                        api_key=settings.QDRANT_APIKEY,
                    )
                    uri = settings.QDRANT_CLOUD_URL
                else:
                    cls._instance = QdrantClient(
                        host=settings.QDRANT_DATABASE_HOST,
                        port=settings.QDRANT_DATABASE_PORT,
                    )
                    uri = f"{settings.QDRANT_DATABASE_HOST}:{settings.QDRANT_DATABASE_PORT}"

                logger.info(f"Connected to Qdrant at {uri}")
            except UnexpectedResponse:
                logger.exception(
                    "Couldn't connect to Qdrant.",
                    host=settings.QDRANT_DATABASE_HOST,
                    port=settings.QDRANT_DATABASE_PORT,
                    url=settings.QDRANT_CLOUD_URL,
                )
                raise

        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """
        Reset the singleton instance.

        Useful for testing or reconnection scenarios.
        """
        cls._instance = None


# Convenience: module-level connection (lazy instantiation)
def get_connection() -> QdrantClient:
    """Get the Qdrant client connection."""
    return QdrantDatabaseConnector.get_instance()
