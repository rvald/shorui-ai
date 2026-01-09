"""
RerankerService: Post-retrieval reranking of search results.

Uses a CrossEncoder model to score query-document pairs
and reorder results by relevance.
"""

from typing import Any

from loguru import logger

from shorui_core.config import settings

try:
    from sentence_transformers import CrossEncoder

    HAS_CROSS_ENCODER = True
except ImportError:
    CrossEncoder = None
    HAS_CROSS_ENCODER = False


class RerankerService:
    """
    Post-retrieval reranking service using CrossEncoder.

    The CrossEncoder scores query-document pairs more accurately
    than bi-encoder similarity, improving retrieval quality.

    Usage:
        reranker = RerankerService()
        reranked = reranker.rerank("query", documents, top_k=5)
    """

    _model_instance = None  # Singleton to avoid reloading model

    def __init__(self, mock: bool = False, model_name: str = None):
        """
        Initialize the reranker service.

        Args:
            mock: If True, skip actual reranking.
            model_name: CrossEncoder model to use (defaults to config).
        """
        self._mock = mock
        self._model_name = model_name or settings.RERANKING_CROSS_ENCODER_MODEL_ID

    def _get_model(self):
        """Get or create the CrossEncoder model (singleton)."""
        if RerankerService._model_instance is None:
            if not HAS_CROSS_ENCODER:
                raise ImportError("sentence-transformers is required for RerankerService")

            logger.info(f"Loading CrossEncoder model: {self._model_name}")
            RerankerService._model_instance = CrossEncoder(self._model_name)

        return RerankerService._model_instance

    def rerank(
        self, query: str, documents: list[dict[str, Any]], top_k: int = 5
    ) -> list[dict[str, Any]]:
        """
        Rerank documents by relevance to the query.

        Args:
            query: The search query.
            documents: List of document dicts (must have 'content' key).
            top_k: Number of documents to return.

        Returns:
            List of documents sorted by relevance, with rerank_score added.
        """
        if not documents:
            return []

        if self._mock:
            # In mock mode, just add placeholder scores and return as-is
            return [
                {**doc, "rerank_score": 1.0 - i * 0.1} for i, doc in enumerate(documents[:top_k])
            ]

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
