"""
Celery task definitions for document processing.

This module contains the Celery tasks that handle async document ingestion.
Tasks delegate to specialized services for the actual processing logic.
"""

import os
import tempfile

from loguru import logger

from app.ingestion.services.job_ledger import JobLedgerService
from app.ingestion.services.storage import StorageService
from app.workers.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="app.workers.tasks.process_document",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def process_document(
    self,
    job_id: str,
    file_content: bytes,
    filename: str,
    content_type: str,
    project_id: str,
    document_type: str = "general",  # "general", "hipaa_regulation"
    index_to_vector: bool = True,
    index_to_graph: bool = False,
    # Regulation-specific metadata
    source: str = None,
    title: str = None,
    category: str = None,
) -> dict:
    """
    Celery task to process an uploaded document.

    Routes based on document_type:
    - "general": Uses DocumentIngestionService
    - "hipaa_regulation": Uses HIPAARegulationService

    Args:
        self: Celery task instance (for retries).
        job_id: Unique job identifier.
        file_content: Raw document bytes.
        filename: Original filename.
        content_type: MIME type.
        project_id: Project for multi-tenancy.
        document_type: Type of document for routing.
        index_to_vector: Index to Qdrant.
        index_to_graph: Index to Neo4j.
        source: For regulations - source identifier.
        title: For regulations - human-readable title.
        category: For regulations - category.

    Returns:
        dict: Processing result with stats.
    """
    logger.info(f"[{job_id}] Starting Celery task for {filename} (type={document_type})")

    # Initialize common services
    storage_service = StorageService()
    ledger_service = JobLedgerService()

    try:
        # 1. Compute content hash for idempotency
        content_hash = ledger_service.compute_content_hash(file_content)

        # 2. Check if already processed (idempotency)
        existing = ledger_service.check_idempotency(project_id, filename, content_hash)
        if existing and existing.get("status") == "completed":
            logger.info(f"[{job_id}] Document already processed (job: {existing['job_id']})")
            return {
                "status": "skipped",
                "existing_job_id": existing["job_id"],
                "message": "Document already processed (idempotent)",
            }

        # 3. Upload to MinIO for persistence
        storage_path = None
        try:
            storage_path = storage_service.upload(file_content, filename, project_id)
            logger.info(f"[{job_id}] Uploaded to MinIO: {storage_path}")
        except Exception as e:
            logger.warning(f"[{job_id}] MinIO upload failed (continuing): {e}")

        # 4. Create job in ledger
        try:
            ledger_service.create_job(
                project_id=project_id,
                filename=filename,
                storage_path=storage_path or "temp",
                content_hash=content_hash,
                job_id=job_id,
            )
            ledger_service.update_status(job_id, "processing", progress=10)
        except Exception as e:
            logger.warning(f"[{job_id}] Ledger create failed (continuing): {e}")

        # ===== ROUTE BASED ON DOCUMENT TYPE =====

        if document_type == "hipaa_regulation":
            stats = _process_hipaa_regulation(
                job_id=job_id,
                file_content=file_content,
                filename=filename,
                source=source,
                title=title,
                category=category,
            )
        else:
            stats = _process_general_document(
                job_id=job_id,
                file_content=file_content,
                filename=filename,
                content_type=content_type,
                project_id=project_id,
                index_to_vector=index_to_vector,
            )

        # 5. Complete job in ledger
        try:
            ledger_service.complete_job(job_id, items_indexed=stats.get("chunks_created", 0))
        except Exception as e:
            logger.warning(f"[{job_id}] Ledger complete failed: {e}")

        result = {
            "status": "completed",
            "storage_path": storage_path,
            **stats,
        }

        logger.info(f"[{job_id}] Processing complete: {result}")
        return result

    except Exception as e:
        logger.exception(f"[{job_id}] Processing failed: {e}")

        # Add to DLQ
        try:
            ledger_service.fail_job(job_id, error=str(e))
            ledger_service.add_to_dlq(job_id, error=str(e), traceback=None)
        except Exception:
            pass

        # Re-raise to trigger Celery retry
        raise


def _process_hipaa_regulation(
    job_id: str,
    file_content: bytes,
    filename: str,
    source: str | None,
    title: str | None,
    category: str | None,
) -> dict:
    """
    Process a HIPAA regulation document.

    Args:
        job_id: Job identifier for logging
        file_content: Raw document bytes
        filename: Original filename
        source: Source identifier
        title: Human-readable title
        category: Category (privacy_rule, security_rule, etc.)

    Returns:
        dict: Processing statistics
    """
    from app.compliance.services.hipaa_regulation_service import HIPAARegulationService

    logger.info(f"[{job_id}] Processing as HIPAA regulation")

    # Decode text content
    text = _extract_text_content(file_content)

    service = HIPAARegulationService()
    stats = service.ingest_regulation(
        text=text,
        source=source or filename,
        title=title,
        category=category or "privacy_rule",
    )

    return {
        "document_type": "hipaa_regulation",
        "chunks_created": stats.get("chunks_created", 0),
        "sections_found": stats.get("sections_found", []),
    }


def _process_general_document(
    job_id: str,
    file_content: bytes,
    filename: str,
    content_type: str,
    project_id: str,
    index_to_vector: bool,
) -> dict:
    """
    Process a general document.

    Args:
        job_id: Job identifier for logging
        file_content: Raw document bytes
        filename: Original filename
        content_type: MIME type
        project_id: Project identifier
        index_to_vector: Whether to index to vector DB

    Returns:
        dict: Processing statistics
    """
    from app.ingestion.services.document_ingestion_service import DocumentIngestionService

    logger.info(f"[{job_id}] Processing as general document")

    if not index_to_vector:
        logger.info(f"[{job_id}] Skipping vector indexing (index_to_vector=False)")
        return {
            "document_type": "general",
            "chunks_created": 0,
            "indexed_to_vector": False,
        }

    service = DocumentIngestionService()
    stats = service.ingest_document(
        content=file_content,
        filename=filename,
        content_type=content_type,
        project_id=project_id,
    )

    return {
        "document_type": "general",
        "chunks_created": stats.get("chunks_created", 0),
        "collection_name": stats.get("collection_name"),
        "indexed_to_vector": True,
    }


def _extract_text_content(file_content: bytes) -> str:
    """
    Extract text from file content (handles UTF-8 and PDF).

    Args:
        file_content: Raw file bytes

    Returns:
        str: Extracted text
    """
    try:
        return file_content.decode("utf-8")
    except UnicodeDecodeError:
        # Try to extract from PDF
        import fitz

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            with fitz.open(tmp_path) as doc:
                text = "".join(page.get_text() for page in doc)
            return text
        finally:
            os.unlink(tmp_path)
