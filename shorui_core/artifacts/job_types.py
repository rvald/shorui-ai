"""
Canonical job types for all async workloads.

Each job type represents a specific async operation that can be tracked
in the jobs ledger. Using an enum ensures consistency across the codebase.
"""

from enum import Enum


class JobType(str, Enum):
    """
    Canonical job types across all modules.
    
    Usage:
        from shorui_core.artifacts import JobType
        
        ledger.create_job(job_type=JobType.INGESTION_DOCUMENT, ...)
    """
    # Ingestion jobs
    INGESTION_DOCUMENT = "ingestion_document"
    INGESTION_REGULATION = "ingestion_regulation"
    
    # Compliance jobs
    COMPLIANCE_TRANSCRIPT = "compliance_transcript"
    
    # RAG jobs (future)
    RAG_INDEX = "rag_index"
    RAG_QUERY = "rag_query"
