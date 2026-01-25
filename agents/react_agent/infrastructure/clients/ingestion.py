"""
Ingestion Service HTTP Client.

Provides async client for document ingestion operations
using the ServiceHttpClient from shorui_core.runtime.
"""

from __future__ import annotations

import os
from typing import Any

import aiofiles

from shorui_core.runtime import RetryPolicy, RunContext, ServiceHttpClient

from .base import ServiceStatus, default_context

# Configuration
INGESTION_BASE_URL = os.getenv(
    "INGESTION_SERVICE_URL", "http://localhost:8082/ingest"
)
DEFAULT_TIMEOUT = 60.0

# Health checks should fail fast, no retry
HEALTH_CHECK_POLICY = RetryPolicy(max_attempts=1, base_delay=0.0)


class IngestionClient:
    """Async client for the Ingestion Service.

    Handles document uploads and job status checks.

    Uses ServiceHttpClient for connection pooling, automatic header injection,
    and retry on transient failures.

    Example:
        async with IngestionClient() as client:
            job = await client.upload_document("doc.pdf", "my-project")
    """

    def __init__(
        self,
        base_url: str = INGESTION_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """Initialize the Ingestion client.

        Args:
            base_url: Base URL of the Ingestion service.
            timeout: Request timeout in seconds.
        """
        self._http = ServiceHttpClient(
            base_url=base_url,
            timeout=timeout,
        )

    async def close(self) -> None:
        """Close the HTTP client and release connections."""
        await self._http.close()

    async def __aenter__(self) -> "IngestionClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager."""
        await self.close()

    async def upload_document(
        self,
        file_path: str,
        project_id: str,
        category: str | None = None,
        document_type: str = "general",
        context: RunContext | None = None,
    ) -> dict[str, Any]:
        """Upload a document for processing.

        Args:
            file_path: Path to the document file.
            project_id: Project to associate with the document.
            category: Optional category for organization.
            document_type: Type of document ("general" or "hipaa_regulation").
            context: Optional RunContext for correlation ID propagation.

        Returns:
            Job information including job_id and status.
        """
        ctx = context or default_context()

        async with aiofiles.open(file_path, "rb") as f:
            content = await f.read()

        files = {"file": (os.path.basename(file_path), content)}
        data: dict[str, str] = {
            "project_id": project_id,
            "document_type": document_type,
        }
        if category:
            data["category"] = category

        response = await self._http.post(
            "/documents",
            ctx,
            files=files,
            data=data,
        )
        return response.json()

    async def check_status(
        self,
        job_id: str,
        context: RunContext | None = None,
    ) -> dict[str, Any]:
        """Check the status of an upload job.

        Args:
            job_id: The job ID to check.
            context: Optional RunContext for correlation ID propagation.

        Returns:
            Job status including progress and result.
        """
        ctx = context or default_context()
        response = await self._http.get(
            f"/documents/{job_id}/status",
            ctx,
        )
        return response.json()

    async def health_check(self) -> ServiceStatus:
        """Check if ingestion service is healthy.

        Returns:
            ServiceStatus indicating health state.
        """
        try:
            ctx = default_context()
            health_http = ServiceHttpClient(
                base_url=self._http.base_url,
                timeout=5.0,
                retry_policy=HEALTH_CHECK_POLICY,
            )
            try:
                response = await health_http.get("/health", ctx)
                response.raise_for_status()
                return ServiceStatus(name="ingestion", healthy=True, message="OK")
            finally:
                await health_http.close()
        except Exception as e:
            return ServiceStatus(name="ingestion", healthy=False, message=str(e))


# Legacy alias for backward compatibility
AsyncIngestionClient = IngestionClient
