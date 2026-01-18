from __future__ import annotations
"""
Reranking service implementing the Reranker protocol.
"""

from typing import Any

from loguru import logger

from app.rag.protocols import Reranker
from shorui_core.config import settings

try:
    from sentence_transformers import CrossEncoder

    HAS_CROSS_ENCODER = True
except ImportError:
    CrossEncoder = None
    HAS_CROSS_ENCODER = False


class CrossEncoderReranker(Reranker):
    """
    Reranker implementation using CrossEncoder.
    """

    _model_instance = None  # Singleton to avoid reloading model

    def __init__(self, model_name: str = None):
        """
        Initialize the reranker.

        Args:
            model_name: CrossEncoder model to use (defaults to config).
        """
        self._model_name = model_name or settings.RERANKING_CROSS_ENCODER_MODEL_ID

    def _get_model(self):
        """Get or create the CrossEncoder model (singleton)."""
        if CrossEncoderReranker._model_instance is None:
            if not HAS_CROSS_ENCODER:
                raise ImportError("sentence-transformers is required for CrossEncoderReranker")

            logger.info(f"Loading CrossEncoder model: {self._model_name}")
            CrossEncoderReranker._model_instance = CrossEncoder(self._model_name)

        return CrossEncoderReranker._model_instance

    def rerank(
        self, query: str, documents: list[dict[str, Any]], top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Rerank documents by relevance to the query."""
        if not documents:
            return []

        logger.info(f"Reranking {len(documents)} documents for query: '{query[:50]}...'")

        model = self._get_model()

        # Build query-document pairs
        pairs = [(query, doc.get("content", "")) for doc in documents]

        # Score all pairs
        scores = model.predict(pairs)

        # Combine scores with documents
        scored_docs = list(zip(scores, documents, strict=False))

        # Sort by score descending
        scored_docs.sort(key=lambda x: x[0], reverse=True)

        # Take top_k and add scores to documents
        reranked = []
        for score, doc in scored_docs[:top_k]:
            reranked.append({**doc, "rerank_score": float(score)})

        logger.info(f"Reranking complete, returning top {len(reranked)} documents")

        return reranked
