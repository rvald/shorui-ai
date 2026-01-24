"""
Pydantic schemas for the ingestion module.

This module contains all request/response models for the ingestion API,
keeping route handlers clean and enabling schema reuse.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ==============================================================================
# DOCUMENT UPLOAD SCHEMAS
# ==============================================================================


class JobResult(BaseModel):
    result_pointer: str | None = None
    items_indexed: int | None = None
    collection_name: str | None = None


class JobStatus(BaseModel):
    """Response model for job status."""

    job_id: str
    status: str
    progress: int | None = None
    error: str | None = None
    result: JobResult | None = None


class UploadResponse(BaseModel):
    """Response model for document upload."""

    job_id: str
    message: str
    raw_pointer: str | None = None
    status: str | None = None
