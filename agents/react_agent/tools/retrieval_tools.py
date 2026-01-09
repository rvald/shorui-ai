"""
Retrieval Tools

Tools for semantic search and RAG over ingested documents.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

# Support both package import and direct script execution
try:
    from ..core.tools import Tool
    from ..infrastructure.http_clients import RAGClient
except ImportError:
    from core.tools import Tool
    from infrastructure.http_clients import RAGClient


class RAGSearchTool(Tool):
    """
    Semantic search tool using RAG (Retrieval-Augmented Generation).
    
    Searches over ingested documents and returns an AI-generated answer
    grounded in the retrieved context.
    
    Example:
        tool = RAGSearchTool()
        result = tool(query="What is the HIPAA Privacy Rule?", collection="hipaa_regulations")
    """
    
    name = "rag_search"
    description = (
        "Search over ingested documents using semantic search. "
        "Returns an AI-generated answer based on relevant documents. "
        "Use this to find information from HIPAA regulations, clinical notes, or policies."
    )
    inputs = {
        "query": {
            "type": "string",
            "description": "The search query or question to answer"
        }
    }
    output_type = "string"
    
    def __init__(self, rag_client: Optional[RAGClient] = None):
        """
        Initialize the RAG search tool.
        
        Args:
            rag_client: Optional RAGClient instance. Creates default if not provided.
        """
        self._client = rag_client or RAGClient()
    
    def forward(
        self,
        query: str,
        collection: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        """
        Execute the RAG search.
        
        Args:
            query: The search query
            collection: Collection to search (default: "multimodal_data")
            project_id: Optional project filter
            
        Returns:
            AI-generated answer based on retrieved documents
        """
        # Default collection
        collection_name = collection or "hipaa_regulations"
        
        try:
            # Run async client in sync context
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                self._client.search(
                    query=query,
                    collection_name=collection_name,
                    project_id=project_id,
                )
            )
            
            # Extract answer from response
            answer = result.get("answer", "")
            if not answer:
                return f"No results found for query: {query}"
            
            return answer
            
        except Exception as e:
            return f"Error performing RAG search: {e}"


class AsyncRAGSearchTool(RAGSearchTool):
    """
    Async version of RAGSearchTool for use in async contexts.
    """
    
    async def async_forward(
        self,
        query: str,
        collection: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        """
        Execute the RAG search asynchronously.
        
        Args:
            query: The search query
            collection: Collection to search (default: "multimodal_data")
            project_id: Optional project filter
            
        Returns:
            AI-generated answer based on retrieved documents
        """
        collection_name = collection or "hipaa_regulations"
        
        try:
            result = await self._client.search(
                query=query,
                collection_name=collection_name,
                project_id=project_id,
            )
            
            answer = result.get("answer", "")
            if not answer:
                return f"No results found for query: {query}"
            
            return answer
            
        except Exception as e:
            return f"Error performing RAG search: {e}"
