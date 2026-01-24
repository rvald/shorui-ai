"""
Compliance module factory.

This module provides factory functions to create instances of compliance services,
handling dependency injection and configuration.
"""

from __future__ import annotations

from functools import lru_cache

from app.compliance.protocols import (
    AuditLogger,
    ComplianceReporter,
    GraphIngestor,
    PHIDetector,
    RegulationRetriever,
)
from app.compliance.services.audit_service import AuditService
from app.compliance.services.compliance_report_service import ComplianceReportService
from app.compliance.services.hipaa_graph_ingestion import HIPAAGraphIngestionService
from app.compliance.services.phi_detector import get_phi_detector
from app.compliance.services.privacy_extraction import PrivacyAwareExtractionService
from app.compliance.services.regulation_retriever import (
    RegulationRetriever as RegulationRetrieverImpl,
)


@lru_cache()
def get_phi_detector_service() -> PHIDetector:
    """Get the PHI detector service instance."""
    return get_phi_detector()


@lru_cache()
def get_audit_logger() -> AuditLogger:
    """Get the audit logger service instance."""
    return AuditService()


@lru_cache()
def get_regulation_retriever() -> RegulationRetriever:
    """Get the regulation retriever service instance."""
    return RegulationRetrieverImpl()


@lru_cache()
def get_compliance_reporter() -> ComplianceReporter:
    """Get the compliance reporter service instance."""
    return ComplianceReportService()


def get_privacy_extraction_service() -> PrivacyAwareExtractionService:
    """
    Get the privacy-aware extraction service instance.

    Wires up dependencies: PHIDetector, RegulationRetriever, AuditLogger.
    """
    return PrivacyAwareExtractionService(
        phi_detector=get_phi_detector_service(),
        regulation_retriever=get_regulation_retriever(),
        audit_logger=get_audit_logger(),
        graph_ingestor=get_graph_ingestor(),
    )


def get_graph_ingestor(audit_logger: AuditLogger | None = None) -> GraphIngestor:
    """
    Get the graph ingestion service instance.

    Args:
        audit_logger: Optional audit logger (defaults to singleton if None)
    """
    # Note: HIPAAGraphIngestionService might need updates to accept audit_logger via init
    # For now, we return the class as is, future refactors will enable injection
    return HIPAAGraphIngestionService()
