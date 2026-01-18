"""
EmbeddingService: Service layer for text embedding generation.

This service handles generating embeddings for text chunks using
a configured embedding model (e5-large by default).
"""

from loguru import logger

from shorui_core.domain.interfaces import EmbedderProtocol
from shorui_core.domain.exceptions import EmbeddingError
from shorui_core.infrastructure.embeddings import EmbeddingModelSingleton


class EmbeddingService(EmbedderProtocol):
    """
    Service for generating text embeddings.

    This service:
    - Uses a singleton embedding model for efficiency
    - Supports batch embedding generation
    - Exposes model metadata

    Usage:
        service = EmbeddingService()
        embeddings = service.embed(["text1", "text2"])
    """

    def __init__(self):
        """Initialize the embedding service."""
        self._model = EmbeddingModelSingleton()

    @property
    def model_id(self) -> str:
        """Get the embedding model identifier."""
        return self._model.model_id

    @property
    def embedding_dimension(self) -> int:
        """Get the embedding vector dimension."""
        return self._model.embedding_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            list: List of embedding vectors (each is a list of floats).
        """
        if not texts:
            return []

        logger.debug(f"Generating embeddings for {len(texts)} texts")

        try:
            # The singleton model is callable and accepts a list
            embeddings = self._model(texts)

            logger.debug(
                f"Generated {len(embeddings)} embeddings of dimension {len(embeddings[0]) if embeddings else 0}"
            )

            return embeddings
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise EmbeddingError(f"Failed to generate embeddings: {e}") from e
