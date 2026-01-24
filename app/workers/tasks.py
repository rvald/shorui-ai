"""
Celery task definitions for document processing.

This module contains the Celery tasks that handle async document ingestion.
Tasks delegate to specialized orchestrators for the actual processing logic.
"""

from app.workers.celery_app import celery_app
from app.ingestion.services.orchestrator import get_ingestion_orchestrator
from app.ingestion.services.job_ledger import JobLedgerService

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
    tenant_id: str,
    project_id: str,
    raw_pointer: str,
    filename: str,
    content_type: str,
    document_type: str = "general",  # "general", "hipaa_regulation"
    index_to_vector: bool = True,
    index_to_graph: bool = False,
    # Regulation-specific metadata
    source: str = None,
    title: str = None,
    category: str = None,
    idempotency_key: str | None = None,
) -> dict:
    """
    Celery task to process an uploaded document using pointer-based artifacts.
    """
    ledger_service = JobLedgerService()
    orchestrator = get_ingestion_orchestrator()

    # Idempotency short-circuit (skip if completed)
    if idempotency_key:
        existing = ledger_service.check_idempotency(
            idempotency_key=idempotency_key,
            job_type="ingestion_document",
            tenant_id=tenant_id,
            project_id=project_id,
        )
        if existing and existing.get("status") == "completed":
            ledger_service.update_status(job_id, "skipped", progress=100)
            return {
                "status": "skipped",
                "existing_job_id": existing["job_id"],
                "result_pointer": existing.get("result_pointer"),
            }

    ledger_service.update_status(job_id, "processing", progress=10)

    try:
        result = orchestrator.process(
            job_id=job_id,
            raw_pointer=raw_pointer,
            filename=filename,
            tenant_id=tenant_id,
            project_id=project_id,
            document_type=document_type,
            content_type=content_type,
            index_to_vector=index_to_vector,
            index_to_graph=index_to_graph,
            source=source,
            title=title,
            category=category,
        )

        ledger_service.complete_job(
            job_id,
            items_indexed=result.get("chunks_created", 0),
            result_pointer=result.get("result_pointer"),
            processed_pointer=result.get("processed_pointer"),
            result_artifacts=[
                {
                    "type": "ingestion_result",
                    "pointer": result.get("result_pointer"),
                    "collection_name": result.get("collection_name"),
                }
            ]
            if result.get("result_pointer")
            else None,
        )
        return result

    except Exception as exc:
        ledger_service.fail_job(job_id, error=str(exc))
        ledger_service.add_to_dlq(job_id, error=str(exc), traceback=None)
        raise
