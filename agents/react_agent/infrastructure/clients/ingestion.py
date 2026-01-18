"""
Ingestion Service HTTP Clients.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx
import aiofiles

from .base import ServiceStatus

# Configuration
INGESTION_BASE_URL = os.getenv("INGESTION_SERVICE_URL", "http://localhost:8082/ingest")
DEFAULT_TIMEOUT = 60.0

DEFAULT_POOL_LIMITS = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=30.0,
)

class IngestionClient:
    """
    Synchronous client for the Ingestion Service.
    
    Handles document uploads and status checks.
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
        """Check the status of an upload job."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/documents/{job_id}/status")
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


class AsyncIngestionClient:
    """
    Async client for the Ingestion Service.
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
        """Close the HTTP client."""
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
        """Upload a document for processing asynchronously."""
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
