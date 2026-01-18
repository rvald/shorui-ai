"""
Document upload and processing routes.

This module handles general document ingestion endpoints:
- Upload documents for processing
- Check processing status
"""

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from loguru import logger

from app.ingestion.schemas import JobStatus, UploadResponse
from app.workers.tasks import process_document

router = APIRouter()


@router.get("/health")
def ingestion_health():
    """Health check for the ingestion module."""
    return {"status": "ok", "module": "ingestion"}


@router.post("/documents", response_model=UploadResponse, status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    document_type: str = Form(default="general"),  # "general", "hipaa_regulation"
    index_to_vector: bool = Form(default=True),
    index_to_graph: bool = Form(default=False),
    # Optional fields for hipaa_regulation type
    source: str | None = Form(default=None),  # e.g., "45 CFR 164.514"
    title: str | None = Form(default=None),
    category: str | None = Form(default=None),  # privacy_rule, security_rule, etc.
):
    """
    Upload a document for processing.

    The document will be processed asynchronously via Celery.
    Use the returned job_id to check the processing status.

    Args:
        file: The document file to upload.
        project_id: Project identifier for multi-tenancy.
        document_type: Type of document - "general" or "hipaa_regulation".
        index_to_vector: Whether to index to vector database (default: True).
        index_to_graph: Whether to index to graph database (default: False).
        source: For regulations - source identifier (e.g., "45 CFR 164.514").
        title: For regulations - human-readable title.
        category: For regulations - category (privacy_rule, security_rule, etc.).

    Returns:
        UploadResponse: Contains job_id for tracking.
    """
    # Generate a unique job ID
    job_id = str(uuid.uuid4())

    # Read file content
    file_content = await file.read()
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "unknown"

    logger.info(
        f"Received {document_type} upload: {filename} ({content_type}) for project {project_id}"
    )

    # Queue task via Celery with document_type for routing
    process_document.delay(
        job_id=job_id,
        file_content=file_content,
        filename=filename,
        content_type=content_type,
        project_id=project_id,
        document_type=document_type,
        index_to_vector=index_to_vector,
        index_to_graph=index_to_graph,
        # Regulation-specific metadata
        source=source,
        title=title,
        category=category,
    )

    logger.info(f"[{job_id}] Queued {document_type} processing via Celery")

    return UploadResponse(job_id=job_id, message=f"Document '{filename}' queued for processing")


@router.get("/documents/{job_id}/status", response_model=JobStatus)
def get_document_status(job_id: str):
    """
    Get the processing status of an uploaded document.

    Queries the PostgreSQL job ledger for job status.

    Args:
        job_id: The job ID returned from the upload endpoint.

    Returns:
        JobStatus: Current status of the processing job.

    Raises:
        HTTPException: 404 if job_id is not found.
    """
    from app.ingestion.services.job_ledger import JobLedgerService

    try:
        ledger_service = JobLedgerService()
        job_info = ledger_service.get_job(job_id)

        if job_info:
            return JobStatus(
                job_id=job_info["job_id"],
                status=job_info["status"],
                progress=job_info.get("progress"),
                error=job_info.get("error"),
                result={
                    "items_indexed": job_info.get("items_indexed"),
                    "storage_path": job_info.get("storage_path"),
                }
                if job_info.get("items_indexed")
                else None,
            )
        else:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to fetch job from ledger: {e}")
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
