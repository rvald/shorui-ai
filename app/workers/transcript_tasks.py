"""
Celery task for async clinical transcript analysis.

Moves long-running HIPAA compliance analysis to background workers
to prevent API timeouts on large transcripts.
"""

import asyncio
from app.workers.celery_app import celery_app
from app.workers.decorators import track_job_ledger
from app.compliance.services.orchestrator import get_compliance_orchestrator

@celery_app.task(
    bind=True,
    name="app.workers.transcript_tasks.analyze_clinical_transcript",
    max_retries=2,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    time_limit=300,  # 5 minute hard limit
    soft_time_limit=240,  # 4 minute soft limit
)
@track_job_ledger(content_arg="text")
def analyze_clinical_transcript(
    self,
    job_id: str,
    text: str,
    filename: str,
    project_id: str,
) -> dict:
    """
    Celery task to analyze a clinical transcript for HIPAA compliance.
    """
    orchestrator = get_compliance_orchestrator()
    
    # Run async orchestrator method in sync context
    # Note: We use a new event loop or get current one if available
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    return loop.run_until_complete(
        orchestrator.analyze_transcript(
            job_id=job_id,
            text=text,
            filename=filename,
            project_id=project_id,
        )
    )
