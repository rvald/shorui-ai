"""
Celery task definitions for document processing.

This module contains the Celery tasks that handle async document ingestion.
Tasks delegate to specialized orchestrators for the actual processing logic.
"""

from app.workers.celery_app import celery_app
from app.workers.decorators import track_job_ledger
from app.ingestion.services.orchestrator import get_ingestion_orchestrator

@celery_app.task(
    bind=True,
    name="app.workers.tasks.process_document",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
@track_job_ledger(content_arg="file_content")
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
    """
    orchestrator = get_ingestion_orchestrator()
    return orchestrator.process(
        job_id=job_id,
        file_content=file_content,
        filename=filename,
        project_id=project_id,
        document_type=document_type,
        content_type=content_type,
        index_to_vector=index_to_vector,
        index_to_graph=index_to_graph,
        source=source,
        title=title,
        category=category,
    )
