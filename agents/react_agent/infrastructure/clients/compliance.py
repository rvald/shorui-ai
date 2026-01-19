"""
Compliance Service HTTP Clients.
"""
from __future__ import annotations

import os
from typing import Any, Optional
import httpx

from .base import ServiceStatus

# Configuration
COMPLIANCE_BASE_URL = os.getenv("COMPLIANCE_SERVICE_URL", "http://localhost:8082/compliance")
DEFAULT_TIMEOUT = 60.0

DEFAULT_POOL_LIMITS = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=30.0,
)

class ComplianceClient:
    """
    Synchronous client for the Compliance Service.
    """
    
    def __init__(self, base_url: str = COMPLIANCE_BASE_URL, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
    
    def analyze_transcript(
        self,
        file_path: str,
        project_id: str,
    ) -> dict[str, Any]:
        """
        Submit a clinical transcript for PHI detection.
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
            # Corrected path: /clinical-transcripts/job/{job_id} (singular 'job')
            response = client.get(
                f"{self.base_url}/clinical-transcripts/job/{job_id}"
            )
            response.raise_for_status()
            return response.json()
    
    def get_compliance_report(
        self,
        transcript_id: str,
    ) -> dict[str, Any]:
        """
        Get compliance report for a transcript.
        """
        with httpx.Client(timeout=self.timeout) as client:
            # Corrected path: /clinical-transcripts/{id}/report
            response = client.get(
                f"{self.base_url}/clinical-transcripts/{transcript_id}/report"
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
        """Check if compliance service is healthy (via root health or specific check)."""
        # Compliance doesn't seem to have a specific health endpoint listed in specs,
        # but we can try to query stats or assume generic connectivity check.
        # For now, we'll try accessing the audit log with limit=1 as a ping.
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/audit-log", params={"limit": 1})
                response.raise_for_status()
                return ServiceStatus(name="compliance", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="compliance", healthy=False, message=str(e))


class AsyncComplianceClient:
    """
    Async client for the Compliance Service.
    """
    
    def __init__(
        self,
        base_url: str = COMPLIANCE_BASE_URL,
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
        
    async def __aenter__(self) -> "AsyncComplianceClient":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self.close()
    
    async def analyze_transcript(
        self,
        file_path: str,
        project_id: str,
    ) -> dict[str, Any]:
        """Submit a clinical transcript asynchronously."""
        import aiofiles
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
            f"{self.base_url}/clinical-transcripts/job/{job_id}"
        )
        response.raise_for_status()
        return response.json()
    
    async def get_compliance_report(
        self,
        transcript_id: str,
    ) -> dict[str, Any]:
        """Get compliance report asynchronously."""
        response = await self._client.get(
            f"{self.base_url}/clinical-transcripts/{transcript_id}/report"
        )
        response.raise_for_status()
        return response.json()
    
    async def query_audit_log(
        self,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Query the HIPAA audit log asynchronously."""
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
        """Check if compliance service is healthy asynchronously."""
        try:
            response = await self._client.get(
                f"{self.base_url}/audit-log",
                params={"limit": 1},
                timeout=5.0
            )
            response.raise_for_status()
            return ServiceStatus(name="compliance", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="compliance", healthy=False, message=str(e))
