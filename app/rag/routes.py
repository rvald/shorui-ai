"""
RAG API routes for the unified application.

This module provides endpoints for RAG (Retrieval-Augmented Generation):
- POST /rag/query - Full RAG: retrieve + generate (grounded, citation-enforced)
- GET /rag/search - Search-only: retrieve without LLM
"""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from app.rag.domain.grounding import (
    RetrievalResult,
    REFUSAL_COLLECTION_NOT_FOUND,
    REFUSAL_NO_RELEVANT_CONTENT,
)
from app.rag.factory import collection_exists, get_grounded_generator, get_retriever
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
    min_sources: int = Field(default=1, ge=0, le=10, description="Minimum sources required")


class SourceDocument(BaseModel):
    """A source document used for the answer."""

    source_id: str | None = None
    filename: str | None = None
    page_num: int | None = None
    score: float
    content_preview: str


class QueryResponse(BaseModel):
    """Response model for RAG query."""

    answer: str
    sources: list[SourceDocument] = []
    citations: list[str] = Field(default_factory=list, description="source_ids cited")
    refusal_reason: str | None = Field(default=None, description="Reason for refusal")
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
    Full RAG query: retrieve context and generate grounded answer.

    This endpoint:
    1. Checks if the collection exists (fast, no LLM cost)
    2. Runs a probe search to check for relevant content (1 embedding, no LLM)
    3. If relevant content exists, runs full pipeline with query expansion
    4. Generates a citation-enforced answer
    5. Returns answer with citations and sources
    """
    logger.info(f"RAG query: '{request.query}' for project '{request.project_id}'")

    try:
        # 1. Early check: Does the collection exist? (no LLM cost)
        if not collection_exists(request.project_id):
            logger.info(f"Collection not found for project '{request.project_id}' - early refusal")
            return QueryResponse(
                answer="I don't have enough information from the indexed documents to answer this question.",
                sources=[],
                citations=[],
                refusal_reason=REFUSAL_COLLECTION_NOT_FOUND,
                query=request.query,
            )

        # 2. Probe search: Quick check for relevant content (1 embedding, no query expansion)
        retriever = get_retriever()
        probe_results = await retriever.search(
            query=request.query,
            project_id=request.project_id,
            k=1,
        )
        
        # Check if probe found anything relevant (score threshold)
        PROBE_SCORE_THRESHOLD = 0.3
        if not probe_results or probe_results[0].get("score", 0) < PROBE_SCORE_THRESHOLD:
            logger.info(
                f"Probe search returned no relevant content (score < {PROBE_SCORE_THRESHOLD}) - early refusal"
            )
            return QueryResponse(
                answer="I don't have enough information from the indexed documents to answer this question.",
                sources=[],
                citations=[],
                refusal_reason=REFUSAL_NO_RELEVANT_CONTENT,
                query=request.query,
            )

        # 3. Full retrieval pipeline (now we know there's relevant content)
        logger.info("Probe successful - running full retrieval pipeline")
        raw_result = await retriever.retrieve(
            query=request.query, project_id=request.project_id, k=request.k
        )
        
        # 4. Convert to structured RetrievalResult
        retrieval_result = RetrievalResult.from_documents(
            documents=raw_result["documents"],
            query_analysis={
                "keywords": raw_result.get("keywords", []),
                "intent": raw_result.get("intent"),
                "is_gap_query": raw_result.get("is_gap_query", False),
            },
            min_sources=request.min_sources,
        )

        # 5. Generate grounded answer
        grounded_gen = get_grounded_generator(
            backend=request.backend,
            min_sources=request.min_sources,
        )
        answer_result = await grounded_gen.generate_grounded(
            query=request.query,
            retrieval_result=retrieval_result,
        )

        # 6. Build sources list from retrieval
        sources = [
            SourceDocument(
                source_id=src.source_id,
                filename=src.metadata.get("filename"),
                page_num=src.metadata.get("page_num"),
                score=src.score,
                content_preview=src.content_snippet[:200] + "..."
                if len(src.content_snippet) > 200
                else src.content_snippet,
            )
            for src in retrieval_result.sources[:5]
        ]

        return QueryResponse(
            answer=answer_result.answer_text,
            sources=sources,
            citations=answer_result.citations,
            refusal_reason=answer_result.refusal_reason,
            query=request.query,
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
