"""
RAG Service HTTP Client.

Provides async client for RAG (Retrieval-Augmented Generation) operations
using the ServiceHttpClient from shorui_core.runtime.
"""

from __future__ import annotations

import os
from typing import Any

from shorui_core.runtime import RunContext, ServiceHttpClient, RetryPolicy

from .base import ServiceStatus, default_context

# Configuration
RAG_BASE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8082/rag")
DEFAULT_TIMEOUT = 60.0

# Health checks should fail fast, no retry
HEALTH_CHECK_POLICY = RetryPolicy(max_attempts=1, base_delay=0.0)


class RAGClient:
    """Async client for the RAG (Retrieval-Augmented Generation) Service.

    Uses ServiceHttpClient for connection pooling, automatic header injection,
    and retry on transient failures.

    Example:
        async with RAGClient() as client:
            result = await client.query("What is HIPAA?", "hipaa_docs")
    """

    def __init__(
        self,
        base_url: str = RAG_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """Initialize the RAG client.

        Args:
            base_url: Base URL of the RAG service.
            timeout: Request timeout in seconds.
        """
        self._http = ServiceHttpClient(
            base_url=base_url,
            timeout=timeout,
        )

    async def close(self) -> None:
        """Close the HTTP client and release connections."""
        await self._http.close()

    async def __aenter__(self) -> "RAGClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager."""
        await self.close()

    async def search(
        self,
        query: str,
        project_id: str,
        k: int = 5,
        context: RunContext | None = None,
    ) -> dict[str, Any]:
        """Semantic search over documents without LLM generation.

        Args:
            query: Search query text.
            project_id: Project to search within.
            k: Number of results to return.
            context: Optional RunContext for correlation ID propagation.

        Returns:
            Search results with matched documents.
        """
        ctx = context or default_context()
        response = await self._http.get(
            "/search",
            ctx,
            params={
                "query": query,
                "project_id": project_id,
                "k": k,
            },
        )
        return response.json()

    async def query(
        self,
        query: str,
        project_id: str,
        k: int = 5,
        backend: str = "openai",
        context: RunContext | None = None,
    ) -> dict[str, Any]:
        """Full RAG: retrieve documents and generate an AI answer.

        Args:
            query: Question to answer.
            project_id: Project containing documents.
            k: Number of documents to retrieve.
            backend: LLM backend to use ("openai" or "runpod").
            context: Optional RunContext for correlation ID propagation.

        Returns:
            Generated answer with source citations.
        """
        ctx = context or default_context()
        response = await self._http.post(
            "/query",
            ctx,
            json={
                "query": query,
                "project_id": project_id,
                "k": k,
                "backend": backend,
            },
        )
        return response.json()

    async def health_check(self) -> ServiceStatus:
        """Check if RAG service is healthy.

        Returns:
            ServiceStatus indicating health state.
        """
        try:
            # Use a minimal context for health checks
            ctx = default_context()
            # Create a separate client with no retry for health checks
            health_http = ServiceHttpClient(
                base_url=self._http.base_url,
                timeout=5.0,
                retry_policy=HEALTH_CHECK_POLICY,
            )
            try:
                response = await health_http.get("/health", ctx)
                response.raise_for_status()
                return ServiceStatus(name="rag", healthy=True, message="OK")
            finally:
                await health_http.close()
        except Exception as e:
            return ServiceStatus(name="rag", healthy=False, message=str(e))


class RegulationRetriever:
    """Client for retrieving HIPAA regulations from the RAG service."""

    def __init__(self, rag_client: RAGClient | None = None):
        """Initialize the regulation retriever.

        Args:
            rag_client: Optional RAGClient to use. Creates one if not provided.
        """
        self._client = rag_client or RAGClient()
        self._owns_client = rag_client is None

    async def close(self) -> None:
        """Close the underlying client if we own it."""
        if self._owns_client:
            await self._client.close()

    async def __aenter__(self) -> "RegulationRetriever":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager."""
        await self.close()

    async def search_regulations(
        self,
        query: str,
        k: int = 5,
        project_id: str = "hipaa_regulations",
        context: RunContext | None = None,
    ) -> list[dict[str, Any]]:
        """Search for relevant HIPAA regulations.

        Args:
            query: Search query.
            k: Number of results.
            project_id: Project containing regulations.
            context: Optional RunContext for correlation.

        Returns:
            List of matching regulation documents.
        """
        result = await self._client.search(
            query=query,
            project_id=project_id,
            k=k,
            context=context,
        )
        return result.get("results", [])

    async def get_regulation_context(
        self,
        query: str,
        k: int = 3,
        project_id: str = "hipaa_regulations",
        context: RunContext | None = None,
    ) -> str:
        """Get formatted regulation context for RAG.

        Args:
            query: Search query.
            k: Number of regulations to retrieve.
            project_id: Project containing regulations.
            context: Optional RunContext for correlation.

        Returns:
            Formatted string with numbered regulation excerpts.
        """
        results = await self.search_regulations(query, k, project_id, context)

        if not results:
            return "No relevant HIPAA regulations found."

        sections = []
        for i, result in enumerate(results, 1):
            content = result.get("content", "")
            filename = result.get("filename", "Unknown")
            sections.append(f"[{i}] {filename}:\n{content}")

        return "\n\n---\n\n".join(sections)


# Legacy aliases for backward compatibility
AsyncRAGClient = RAGClient
AsyncRegulationRetriever = RegulationRetriever
