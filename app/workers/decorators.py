import functools
from loguru import logger
from app.ingestion.services.job_ledger import JobLedgerService

def track_job_ledger(content_arg: str):
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
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Resolve arguments to find job_id, project_id, filename, and content
            # Inspect signature to map args to names if needed, but Celery usually passes kwargs
            # or positional args. We'll assume job_id is explicit or in kwargs.
            
            # For robustness, we assume the signature is (self, job_id, ...) like our tasks
            # If strictly kwargs, we get them from kwargs.
            
            # Helper to get arg value
            import inspect
            sig = inspect.signature(func)
            bound_args = sig.bind(self, *args, **kwargs)
            bound_args.apply_defaults()
            
            job_id = bound_args.arguments.get("job_id")
            project_id = bound_args.arguments.get("project_id")
            filename = bound_args.arguments.get("filename")
            content = bound_args.arguments.get(content_arg)

            if not all([job_id, project_id, filename]):
                 # If we can't find core tracking info, warn and run untracked (?) 
                 # or fail hard. Fail hard is safer for a tracked system.
                 logger.error(f"Missing required args for ledger tracking: job_id={job_id}, project_id={project_id}, filename={filename}")
                 # We still run the function, assuming it might handle itself or fail.
                 # But we can't track it.
                 return func(self, *args, **kwargs)

            ledger_service = JobLedgerService()

            try:
                # 1. Compute Hash
                if isinstance(content, str):
                    content_bytes = content.encode("utf-8")
                elif isinstance(content, bytes):
                    content_bytes = content
                else:
                    content_bytes = b"" # Should probably not happen
                
                content_hash = ledger_service.compute_content_hash(content_bytes)

                # 2. Idempotency Check
                existing = ledger_service.check_idempotency(project_id, filename, content_hash)
                if existing and existing.get("status") == "completed":
                    logger.info(f"[{job_id}] Document already processed (job: {existing['job_id']})")
                    return {
                        "status": "skipped",
                        "existing_job_id": existing["job_id"],
                        "message": "Document already processed (idempotent)",
                    }

                # 3. Create Job
                # Note: Storage path is unknown here until Orchestrator runs. 
                # We put a placeholder or let Orchestrator update it?
                # The original code created the job here.
                # We will set a temporary storage path.
                try:
                    ledger_service.create_job(
                        project_id=project_id,
                        filename=filename,
                        storage_path=f"pending:{job_id}", 
                        content_hash=content_hash,
                        job_id=job_id,
                    )
                    ledger_service.update_status(job_id, "processing", progress=10)
                except Exception as e:
                    logger.warning(f"[{job_id}] Ledger create failed (continuing): {e}")

                # 4. Run Task
                result = func(self, *args, **kwargs)

                # 5. Complete Job
                # Orchestrator might return stats like 'items_indexed' or 'phi_detected'
                items_indexed = result.get("chunks_created") or result.get("phi_detected") or 0
                
                try:
                    ledger_service.complete_job(job_id, items_indexed=items_indexed)
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
