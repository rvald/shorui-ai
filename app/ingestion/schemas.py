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


class JobStatus(BaseModel):
    """Response model for job status."""

    job_id: str
    status: str
    progress: int | None = None
    error: str | None = None
    result: dict | None = None


class UploadResponse(BaseModel):
    """Response model for document upload."""

    job_id: str
    message: str
