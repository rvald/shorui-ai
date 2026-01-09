"""
Document Management Tools

Tools for uploading documents and checking ingestion status.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

# Support both package import and direct script execution
try:
    from ..core.tools import Tool
    from ..infrastructure.http_clients import IngestionClient
except ImportError:
    from core.tools import Tool
    from infrastructure.http_clients import IngestionClient


class UploadDocumentTool(Tool):
    """
    Upload a document to the Shorui AI knowledge base.
    
    Supports PDF and Markdown files. Documents are processed asynchronously
    and indexed for semantic search.
    
    Example:
        tool = UploadDocumentTool()
        result = tool(file_path="/path/to/doc.pdf", project_id="my-project")
    """
    
    name = "upload_document"
    description = (
        "Upload and ingest a document (PDF or Markdown) into the knowledge base. "
        "Returns a job_id to track processing status. "
        "Use check_ingestion_status to poll for completion."
    )
    inputs = {
        "file_path": {
            "type": "string",
            "description": "Local path to the file to upload"
        },
        "project_id": {
            "type": "string",
            "description": "Project/tenant identifier"
        },
        "category": {
            "type": "string",
            "description": "Optional category (e.g., 'policy', 'regulation')",
            "nullable": True,
        },
        "document_type": {
            "type": "string",
            "description": "Document type: 'general' or 'hipaa_regulation'",
            "nullable": True,
        }
    }
    output_type = "string"
    
    def __init__(self, client: Optional[IngestionClient] = None):
        self._client = client or IngestionClient()
    
    def forward(
        self,
        file_path: str,
        project_id: str,
        category: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> str:
        """Upload a document and return the job_id."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                self._client.upload_document(
                    file_path=file_path,
                    project_id=project_id,
                    category=category,
                    document_type=document_type or "general",
                )
            )
            
            job_id = result.get("job_id", "unknown")
            message = result.get("message", "Document queued")
            return f"Upload successful. Job ID: {job_id}. {message}"
            
        except FileNotFoundError:
            return f"Error: File not found: {file_path}"
        except Exception as e:
            return f"Error uploading document: {e}"


class CheckIngestionStatusTool(Tool):
    """
    Check the status of a document ingestion job.
    
    Example:
        tool = CheckIngestionStatusTool()
        result = tool(job_id="abc-123")
    """
    
    name = "check_ingestion_status"
    description = (
        "Check if a document upload job has completed. "
        "Returns status: 'pending', 'processing', 'completed', or 'failed'."
    )
    inputs = {
        "job_id": {
            "type": "string",
            "description": "The job ID returned from upload_document"
        }
    }
    output_type = "string"
    
    def __init__(self, client: Optional[IngestionClient] = None):
        self._client = client or IngestionClient()
    
    def forward(self, job_id: str) -> str:
        """Check ingestion status for a job."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                self._client.check_status(job_id)
            )
            
            status = result.get("status", "unknown")
            progress = result.get("progress")
            error = result.get("error")
            
            if error:
                return f"Job {job_id}: FAILED - {error}"
            elif progress is not None:
                return f"Job {job_id}: {status.upper()} ({progress}% complete)"
            else:
                return f"Job {job_id}: {status.upper()}"
            
        except Exception as e:
            return f"Error checking status: {e}"
