from typing import Protocol, Any, Dict
from datetime import datetime

from app.ingestion.services.document_ingestion_service import DocumentIngestionService
from app.ingestion.services.storage import get_storage_backend
from loguru import logger

class DocumentProcessor(Protocol):
    """Protocol for document processing strategies."""
    def process(self, content: bytes, filename: str, **kwargs) -> Dict[str, Any]:
        """
        Process a document.
        
        Args:
            content: Raw document bytes.
            filename: Name of the file.
            **kwargs: Additional metadata/options specific to the processor.
            
        Returns:
            Dict containing processing statistics.
        """
        ...

class GeneralDocumentProcessor:
    """Processor for general documents (PDFs, TXT, etc.)."""
    def process(self, content: bytes, filename: str, **kwargs) -> Dict[str, Any]:
        project_id = kwargs.get("project_id")
        content_type = kwargs.get("content_type", "application/octet-stream")
        index_to_vector = kwargs.get("index_to_vector", True)

        if not index_to_vector:
            logger.info("Skipping vector indexing for document")
            return {
                "document_type": "general",
                "chunks_created": 0,
                "indexed_to_vector": False,
            }

        service = DocumentIngestionService()
        stats = service.ingest_document(
            content=content,
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


class HipaaRegulationProcessor:
    """Processor for HIPAA regulation documents."""
    def process(self, content: bytes, filename: str, **kwargs) -> Dict[str, Any]:
        from app.compliance.services.hipaa_regulation_service import HIPAARegulationService
        
        text = _extract_text_content(content)


        source = kwargs.get("source")
        title = kwargs.get("title")
        category = kwargs.get("category")

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

def _extract_text_content(file_content: bytes) -> str:
    """
    Extract text from file content (handles UTF-8 and PDF).
    """
    import os
    import tempfile
    
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
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class IngestionOrchestrator:
    """
    Orchestrates the ingestion process:
    1. Uploads to Storage (MinIO).
    2. Routes to correct Processor.
    """
    
    def __init__(self):
        self.storage_service = get_storage_backend()
        self.processors: Dict[str, DocumentProcessor] = {
            "general": GeneralDocumentProcessor(),
            "hipaa_regulation": HipaaRegulationProcessor(),
        }
        self.raw_bucket = getattr(self.storage_service, "raw_bucket", None)
        self.processed_bucket = getattr(self.storage_service, "processed_bucket", None)

    def process(
        self,
        job_id: str,
        raw_pointer: str,
        filename: str,
        tenant_id: str,
        project_id: str,
        content_type: str,
        document_type: str = "general",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute the ingestion flow.
        """
        logger.info(f"[{job_id}] Orchestrating ingestion (type={document_type})")

        # 1. Download raw content by pointer
        file_content = self.storage_service.download(raw_pointer)

        # 2. Select Processor
        processor = self.processors.get(document_type)
        if not processor:
            raise ValueError(f"Unsupported document_type: {document_type}")

        # 3. Process
        stats = processor.process(
            content=file_content, 
            filename=filename, 
            project_id=project_id,
            storage_path=raw_pointer,
            tenant_id=tenant_id,
            content_type=content_type,
            **kwargs
        )

        result_payload = {
            "job_id": job_id,
            "status": "completed",
            "document_type": document_type,
            "raw_pointer": raw_pointer,
            "items_indexed": stats.get("chunks_created", 0),
            "collection_name": stats.get("collection_name"),
            "indexed_to_vector": stats.get("indexed_to_vector", True),
            "timestamp": datetime.utcnow().isoformat(),
        }

        result_pointer = self.storage_service.upload_json(
            payload=result_payload,
            filename=f"{job_id}.json",
            tenant_id=tenant_id,
            project_id=project_id,
            bucket=self.processed_bucket,
        )

        result = {
            "status": "completed",
            "raw_pointer": raw_pointer,
            "result_pointer": result_pointer,
            **stats,
        }

        return result

def get_ingestion_orchestrator() -> IngestionOrchestrator:
    return IngestionOrchestrator()
