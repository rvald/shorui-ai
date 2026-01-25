import functools
import inspect
from loguru import logger

from app.ingestion.services.job_ledger import JobLedgerService
from shorui_core.artifacts import JobType


def track_job_ledger(content_arg: str, job_type: JobType = JobType.COMPLIANCE_TRANSCRIPT):
    """
    Decorator to handle JobLedger lifecycle for Celery tasks.

    Handles:
    1. Idempotency check (computing hash from content_arg).
    2. Creating job in ledger.
    3. Updating status to 'processing'.
    4. Completing job on success (with items_indexed stats).
    5. Failing job on exception.
    6. Adding to DLQ on failure.

    Args:
        content_arg: Name of the argument containing the file content/text for hashing.
        job_type: JobType enum for this task (default: COMPLIANCE_TRANSCRIPT).
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Resolve arguments to find job_id, project_id, tenant_id, filename, and content
            sig = inspect.signature(func)
            bound_args = sig.bind(self, *args, **kwargs)
            bound_args.apply_defaults()
            
            job_id = bound_args.arguments.get("job_id")
            project_id = bound_args.arguments.get("project_id")
            tenant_id = bound_args.arguments.get("tenant_id", "default")
            filename = bound_args.arguments.get("filename")
            content = bound_args.arguments.get(content_arg)

            if not all([job_id, project_id, filename]):
                logger.error(
                    f"Missing required args for ledger tracking: "
                    f"job_id={job_id}, project_id={project_id}"
                )
                # Still run the function, but can't track it
                return func(self, *args, **kwargs)

            ledger_service = JobLedgerService()

            try:
                # 1. Compute Hash
                if isinstance(content, str):
                    content_bytes = content.encode("utf-8")
                elif isinstance(content, bytes):
                    content_bytes = content
                else:
                    content_bytes = b""
                
                content_hash = ledger_service.compute_content_hash(content_bytes)

                # 2. Idempotency Check
                existing = ledger_service.check_idempotency(
                    idempotency_key=content_hash,
                    job_type=job_type.value,
                    tenant_id=tenant_id,
                    project_id=project_id,
                )
                if existing and existing.get("status") == "completed":
                    logger.info(
                        f"[{job_id}] Document already processed (job: {existing['job_id']})"
                    )
                    return {
                        "status": "skipped",
                        "existing_job_id": existing["job_id"],
                        "message": "Document already processed (idempotent)",
                    }

                # 3. Create Job
                try:
                    ledger_service.create_job(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        job_type=job_type,
                        job_id=job_id,
                        idempotency_key=content_hash,
                        document_type=filename,
                        raw_pointer=f"pending:{job_id}",
                    )
                    ledger_service.update_status(job_id, "processing", progress=10)
                except Exception as e:
                    logger.warning(f"[{job_id}] Ledger create failed (continuing): {e}")

                # 4. Run Task
                result = func(self, *args, **kwargs)

                # 5. Complete Job
                items_indexed = (
                    result.get("chunks_created") or result.get("phi_detected") or 0
                )
                
                # Store transcript_id and report_id in result_artifacts for retrieval
                result_artifacts = {
                    "transcript_id": result.get("transcript_id"),
                    "report_id": result.get("report_id"),
                }
                
                try:
                    ledger_service.complete_job(
                        job_id, 
                        items_indexed=items_indexed,
                        result_artifacts=[result_artifacts],
                    )
                except Exception as e:
                    logger.warning(f"[{job_id}] Ledger complete failed: {e}")

                return result

            except Exception as e:
                logger.exception(f"[{job_id}] Task failed: {e}")
                
                # 6. Fail Job & DLQ
                try:
                    ledger_service.fail_job(job_id, error=str(e))
                    ledger_service.add_to_dlq(job_id, error=str(e), traceback=None)
                except Exception:
                    pass
                
                # Re-raise for Celery retry
                raise

        return wrapper
    return decorator

