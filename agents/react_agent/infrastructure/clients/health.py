"""
Health Check HTTP Client.

Provides async client for checking backend service health
using the ServiceHttpClient from shorui_core.runtime.
"""

from __future__ import annotations

from shorui_core.runtime import RetryPolicy, RunContext, ServiceHttpClient

from .base import ServiceStatus, default_context
from .ingestion import INGESTION_BASE_URL
from .rag import RAG_BASE_URL

# Health checks should fail fast, no retry
HEALTH_CHECK_POLICY = RetryPolicy(max_attempts=1, base_delay=0.0)


class HealthClient:
    """Async client for checking backend service health.

    Example:
        async with HealthClient() as client:
            status = await client.check_all()
            print(status["rag"].healthy)
    """

    def __init__(
        self,
        ingestion_url: str = INGESTION_BASE_URL,
        rag_url: str = RAG_BASE_URL,
        timeout: float = 5.0,
    ):
        """Initialize the Health client.

        Args:
            ingestion_url: Base URL of the Ingestion service.
            rag_url: Base URL of the RAG service.
            timeout: Request timeout in seconds.
        """
        self._ingestion_http = ServiceHttpClient(
            base_url=ingestion_url,
            timeout=timeout,
            retry_policy=HEALTH_CHECK_POLICY,
        )
        self._rag_http = ServiceHttpClient(
            base_url=rag_url,
            timeout=timeout,
            retry_policy=HEALTH_CHECK_POLICY,
        )

    async def close(self) -> None:
        """Close all HTTP clients."""
        await self._ingestion_http.close()
        await self._rag_http.close()

    async def __aenter__(self) -> "HealthClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args) -> None:
        """Exit async context manager."""
        await self.close()

    async def check_all(self) -> dict[str, ServiceStatus]:
        """Check health of all backend services.

        Returns:
            Dictionary mapping service name to ServiceStatus.
        """
        return {
            "ingestion": await self.check_ingestion(),
            "rag": await self.check_rag(),
        }

    async def check_ingestion(self) -> ServiceStatus:
        """Check ingestion service health.

        Returns:
            ServiceStatus for the ingestion service.
        """
        try:
            ctx = default_context()
            response = await self._ingestion_http.get("/health", ctx)
            response.raise_for_status()
            return ServiceStatus(name="ingestion", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="ingestion", healthy=False, message=str(e))

    async def check_rag(self) -> ServiceStatus:
        """Check RAG service health.

        Returns:
            ServiceStatus for the RAG service.
        """
        try:
            ctx = default_context()
            response = await self._rag_http.get("/health", ctx)
            response.raise_for_status()
            return ServiceStatus(name="rag", healthy=True, message="OK")
        except Exception as e:
            return ServiceStatus(name="rag", healthy=False, message=str(e))


# Legacy alias for backward compatibility
AsyncHealthClient = HealthClient
