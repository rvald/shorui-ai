"""
RAG API routes for the unified application.

This module provides endpoints for RAG (Retrieval-Augmented Generation):
- POST /rag/query - Full RAG: retrieve + generate
- GET /rag/search - Search-only: retrieve without LLM
"""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from app.rag.factory import get_generator, get_retriever
from shorui_core.auth.dependencies import require_rag_read
from shorui_core.domain.auth import AuthContext

router = APIRouter()


# --- Request/Response Models ---


class QueryRequest(BaseModel):
    """Request model for RAG query."""

    query: str = Field(..., description="The question to answer")
    project_id: str = Field(..., description="Project identifier")
    k: int = Field(default=5, ge=1, le=20, description="Number of documents to retrieve")
    backend: str = Field(default="openai", description="LLM backend: 'openai' or 'runpod'")


class SourceDocument(BaseModel):
    """A source document used for the answer."""

    filename: str | None = None
    page_num: int | None = None
    score: float
    content_preview: str


class QueryResponse(BaseModel):
    """Response model for RAG query."""

    answer: str
    sources: list[SourceDocument] = []
    query: str


class SearchResult(BaseModel):
    """A search result item."""

    id: str
    score: float
    content: str
    filename: str | None = None
    page_num: int | None = None
    project_id: str | None = None


class SearchResponse(BaseModel):
    """Response model for search."""

    results: list[SearchResult]
    query: str
    k: int


# --- Endpoints ---


@router.get("/health")
def rag_health():
    """Health check for the RAG module."""
    return {"status": "ok", "module": "rag"}


@router.post("/query", response_model=QueryResponse)
async def rag_query(
    request: QueryRequest,
    auth: AuthContext = Depends(require_rag_read),
):
    """
    Full RAG query: retrieve context and generate answer.

    This endpoint:
    1. Searches for relevant documents in Qdrant
    2. Uses the documents as context for the LLM
    3. Returns a generated answer with sources
    """
    logger.info(f"RAG query: '{request.query}' for project '{request.project_id}'")

    try:
        # Retrieve context using factory
        retriever = get_retriever()
        
        # Note: We use the full retrieve pipeline here which returns a dict
        # matching what the route expects (documents list inside a dict)
        retrieval_result = await retriever.retrieve(
            query=request.query, project_id=request.project_id, k=request.k
        )
        search_results = retrieval_result["documents"]

        if not search_results:
            return QueryResponse(
                answer="I couldn't find any relevant documents for your question. Please try rephrasing or ensure documents have been indexed.",
                sources=[],
                query=request.query,
            )

        # Build context string from search results
        context_parts = []
        for i, result in enumerate(search_results, 1):
            if result.get("is_graph"):
                 context_parts.append(result.get("content", ""))
            else:
                source = result.get("filename", "unknown")
                page = result.get("page_num", "?")
                content = result.get("content", "")
                context_parts.append(f"[Source {i}: {source}, page {page}]\n{content}")

        context_text = "\n\n".join(context_parts)

        # Generate answer using specified backend via factory
        generator = get_generator(backend=request.backend)
        generation_result = await generator.generate(
            query=request.query, context=context_text
        )

        # Build sources list
        sources = []
        for r in search_results[:5]:  # Top 5 sources
            if r.get("is_graph"):
                continue
                
            sources.append(
                SourceDocument(
                    filename=r.get("filename"),
                    page_num=r.get("page_num"),
                    score=r.get("score", 0),
                    content_preview=r.get("content", "")[:200] + "..."
                    if len(r.get("content", "")) > 200
                    else r.get("content", ""),
                )
            )

        return QueryResponse(
            answer=generation_result["answer"], sources=sources, query=request.query
        )

    except Exception as e:
        logger.exception(f"RAG query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=SearchResponse)
async def rag_search(
    query: str = Query(..., description="Search query"),
    project_id: str = Query(..., description="Project identifier"),
    k: int = Query(default=10, ge=1, le=50, description="Number of results"),
    auth: AuthContext = Depends(require_rag_read),
):
    """
    Search-only: retrieve documents without LLM generation.

    Useful for:
    - Exploring indexed documents
    - Debugging retrieval quality
    - Building custom RAG pipelines
    """
    logger.info(f"RAG search: '{query}' in project '{project_id}' (k={k})")

    try:
        retriever = get_retriever()
        
        # We use the search() method on the retriever for simple vector search
        # OR we could use retrieve() if we want the full pipeline output.
        # The original code used retrieval_service.search() which was a wrapper.
        # PipelineRetriever.search() is also a wrapper.
        # However, the endpoint expects specific fields.
        
        search_results = await retriever.search(query=query, project_id=project_id, k=k)

        results = [
            SearchResult(
                id=r["id"],
                score=r["score"],
                content=r["content"],
                filename=r.get("filename"),
                page_num=r.get("page_num"),
                project_id=r.get("project_id"),
            )
            for r in search_results
        ]

        return SearchResponse(results=results, query=query, k=k)

    except Exception as e:
        logger.exception(f"RAG search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
