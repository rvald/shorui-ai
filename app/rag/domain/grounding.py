"""
Domain models for grounded RAG contract.

These models define the structured interfaces for retrieval and generation,
enforcing citation-based grounding in RAG responses.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# Refusal reason constants
REFUSAL_INSUFFICIENT_SOURCES = "insufficient_sources"
REFUSAL_COLLECTION_NOT_FOUND = "collection_not_found"
REFUSAL_NO_RELEVANT_CONTENT = "no_relevant_content"
REFUSAL_GENERATION_ERROR = "generation_error"


class RetrievalSource(BaseModel):
    """A single retrieved source document."""

    source_id: str = Field(..., description="Stable ID from vector DB")
    content_snippet: str = Field(..., description="Retrieved text content")
    score: float = Field(..., description="Similarity/relevance score")
    metadata: dict = Field(
        default_factory=dict,
        description="Source metadata: filename, page, chunk_id, doc_hash",
    )


class RetrievalResult(BaseModel):
    """Result of a retrieval operation with sufficiency signal."""

    sources: list[RetrievalSource] = Field(default_factory=list)
    query_analysis: dict = Field(
        default_factory=dict, description="Intent, keywords, expansions"
    )
    is_sufficient: bool = Field(
        default=False, description="True if sources meet minimum threshold"
    )

    @classmethod
    def from_documents(
        cls,
        documents: list[dict],
        query_analysis: dict | None = None,
        min_sources: int = 1,
    ) -> "RetrievalResult":
        """Factory method to create from raw retrieval documents."""
        sources = [
            RetrievalSource(
                source_id=doc.get("id", ""),
                content_snippet=doc.get("content", ""),
                score=doc.get("score", 0.0),
                metadata={
                    "filename": doc.get("filename"),
                    "page_num": doc.get("page_num"),
                    "project_id": doc.get("project_id"),
                    "block_id": doc.get("block_id"),
                    "section_id": doc.get("section_id"),
                },
            )
            for doc in documents
            if not doc.get("is_graph")  # Exclude graph-expanded results
        ]
        return cls(
            sources=sources,
            query_analysis=query_analysis or {},
            is_sufficient=len(sources) >= min_sources,
        )


class AnswerResult(BaseModel):
    """Result of a grounded generation with citation tracking."""

    answer_text: str = Field(..., description="Generated answer text")
    citations: list[str] = Field(
        default_factory=list, description="source_ids referenced in answer"
    )
    refusal_reason: str | None = Field(
        default=None, description="Reason for refusing to answer, if applicable"
    )
    confidence: float | None = Field(
        default=None, description="Optional confidence score"
    )

    @property
    def is_refusal(self) -> bool:
        """Check if this result is a refusal to answer."""
        return self.refusal_reason is not None

    @classmethod
    def refusal(cls, reason: str) -> "AnswerResult":
        """Factory method for refusal responses."""
        return cls(
            answer_text="I don't have enough information from the indexed documents to answer this question.",
            citations=[],
            refusal_reason=reason,
        )
