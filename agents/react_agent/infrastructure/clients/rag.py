"""
RAG Service HTTP Clients.
"""
from __future__ import annotations

import os
from typing import Any, Optional
import httpx

from .base import ServiceStatus

# Configuration
RAG_BASE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8082/rag")
DEFAULT_TIMEOUT = 60.0

DEFAULT_POOL_LIMITS = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=30.0,
)

class RAGClient:
    """
    Synchronous client for the RAG (Retrieval-Augmented Generation) Service.
    """
    
    def __init__(self, base_url: str = RAG_BASE_URL, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
    
    def search(
        self,
        query: str,
        project_id: str,
        k: int = 5,
    ) -> dict[str, Any]:
        """
        RETRIEVAL ONLY: Semantic search over documents without LLM generation.
        """
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/search",
                params={
                    "query": query,
                    "project_id": project_id,
                    "k": k,
                },
            )
            response.raise_for_status()
            return response.json()
    
    def query(
        self,
        query: str,
        project_id: str,
        k: int = 5,
        backend: str = "openai",
    ) -> dict[str, Any]:
        """
        FULL RAG: Retrieve documents and generate an AI answer.
        """
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/query",
                json={
                    "query": query,
                    "project_id": project_id,
                    "k": k,
                    "backend": backend,
                },
            )
            response.raise_for_status()
            return response.json()
    
    def health_check(self) -> ServiceStatus:
        """Check if RAG service is healthy."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/health")
                response.raise_for_status()
                return ServiceStatus(name="rag", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="rag", healthy=False, message=str(e))


class RegulationRetriever:
    """
    Client for retrieving HIPAA regulations from the RAG service.
    """
    
    def __init__(self, rag_client: Optional[RAGClient] = None):
        self._client = rag_client or RAGClient()
    
    def search_regulations(
        self,
        query: str,
        k: int = 5,
        project_id: str = "hipaa_regulations",
    ) -> list[dict[str, Any]]:
        """
        Search for relevant HIPAA regulations.
        """
        result = self._client.search(
            query=query,
            project_id=project_id,
            k=k,
        )
        return result.get("results", [])
    
    def get_regulation_context(
        self,
        query: str,
        k: int = 3,
        project_id: str = "hipaa_regulations",
    ) -> str:
        """
        Get formatted regulation context for RAG.
        """
        results = self.search_regulations(query, k, project_id)
        
        if not results:
            return "No relevant HIPAA regulations found."
        
        sections = []
        for i, result in enumerate(results, 1):
            content = result.get("content", "")
            filename = result.get("filename", "Unknown")
            sections.append(f"[{i}] {filename}:\n{content}")
        
        return "\n\n---\n\n".join(sections)


class AsyncRAGClient:
    """
    Async client for the RAG Service with connection pooling.
    """
    
    def __init__(
        self,
        base_url: str = RAG_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        limits: Optional[httpx.Limits] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits or DEFAULT_POOL_LIMITS,
        )
    
    async def close(self) -> None:
        """Close the HTTP client and release connections."""
        await self._client.aclose()
    
    async def __aenter__(self) -> "AsyncRAGClient":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self.close()
    
    async def search(
        self,
        query: str,
        project_id: str,
        k: int = 5,
    ) -> dict[str, Any]:
        """
        Semantic search over documents asynchronously.
        """
        response = await self._client.get(
            f"{self.base_url}/search",
            params={
                "query": query,
                "project_id": project_id,
                "k": k,
            },
        )
        response.raise_for_status()
        return response.json()
    
    async def query(
        self,
        query: str,
        project_id: str,
        k: int = 5,
        backend: str = "openai",
    ) -> dict[str, Any]:
        """
        Full RAG query - retrieve + generate answer asynchronously.
        """
        response = await self._client.post(
            f"{self.base_url}/query",
            json={
                "query": query,
                "project_id": project_id,
                "k": k,
                "backend": backend,
            },
        )
        response.raise_for_status()
        return response.json()
    
    async def health_check(self) -> ServiceStatus:
        """Check if RAG service is healthy asynchronously."""
        try:
            response = await self._client.get(
                f"{self.base_url}/health",
                timeout=5.0,
            )
            response.raise_for_status()
            return ServiceStatus(name="rag", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="rag", healthy=False, message=str(e))


class AsyncRegulationRetriever:
    """
    Async client for retrieving HIPAA regulations from the RAG service.
    """
    
    def __init__(self, rag_client: Optional[AsyncRAGClient] = None):
        self._client = rag_client or AsyncRAGClient()
        self._owns_client = rag_client is None
    
    async def close(self) -> None:
        """Close the underlying client if we own it."""
        if self._owns_client:
            await self._client.close()
    
    async def __aenter__(self) -> "AsyncRegulationRetriever":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self.close()
    
    async def search_regulations(
        self,
        query: str,
        k: int = 5,
        project_id: str = "hipaa_regulations",
    ) -> list[dict[str, Any]]:
        """
        Search for relevant HIPAA regulations asynchronously.
        """
        result = await self._client.search(
            query=query,
            project_id=project_id,
            k=k,
        )
        return result.get("results", [])
    
    async def get_regulation_context(
        self,
        query: str,
        k: int = 3,
        project_id: str = "hipaa_regulations",
    ) -> str:
        """
        Get formatted regulation context for RAG asynchronously.
        """
        results = await self.search_regulations(query, k, project_id)
        
        if not results:
            return "No relevant HIPAA regulations found."
        
        sections = []
        for i, result in enumerate(results, 1):
            content = result.get("content", "")
            filename = result.get("filename", "Unknown")
            sections.append(f"[{i}] {filename}:\n{content}")
        
        return "\n\n---\n\n".join(sections)
