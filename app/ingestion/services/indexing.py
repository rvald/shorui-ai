"""
IndexingService: Service layer for vector database indexing.

This service handles indexing embedded chunks into the Qdrant vector
database, including collection management.
"""

from __future__ import annotations

import uuid
from typing import Any

from loguru import logger
from qdrant_client.models import Distance, PointStruct, VectorParams

# Import from shorui_core for infrastructure
from shorui_core.domain.interfaces import IndexerProtocol
from shorui_core.domain.exceptions import IndexingError
from shorui_core.infrastructure.qdrant import QdrantDatabaseConnector


class IndexingService(IndexerProtocol):
    """
    Service for indexing embeddings in Qdrant.

    This service:
    - Indexes chunks with embeddings into Qdrant
    - Manages collection creation
    - Supports configurable default collection

    Usage:
        service = IndexingService()
        service.index(chunks, embeddings, metadata, "my_collection")
    """

    def __init__(self, default_collection: str = "hipaa_regulations"):
        """
        Initialize the indexing service.

        Args:
            default_collection: Default collection name for indexing.
        """
        self.default_collection_name = default_collection
        self._client = None

    def _get_client(self):
        """Get the Qdrant client (lazy initialization)."""
        if self._client is None:
            self._client = QdrantDatabaseConnector.get_instance()
        return self._client

    def index(
        self,
        chunks: list[str],
        embeddings: list[list[float]],
        metadata: list[dict[str, Any]],
        collection_name: str | None = None,
        batch_size: int = 256,
    ) -> bool:
        """
        Index chunks with embeddings into Qdrant.

        Args:
            chunks: List of text chunks.
            embeddings: List of embedding vectors.
            metadata: List of metadata dicts for each chunk.
            collection_name: Target collection (uses default if not specified).
            batch_size: Number of points per batch (default 256).

        Returns:
            bool: True if indexing succeeded.
        """
        collection = collection_name or self.default_collection_name
        client = self._get_client()

        # Ensure collection exists
        if not self.collection_exists(collection):
            vector_size = len(embeddings[0]) if embeddings else 1024
            self.create_collection(collection, vector_size=vector_size)

        # Build points
        points = []
        for i, (chunk, embedding, meta) in enumerate(
            zip(chunks, embeddings, metadata, strict=False)
        ):
            point_id = str(uuid.uuid4())
            payload = {"content": chunk, "chunk_index": i, **meta}
            points.append(PointStruct(id=point_id, vector=embedding, payload=payload))

        # Upsert to Qdrant in batches
        total_points = len(points)
        logger.info(
            f"Indexing {total_points} points to collection '{collection}' in batches of {batch_size}"
        )

        try:
            for i in range(0, total_points, batch_size):
                batch = points[i : i + batch_size]
                client.upsert(collection_name=collection, points=batch)
                logger.debug(f"Indexed batch {i // batch_size + 1}: {len(batch)} points")

            logger.info(f"Successfully indexed {total_points} points")
            return True
        except Exception as e:
            logger.error(f"Failed to index documents: {e}")
            raise IndexingError(f"Failed to index documents: {e}") from e

    def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection exists in Qdrant.

        Args:
            collection_name: Name of the collection.

        Returns:
            bool: True if collection exists.
        """
        client = self._get_client()
        return client.collection_exists(collection_name)

    def create_collection(
        self, 
        collection_name: str, 
        vector_size: int = 1024, 
        distance: Distance = Distance.COSINE
    ) -> None:
        """
        Create a new collection in Qdrant.

        Args:
            collection_name: Name for the new collection.
            vector_size: Dimension of vectors.
            distance: Distance metric for similarity.
        """
        client = self._get_client()

        logger.info(f"Creating collection '{collection_name}' with dimension {vector_size}")

        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=distance),
        )
