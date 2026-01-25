"""
Canonical Artifacts & Jobs module.

Provides standardized job and artifact tracking across all async workloads
(ingestion, compliance, RAG). See specs/component_artifacts_and_jobs.md.

Exports:
    - ArtifactType: Enum of artifact types (raw_upload, ingestion_result, etc.)
    - JobType: Enum of job types (ingestion_document, compliance_transcript, etc.)
    - JobStatus: Enum of job statuses (pending, processing, completed, etc.)
    - Artifact: Domain model for artifacts
    - ArtifactService: CRUD operations for the artifacts registry
"""

from shorui_core.artifacts.models import (
    Artifact,
    ArtifactType,
    JobStatus,
)
from shorui_core.artifacts.job_types import JobType
from shorui_core.artifacts.artifact_service import (
    ArtifactService,
    get_artifact_service,
)

__all__ = [
    "Artifact",
    "ArtifactType",
    "ArtifactService",
    "JobStatus",
    "JobType",
    "get_artifact_service",
]
