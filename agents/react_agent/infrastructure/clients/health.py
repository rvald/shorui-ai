"""
Health Check HTTP Clients.
"""
from __future__ import annotations
import httpx
from .base import ServiceStatus
from .ingestion import INGESTION_BASE_URL
from .rag import RAG_BASE_URL

class HealthClient:
    """
    Synchronous client for checking backend service health.
    """
    
    def __init__(
        self,
        ingestion_url: str = INGESTION_BASE_URL,
        rag_url: str = RAG_BASE_URL,
        timeout: float = 5.0,
    ):
        self.ingestion_url = ingestion_url.rstrip("/")
        self.rag_url = rag_url.rstrip("/")
        self.timeout = timeout
    
    def check_all(self) -> dict[str, ServiceStatus]:
        """Check health of all backend services."""
        return {
            "ingestion": self.check_ingestion(),
            "rag": self.check_rag(),
        }
    
    def check_ingestion(self) -> ServiceStatus:
        """Check ingestion service health."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(f"{self.ingestion_url}/health")
                response.raise_for_status()
                return ServiceStatus(name="ingestion", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="ingestion", healthy=False, message=str(e))
    
    def check_rag(self) -> ServiceStatus:
        """Check RAG service health."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(f"{self.rag_url}/health")
                response.raise_for_status()
                return ServiceStatus(name="rag", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="rag", healthy=False, message=str(e))


class AsyncHealthClient:
    """
    Async client for checking backend service health.
    """
    
    def __init__(
        self,
        ingestion_url: str = INGESTION_BASE_URL,
        rag_url: str = RAG_BASE_URL,
        timeout: float = 5.0,
    ):
        self.ingestion_url = ingestion_url.rstrip("/")
        self.rag_url = rag_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
        
    async def __aenter__(self) -> "AsyncHealthClient":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self.close()
    
    async def check_all(self) -> dict[str, ServiceStatus]:
        """Check health of all backend services asynchronously."""
        return {
            "ingestion": await self.check_ingestion(),
            "rag": await self.check_rag(),
        }

    async def check_ingestion(self) -> ServiceStatus:
        """Check ingestion service health."""
        try:
            response = await self._client.get(f"{self.ingestion_url}/health")
            response.raise_for_status()
            return ServiceStatus(name="ingestion", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="ingestion", healthy=False, message=str(e))

    async def check_rag(self) -> ServiceStatus:
        """Check RAG service health."""
        try:
            response = await self._client.get(f"{self.rag_url}/health")
            response.raise_for_status()
            return ServiceStatus(name="rag", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="rag", healthy=False, message=str(e))
