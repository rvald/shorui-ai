"""
Compliance Service HTTP Client.

Provides async client for compliance operations (PHI detection, audit log)
using the ServiceHttpClient from shorui_core.runtime.
"""

from __future__ import annotations

import os
from typing import Any

import aiofiles

from shorui_core.runtime import RetryPolicy, RunContext, ServiceHttpClient

from .base import ServiceStatus, default_context

# Configuration
COMPLIANCE_BASE_URL = os.getenv(
    "COMPLIANCE_SERVICE_URL", "http://localhost:8082/compliance"
)
DEFAULT_TIMEOUT = 60.0

# Health checks should fail fast, no retry
HEALTH_CHECK_POLICY = RetryPolicy(max_attempts=1, base_delay=0.0)


class ComplianceClient:
    """Async client for the Compliance Service.

    Uses ServiceHttpClient for connection pooling, automatic header injection,
    and retry on transient failures.

    Example:
        async with ComplianceClient() as client:
            job = await client.analyze_transcript("transcript.txt", "project-1")
    """

    def __init__(
        self,
        base_url: str = COMPLIANCE_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """Initialize the Compliance client.

        Args:
            base_url: Base URL of the Compliance service.
            timeout: Request timeout in seconds.
        """
        self._http = ServiceHttpClient(
            base_url=base_url,
            timeout=timeout,
        )

    async def close(self) -> None:
        """Close the HTTP client and release connections."""
        await self._http.close()

    async def __aenter__(self) -> "ComplianceClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager."""
        await self.close()

    async def analyze_transcript(
        self,
        file_path: str,
        project_id: str,
        context: RunContext | None = None,
    ) -> dict[str, Any]:
        """Submit a clinical transcript for PHI detection.

        Args:
            file_path: Path to the transcript file.
            project_id: Project to associate with the analysis.
            context: Optional RunContext for correlation ID propagation.

        Returns:
            Job information including job_id and status.
        """
        ctx = context or default_context()

        async with aiofiles.open(file_path, "rb") as f:
            content = await f.read()

        files = {"file": (os.path.basename(file_path), content)}
        data = {"project_id": project_id}

        response = await self._http.post(
            "/clinical-transcripts",
            ctx,
            files=files,
            data=data,
        )
        return response.json()

    async def get_transcript_job_status(
        self,
        job_id: str,
        context: RunContext | None = None,
    ) -> dict[str, Any]:
        """Check status of a transcript analysis job.

        Args:
            job_id: The job ID to check.
            context: Optional RunContext for correlation ID propagation.

        Returns:
            Job status including progress and result.
        """
        ctx = context or default_context()
        response = await self._http.get(
            f"/clinical-transcripts/job/{job_id}",
            ctx,
        )
        return response.json()

    async def get_compliance_report(
        self,
        transcript_id: str,
        context: RunContext | None = None,
    ) -> dict[str, Any]:
        """Get compliance report for a transcript.

        Args:
            transcript_id: The transcript ID.
            context: Optional RunContext for correlation ID propagation.

        Returns:
            Compliance report with PHI findings and recommendations.
        """
        ctx = context or default_context()
        response = await self._http.get(
            f"/clinical-transcripts/{transcript_id}/report",
            ctx,
        )
        return response.json()

    async def query_audit_log(
        self,
        event_type: str | None = None,
        limit: int = 100,
        context: RunContext | None = None,
    ) -> dict[str, Any]:
        """Query the HIPAA audit log.

        Args:
            event_type: Optional filter by event type.
            limit: Maximum number of events to return.
            context: Optional RunContext for correlation ID propagation.

        Returns:
            List of audit events.
        """
        ctx = context or default_context()
        params: dict[str, Any] = {"limit": limit}
        if event_type:
            params["event_type"] = event_type

        response = await self._http.get(
            "/audit-log",
            ctx,
            params=params,
        )
        return response.json()

    async def health_check(self) -> ServiceStatus:
        """Check if compliance service is healthy.

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
                response = await health_http.get(
                    "/audit-log",
                    ctx,
                    params={"limit": 1},
                )
                response.raise_for_status()
                return ServiceStatus(name="compliance", healthy=True, message="OK")
            finally:
                await health_http.close()
        except Exception as e:
            return ServiceStatus(name="compliance", healthy=False, message=str(e))


# Legacy alias for backward compatibility
AsyncComplianceClient = ComplianceClient
