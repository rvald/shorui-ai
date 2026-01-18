from __future__ import annotations
"""
Protocols for the RAG (Retrieval-Augmented Generation) module.

These protocols define the interfaces for the key components of the RAG pipeline,
allowing for swappable implementations (e.g., different vector DBs, LLMs, or testing doubles).
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GenerativeModel(Protocol):
    """Protocol for LLM generation services."""

    async def generate(
        self, query: str, context: str | None = None, max_tokens: int = 2048
    ) -> dict[str, Any]:
        """
        Generate an answer for the given query and context.

        Args:
            query: The user's question.
            context: Retrieved context (optional).
            max_tokens: Maximum tokens in response.

        Returns:
            Dict containing the 'answer' and metadata.
        """
        ...


@runtime_checkable
class QueryAnalyzer(Protocol):
    """Protocol for query understanding and expansion."""

    async def process_async(self, query: str, expand_to_n: int = 3) -> dict[str, Any]:
        """
        Analyze the query to extract keywords, intent, and generate variations.

        Args:
            query: The user's search query.
            expand_to_n: Number of query variations to generate.

        Returns:
            Dict with 'keywords', 'intent', 'is_gap_query', 'expanded_queries'.
        """
        ...
    
    def process(self, query: str, expand_to_n: int = 3) -> dict[str, Any]:
        """Synchronous version of process_async."""
        ...


@runtime_checkable
class Reranker(Protocol):
    """Protocol for result reranking services."""

    def rerank(
        self, query: str, documents: list[dict[str, Any]], top_k: int = 5
    ) -> list[dict[str, Any]]:
        """
        Re-score and sort documents based on relevance to the query.

        Args:
            query: The search query.
            documents: List of document dicts.
            top_k: Number of documents to return.

        Returns:
            Reranked list of documents.
        """
        ...


@runtime_checkable
class GraphRetriever(Protocol):
    """Protocol for graph-based reasoning."""
    
    async def retrieve_and_reason(
        self, hits: list[dict[str, Any]], project_id: str, is_gap_query: bool = False
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Reason over search hits using the graph.

        Args:
            hits: Search results.
            project_id: Project identifier.
            is_gap_query: Whether to fetch all gaps.

        Returns:
            Tuple of (expanded_references, gap_report).
        """
        ...


@runtime_checkable
class Retriever(Protocol):
    """Protocol for the main retrieval pipeline."""

    async def retrieve(
        self,
        query: str,
        project_id: str,
        k: int = 5,
        expand_queries: int = 3,
        include_graph: bool = True,
        rerank: bool = True,
    ) -> dict[str, Any]:
        """
        Execute the full retrieval pipeline.

        Args:
            query: User's search query.
            project_id: Project for multi-tenancy.
            k: Number of final results.
            expand_queries: Number of query variations.
            include_graph: Whether to use graph reasoning.
            rerank: Whether to use reranking.

        Returns:
            Dict with 'documents' and pipeline metadata.
        """
        ...

    async def search(
        self, query: str, project_id: str, k: int = 5, score_threshold: float | None = None
    ) -> list[dict[str, Any]]:
        """Simple vector search (without full pipeline overhead)."""
        ...
