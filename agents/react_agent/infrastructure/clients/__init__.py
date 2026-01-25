"""
HTTP clients for Shorui AI services.

All clients are async and use ServiceHttpClient from shorui_core.runtime
for connection pooling, automatic header injection, and retry on transient failures.

Legacy sync aliases (e.g., AsyncRAGClient) are provided for backward compatibility.
"""

from .base import ServiceStatus, default_context
from .compliance import (
    COMPLIANCE_BASE_URL,
    AsyncComplianceClient,
    ComplianceClient,
)
from .health import AsyncHealthClient, HealthClient
from .ingestion import (
    INGESTION_BASE_URL,
    AsyncIngestionClient,
    IngestionClient,
)
from .rag import (
    RAG_BASE_URL,
    AsyncRAGClient,
    AsyncRegulationRetriever,
    RAGClient,
    RegulationRetriever,
)

__all__ = [
    # Base
    "ServiceStatus",
    "default_context",
    # RAG
    "RAGClient",
    "AsyncRAGClient",
    "RegulationRetriever",
    "AsyncRegulationRetriever",
    "RAG_BASE_URL",
    # Compliance
    "ComplianceClient",
    "AsyncComplianceClient",
    "COMPLIANCE_BASE_URL",
    # Ingestion
    "IngestionClient",
    "AsyncIngestionClient",
    "INGESTION_BASE_URL",
    # Health
    "HealthClient",
    "AsyncHealthClient",
]
