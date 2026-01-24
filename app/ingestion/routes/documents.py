"""
Document upload and processing routes.

This module handles general document ingestion endpoints:
- Upload documents for processing
- Check processing status
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from loguru import logger

from app.ingestion.schemas import JobStatus, UploadResponse
from app.ingestion.services.job_ledger import JobLedgerService
from app.ingestion.services.storage import get_storage_backend
from app.ingestion.services.tenant import resolve_tenant_from_project
from app.workers.tasks import process_document

router = APIRouter()
_storage_service = None

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB limit
ALLOWED_CONTENT_TYPES = {"application/pdf", "text/plain"}


@router.get("/health")
def ingestion_health():
    """Health check for the ingestion module."""
    return {"status": "ok", "module": "ingestion"}


def get_storage_service():
    """Lazily construct storage backend to avoid side effects at import."""
    global _storage_service
    if _storage_service is None:
        _storage_service = get_storage_backend()
    return _storage_service


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
    tenant_id = resolve_tenant_from_project(project_id)
    request_id = str(uuid.uuid4())
    ledger = JobLedgerService()

    # Read file content
    file_content = await file.read()
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "unknown"

    logger.info(
        f"[{request_id}] Received {document_type} upload for project={project_id} tenant={tenant_id}"
    )

    storage_service = get_storage_service()

    byte_size = len(file_content)
    if byte_size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported content type")

    # Compute idempotency key before upload to avoid duplicate work
    content_hash = ledger.compute_content_hash(file_content)
    idempotency_key = ledger.build_idempotency_key(
        content_hash=content_hash,
        tenant_id=tenant_id,
        project_id=project_id,
        document_type=document_type,
        content_type=content_type,
    )

    existing = ledger.check_idempotency(
        idempotency_key=idempotency_key,
        job_type="ingestion_document",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    if existing:
        logger.info(f"Idempotent hit for upload (job={existing['job_id']}, status={existing['status']})")
        return UploadResponse(
            job_id=existing["job_id"],
            message="Document already processed",
            raw_pointer=None,
            status="skipped" if existing["status"] == "completed" else existing["status"],
        )

    # Upload raw content to storage and record artifact
    try:
        raw_pointer = storage_service.upload(
            content=file_content,
            filename=filename,
            tenant_id=tenant_id,
            project_id=project_id,
            bucket=storage_service.raw_bucket,
        )
    except Exception as e:
        logger.error(f"[{request_id}] Storage upload failed: {type(e).__name__}")
        raise HTTPException(status_code=503, detail="Storage temporarily unavailable")

    job_id = ledger.create_job(
        tenant_id=tenant_id,
        project_id=project_id,
        job_type="ingestion_document",
        job_id=str(uuid.uuid4()),
        status="pending",
        progress=0,
        idempotency_key=idempotency_key,
        request_id=request_id,
        raw_pointer=raw_pointer,
        content_type=content_type,
        document_type=document_type,
        byte_size=byte_size,
        input_artifacts=[
            {"type": "raw_upload", "pointer": raw_pointer, "filename": filename}
        ],
    )

    ledger.register_artifact(
        tenant_id=tenant_id,
        project_id=project_id,
        artifact_type="raw_upload",
        storage_pointer=raw_pointer,
        content_type=content_type,
        byte_size=byte_size,
        sha256=content_hash,
        created_by_job_id=job_id,
    )

    # Queue task via Celery with document_type for routing
    process_document.delay(
        job_id=job_id,
        tenant_id=tenant_id,
        project_id=project_id,
        raw_pointer=raw_pointer,
        filename=filename,
        content_type=content_type,
        document_type=document_type,
        index_to_vector=index_to_vector,
        index_to_graph=index_to_graph,
        idempotency_key=idempotency_key,
        # Regulation-specific metadata
        source=source,
        title=title,
        category=category,
    )

    logger.info(f"[{job_id}] Queued {document_type} processing via Celery")

    return UploadResponse(job_id=job_id, message="Document queued for processing", raw_pointer=None, status="pending")


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
            collection_name = None
            result_artifacts = job_info.get("result_artifacts")
            if isinstance(result_artifacts, list) and result_artifacts:
                collection_name = result_artifacts[0].get("collection_name")

            result_block = None
            if job_info.get("result_pointer") or job_info.get("items_indexed"):
                result_block = {
                    "result_pointer": job_info.get("result_pointer"),
                    "items_indexed": job_info.get("items_indexed"),
                    "collection_name": collection_name,
                }

            return JobStatus(
                job_id=job_info["job_id"],
                status=job_info["status"],
                progress=job_info.get("progress"),
                error=job_info.get("error"),
                result=result_block,
            )
        else:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to fetch job from ledger: {e}")
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
