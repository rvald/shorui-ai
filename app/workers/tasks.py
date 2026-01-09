"""
Celery task definitions for document processing.

This module contains the Celery tasks that handle async document ingestion.
"""

import os
import tempfile

from loguru import logger

from app.ingestion.services.chunking import ChunkingService
from app.ingestion.services.embedding import EmbeddingService
from app.ingestion.services.indexing import IndexingService
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
    - "general": Standard chunking → embeddings → Qdrant
    - "hipaa_regulation": Uses HIPAARegulationService for specialized processing

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

    # Initialize services
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
        try:
            storage_path = storage_service.upload(file_content, filename, project_id)
            logger.info(f"[{job_id}] Uploaded to MinIO: {storage_path}")
        except Exception as e:
            logger.warning(f"[{job_id}] MinIO upload failed (continuing): {e}")
            storage_path = None

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
            # Use specialized HIPAA regulation service
            from app.compliance.services.hipaa_regulation_service import HIPAARegulationService

            logger.info(f"[{job_id}] Processing as HIPAA regulation")

            # Decode text content
            try:
                text = file_content.decode("utf-8")
            except UnicodeDecodeError:
                # Try to extract from PDF
                import fitz

                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(file_content)
                    tmp_path = tmp.name
                with fitz.open(tmp_path) as doc:
                    text = "".join(page.get_text() for page in doc)
                os.unlink(tmp_path)

            service = HIPAARegulationService()
            stats = service.ingest_regulation(
                text=text,
                source=source or filename,
                title=title,
                category=category or "privacy_rule",
            )

            ledger_service.complete_job(job_id, items_indexed=stats.get("chunks_created", 0))

            return {
                "status": "completed",
                "document_type": "hipaa_regulation",
                "chunks_created": stats.get("chunks_created", 0),
                "sections_found": stats.get("sections_found", []),
                "storage_path": storage_path,
            }

        # ===== GENERAL DOCUMENT PROCESSING =====

        # 5. Save file to temp location for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        logger.info(f"[{job_id}] Saved file to {tmp_path}")

        # Determine if this is a text file for simple processing
        is_text = content_type == "text/plain" or filename.lower().endswith(".txt")

        if is_text:
            # Read text directly
            with open(tmp_path, encoding="utf-8", errors="ignore") as f:
                text = f.read()

            logger.info(f"[{job_id}] Read {len(text)} characters from text file")
            ledger_service.update_status(job_id, "processing", progress=40)

            # Chunk the text
            chunking_service = ChunkingService()
            chunks = chunking_service.chunk(text)

            logger.info(f"[{job_id}] Created {len(chunks)} chunks")

            texts_to_embed = chunks
            metadata_list = [
                {
                    "project_id": project_id,
                    "filename": filename,
                    "content_type": content_type,
                    "chunk_index": i,
                }
                for i in range(len(chunks))
            ]

            num_items = len(chunks)
        else:
            # For other file types, log a warning
            logger.warning(
                f"[{job_id}] Unsupported file type: {content_type}. Use /clinical-transcripts for clinical data."
            )
            texts_to_embed = []
            metadata_list = []
            num_items = 0

        # 6. Generate embeddings and index to vector database
        if index_to_vector and texts_to_embed:
            embedding_service = EmbeddingService()
            embeddings = embedding_service.embed(texts_to_embed)

            logger.info(f"[{job_id}] Generated {len(embeddings)} embeddings")
            ledger_service.update_status(job_id, "processing", progress=70)

            # Index to vector database
            indexing_service = IndexingService()
            collection_name = f"project_{project_id}"
            indexing_service.index(texts_to_embed, embeddings, metadata_list, collection_name)

            logger.info(
                f"[{job_id}] Indexed {len(texts_to_embed)} items to Qdrant '{collection_name}'"
            )

        # 8. Update ledger with completion
        try:
            ledger_service.complete_job(job_id, items_indexed=num_items)
        except Exception as e:
            logger.warning(f"[{job_id}] Ledger complete failed: {e}")

        # Cleanup temp file
        os.unlink(tmp_path)

        # Determine file type for result
        is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")
        graph_stats = None  # Graph ingestion not implemented in this task

        result = {
            "status": "completed",
            "items_indexed": num_items,
            "is_pdf": is_pdf,
            "indexed_to_vector": index_to_vector,
            "indexed_to_graph": index_to_graph,
            "storage_path": storage_path,
            "graph_stats": graph_stats,
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
