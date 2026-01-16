"""
HTTP Client Infrastructure

HTTP clients for communicating with Shorui AI backend services.
Includes both synchronous and asynchronous implementations.

Sync clients: Use for simple scripts or sync contexts
Async clients: Use for FastAPI routes and async agents (with connection pooling)
"""
from __future__ import annotations

import os
from typing import Any, Optional
from contextlib import asynccontextmanager

import httpx
import aiofiles
from pydantic import BaseModel, Field


# Configuration from environment
INGESTION_BASE_URL = os.getenv("INGESTION_SERVICE_URL", "http://localhost:8082/ingest")
RAG_BASE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8082/rag")
DEFAULT_TIMEOUT = 60.0


class ServiceStatus(BaseModel):
    """Status of a backend service."""
    name: str
    healthy: bool
    message: str = ""


class IngestionClient:
    """
    Synchronous client for the Ingestion Service.
    
    Handles document uploads, clinical transcript analysis,
    and audit log queries.
    """
    
    def __init__(self, base_url: str = INGESTION_BASE_URL, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
    
    def upload_document(
        self,
        file_path: str,
        project_id: str,
        category: Optional[str] = None,
        document_type: str = "general",
    ) -> dict[str, Any]:
        """
        Upload a document for processing.
        
        Args:
            file_path: Local path to the file
            project_id: Tenant/project identifier
            category: Optional category (e.g., "policy", "regulation")
            document_type: Type of document ("general" or "hipaa_regulation")
            
        Returns:
            dict with job_id and message
        """
        with httpx.Client(timeout=self.timeout) as client:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                data = {
                    "project_id": project_id,
                    "document_type": document_type,
                }
                if category:
                    data["category"] = category
                    
                response = client.post(
                    f"{self.base_url}/documents",
                    files=files,
                    data=data,
                )
                response.raise_for_status()
                return response.json()
    
    def check_status(self, job_id: str) -> dict[str, Any]:
        """
        Check the status of an upload job.
        
        Args:
            job_id: The job ID from upload
            
        Returns:
            dict with status, progress, and result
        """
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/documents/{job_id}/status")
            response.raise_for_status()
            return response.json()
    
    def analyze_transcript(
        self,
        file_path: str,
        project_id: str,
    ) -> dict[str, Any]:
        """
        Submit a clinical transcript for PHI detection.
        
        Args:
            file_path: Path to the transcript file
            project_id: Project identifier
            
        Returns:
            dict with job_id for polling
        """
        with httpx.Client(timeout=self.timeout) as client:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                data = {"project_id": project_id}
                
                response = client.post(
                    f"{self.base_url}/clinical-transcripts",
                    files=files,
                    data=data,
                )
                response.raise_for_status()
                return response.json()
    
    def get_transcript_job_status(self, job_id: str) -> dict[str, Any]:
        """Check status of a transcript analysis job."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/clinical-transcripts/jobs/{job_id}"
            )
            response.raise_for_status()
            return response.json()
    
    def get_compliance_report(
        self,
        transcript_id: str,
        project_id: str = "default",
    ) -> dict[str, Any]:
        """
        Get compliance report for a transcript.
        
        Args:
            transcript_id: ID of the analyzed transcript
            project_id: Project identifier
            
        Returns:
            Full compliance report dict
        """
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/clinical-transcripts/{transcript_id}/compliance-report",
                params={"project_id": project_id},
            )
            response.raise_for_status()
            return response.json()
    
    def query_audit_log(
        self,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Query the HIPAA audit log.
        
        Args:
            event_type: Filter by event type (e.g., "PHI_DETECTED")
            limit: Maximum number of events
            
        Returns:
            dict with events list and total count
        """
        with httpx.Client(timeout=self.timeout) as client:
            params = {"limit": limit}
            if event_type:
                params["event_type"] = event_type
                
            response = client.get(
                f"{self.base_url}/audit-log",
                params=params,
            )
            response.raise_for_status()
            return response.json()
    
    def health_check(self) -> ServiceStatus:
        """Check if ingestion service is healthy."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/health")
                response.raise_for_status()
                return ServiceStatus(name="ingestion", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="ingestion", healthy=False, message=str(e))


class RAGClient:
    """
    Synchronous client for the RAG (Retrieval-Augmented Generation) Service.
    
    Provides two main methods:
    - search(): Retrieval-only, returns raw documents (free, fast, for debugging)
    - query(): Full RAG, returns AI-generated answer (costs tokens, slower)
    
    For agent tools, use query() to get grounded answers.
    For debugging retrieval quality, use search().
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
        
        Use this for:
        - Debugging retrieval quality
        - Exploring indexed documents
        - Building custom RAG pipelines
        
        For AI-generated answers, use query() instead.
        
        Args:
            query: Natural language query
            project_id: Project identifier
            k: Number of results to return
            
        Returns:
            dict with 'results' list containing document chunks
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
        
        This is the primary method for agent tools. It:
        1. Searches for relevant documents in Qdrant
        2. Passes them as context to the LLM
        3. Returns a grounded answer with sources
        
        Args:
            query: Natural language question
            project_id: Project identifier (e.g., 'default', 'hipaa_regulations')
            k: Number of documents to retrieve for context
            backend: LLM backend ('openai' or 'runpod')
            
        Returns:
            dict with 'answer' (str) and 'sources' (list)
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
    
    Uses semantic search to find relevant regulation sections.
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
        
        Args:
            query: Natural language query about regulations
            k: Number of results
            project_id: Project containing regulations
            
        Returns:
            List of matching regulation sections
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
        
        Args:
            query: Query to find relevant regulations
            k: Number of regulation sections to include
            project_id: Project containing regulations
            
        Returns:
            Formatted string with regulation excerpts
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


# =============================================================================
# ASYNC HTTP CLIENTS
# =============================================================================

# Connection pool limits for async clients
DEFAULT_POOL_LIMITS = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=30.0,
)


class AsyncIngestionClient:
    """
    Async client for the Ingestion Service with connection pooling.
    
    Use as context manager or call close() when done:
    
    ```python
    async with AsyncIngestionClient() as client:
        result = await client.analyze_transcript(...)
    ```
    
    Or for singleton usage:
    ```python
    client = AsyncIngestionClient()
    try:
        result = await client.analyze_transcript(...)
    finally:
        await client.close()
    ```
    """
    
    def __init__(
        self,
        base_url: str = INGESTION_BASE_URL,
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
    
    async def __aenter__(self) -> "AsyncIngestionClient":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self.close()
    
    async def upload_document(
        self,
        file_path: str,
        project_id: str,
        category: Optional[str] = None,
        document_type: str = "general",
    ) -> dict[str, Any]:
        """
        Upload a document for processing asynchronously.
        
        Args:
            file_path: Local path to the file
            project_id: Tenant/project identifier
            category: Optional category (e.g., "policy", "regulation")
            document_type: Type of document ("general" or "hipaa_regulation")
            
        Returns:
            dict with job_id and message
        """
        async with aiofiles.open(file_path, "rb") as f:
            content = await f.read()
        
        files = {"file": (os.path.basename(file_path), content)}
        data = {
            "project_id": project_id,
            "document_type": document_type,
        }
        if category:
            data["category"] = category
        
        response = await self._client.post(
            f"{self.base_url}/documents",
            files=files,
            data=data,
        )
        response.raise_for_status()
        return response.json()
    
    async def check_status(self, job_id: str) -> dict[str, Any]:
        """Check the status of an upload job asynchronously."""
        response = await self._client.get(
            f"{self.base_url}/documents/{job_id}/status"
        )
        response.raise_for_status()
        return response.json()
    
    async def analyze_transcript(
        self,
        file_path: str,
        project_id: str,
    ) -> dict[str, Any]:
        """
        Submit a clinical transcript for PHI detection asynchronously.
        
        Args:
            file_path: Path to the transcript file
            project_id: Project identifier
            
        Returns:
            dict with job_id for polling
        """
        async with aiofiles.open(file_path, "rb") as f:
            content = await f.read()
        
        files = {"file": (os.path.basename(file_path), content)}
        data = {"project_id": project_id}
        
        response = await self._client.post(
            f"{self.base_url}/clinical-transcripts",
            files=files,
            data=data,
        )
        response.raise_for_status()
        return response.json()
    
    async def get_transcript_job_status(self, job_id: str) -> dict[str, Any]:
        """Check status of a transcript analysis job asynchronously."""
        response = await self._client.get(
            f"{self.base_url}/clinical-transcripts/jobs/{job_id}"
        )
        response.raise_for_status()
        return response.json()
    
    async def get_compliance_report(
        self,
        transcript_id: str,
        project_id: str = "default",
    ) -> dict[str, Any]:
        """
        Get compliance report for a transcript asynchronously.
        
        Args:
            transcript_id: ID of the analyzed transcript
            project_id: Project identifier
            
        Returns:
            Full compliance report dict
        """
        response = await self._client.get(
            f"{self.base_url}/clinical-transcripts/{transcript_id}/compliance-report",
            params={"project_id": project_id},
        )
        response.raise_for_status()
        return response.json()
    
    async def query_audit_log(
        self,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Query the HIPAA audit log asynchronously.
        
        Args:
            event_type: Filter by event type (e.g., "PHI_DETECTED")
            limit: Maximum number of events
            
        Returns:
            dict with events list and total count
        """
        params = {"limit": limit}
        if event_type:
            params["event_type"] = event_type
        
        response = await self._client.get(
            f"{self.base_url}/audit-log",
            params=params,
        )
        response.raise_for_status()
        return response.json()
    
    async def health_check(self) -> ServiceStatus:
        """Check if ingestion service is healthy asynchronously."""
        try:
            response = await self._client.get(
                f"{self.base_url}/health",
                timeout=5.0,
            )
            response.raise_for_status()
            return ServiceStatus(name="ingestion", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="ingestion", healthy=False, message=str(e))


class AsyncRAGClient:
    """
    Async client for the RAG Service with connection pooling.
    
    Use as context manager or call close() when done.
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
        
        Args:
            query: Natural language query
            project_id: Project identifier
            k: Number of results to return
            
        Returns:
            dict with search results
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
        
        Args:
            query: Natural language question
            project_id: Project identifier
            k: Number of documents to retrieve
            backend: LLM backend ("openai" or "runpod")
            
        Returns:
            dict with answer and sources
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
        
        Args:
            query: Natural language query about regulations
            k: Number of results
            project_id: Project containing regulations
            
        Returns:
            List of matching regulation sections
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
        
        Args:
            query: Query to find relevant regulations
            k: Number of regulation sections to include
            project_id: Project containing regulations
            
        Returns:
            Formatted string with regulation excerpts
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
        """Check health of all backend services concurrently."""
        import asyncio
        results = await asyncio.gather(
            self.check_ingestion(),
            self.check_rag(),
            return_exceptions=True,
        )
        return {
            "ingestion": results[0] if isinstance(results[0], ServiceStatus) 
                         else ServiceStatus(name="ingestion", healthy=False, message=str(results[0])),
            "rag": results[1] if isinstance(results[1], ServiceStatus)
                   else ServiceStatus(name="rag", healthy=False, message=str(results[1])),
        }
    
    async def check_ingestion(self) -> ServiceStatus:
        """Check ingestion service health asynchronously."""
        try:
            response = await self._client.get(f"{self.ingestion_url}/health")
            response.raise_for_status()
            return ServiceStatus(name="ingestion", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="ingestion", healthy=False, message=str(e))
    
    async def check_rag(self) -> ServiceStatus:
        """Check RAG service health asynchronously."""
        try:
            response = await self._client.get(f"{self.rag_url}/health")
            response.raise_for_status()
            return ServiceStatus(name="rag", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="rag", healthy=False, message=str(e))

