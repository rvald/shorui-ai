"""
Tests for GroundedGenerator and grounding domain models.
"""

from __future__ import annotations

import pytest

from app.rag.domain.grounding import AnswerResult, RetrievalResult, RetrievalSource
from app.rag.services.grounded_generator import GroundedGenerator


# --- Fixtures ---


class FakeGenerator:
    """Fake generator that returns predictable answers with citations."""

    def __init__(self, answer: str = "Test answer [SOURCE: src-1]"):
        self.answer = answer
        self.generate_calls = []

    async def generate(self, query: str, context: str | None = None, max_tokens: int = 2048):
        self.generate_calls.append({"query": query, "context": context})
        return {"answer": self.answer, "model": "fake", "backend": "fake"}


@pytest.fixture
def fake_generator():
    return FakeGenerator()


@pytest.fixture
def sample_sources():
    return [
        RetrievalSource(
            source_id="src-1",
            content_snippet="HIPAA requires covered entities to protect PHI.",
            score=0.92,
            metadata={"filename": "hipaa_guide.pdf", "page_num": 5},
        ),
        RetrievalSource(
            source_id="src-2",
            content_snippet="The Privacy Rule establishes standards for PHI.",
            score=0.88,
            metadata={"filename": "privacy_rule.pdf", "page_num": 12},
        ),
    ]


@pytest.fixture
def retrieval_result(sample_sources):
    return RetrievalResult(
        sources=sample_sources,
        query_analysis={"keywords": ["hipaa", "phi"], "intent": "information"},
        is_sufficient=True,
    )


@pytest.fixture
def grounded_generator(fake_generator):
    return GroundedGenerator(
        base_generator=fake_generator,
        min_sources=1,
        require_citations=True,
    )


# --- Domain Model Tests ---


class TestRetrievalSource:
    def test_create_source(self):
        source = RetrievalSource(
            source_id="test-id",
            content_snippet="Test content",
            score=0.95,
            metadata={"filename": "test.pdf"},
        )
        assert source.source_id == "test-id"
        assert source.score == 0.95


class TestRetrievalResult:
    def test_from_documents_empty(self):
        result = RetrievalResult.from_documents([], min_sources=1)
        assert len(result.sources) == 0
        assert result.is_sufficient is False

    def test_from_documents_sufficient(self):
        docs = [
            {"id": "doc-1", "content": "Content 1", "score": 0.9, "filename": "a.pdf"},
            {"id": "doc-2", "content": "Content 2", "score": 0.8, "filename": "b.pdf"},
        ]
        result = RetrievalResult.from_documents(docs, min_sources=1)
        assert len(result.sources) == 2
        assert result.is_sufficient is True

    def test_from_documents_excludes_graph_results(self):
        docs = [
            {"id": "doc-1", "content": "Vector content", "score": 0.9},
            {"id": "graph-1", "content": "Graph content", "score": 1.0, "is_graph": True},
        ]
        result = RetrievalResult.from_documents(docs, min_sources=1)
        assert len(result.sources) == 1
        assert result.sources[0].source_id == "doc-1"


class TestAnswerResult:
    def test_refusal_factory(self):
        result = AnswerResult.refusal("insufficient_sources")
        assert result.is_refusal is True
        assert result.refusal_reason == "insufficient_sources"
        assert "don't have enough information" in result.answer_text

    def test_normal_answer(self):
        result = AnswerResult(
            answer_text="The answer is 42.",
            citations=["src-1"],
        )
        assert result.is_refusal is False
        assert result.refusal_reason is None


# --- GroundedGenerator Tests ---


class TestGroundedGeneratorRefusal:
    @pytest.mark.asyncio
    async def test_refuses_when_no_sources(self, grounded_generator):
        empty_result = RetrievalResult(sources=[], is_sufficient=False)
        
        answer = await grounded_generator.generate_grounded(
            query="What is HIPAA?",
            retrieval_result=empty_result,
        )
        
        assert answer.is_refusal is True
        assert answer.refusal_reason == "insufficient_sources"
        assert answer.citations == []

    @pytest.mark.asyncio
    async def test_refuses_below_threshold(self, fake_generator, sample_sources):
        # Require 5 sources but only have 2
        generator = GroundedGenerator(
            base_generator=fake_generator,
            min_sources=5,
        )
        result = RetrievalResult(sources=sample_sources, is_sufficient=False)
        
        answer = await generator.generate_grounded(
            query="What is HIPAA?",
            retrieval_result=result,
        )
        
        assert answer.is_refusal is True


class TestGroundedGeneratorCitations:
    @pytest.mark.asyncio
    async def test_extracts_citations(self, grounded_generator, retrieval_result):
        answer = await grounded_generator.generate_grounded(
            query="What is HIPAA?",
            retrieval_result=retrieval_result,
        )
        
        assert answer.is_refusal is False
        assert "src-1" in answer.citations

    @pytest.mark.asyncio
    async def test_validates_citations_against_sources(self, retrieval_result):
        # Generator cites an unknown source
        bad_generator = FakeGenerator(answer="Answer [SOURCE: unknown-id]")
        grounded = GroundedGenerator(base_generator=bad_generator, min_sources=1)
        
        answer = await grounded.generate_grounded(
            query="Test?",
            retrieval_result=retrieval_result,
        )
        
        # Unknown citation should not appear in validated citations
        assert "unknown-id" not in answer.citations


class TestGroundedGeneratorContext:
    @pytest.mark.asyncio
    async def test_labels_sources_in_context(self, fake_generator, retrieval_result):
        grounded = GroundedGenerator(base_generator=fake_generator, min_sources=1)
        
        await grounded.generate_grounded(
            query="Test?",
            retrieval_result=retrieval_result,
        )
        
        # Check the context passed to the generator
        assert len(fake_generator.generate_calls) == 1
        context = fake_generator.generate_calls[0]["context"]
        
        assert "[SOURCE: src-1]" in context
        assert "[SOURCE: src-2]" in context
        assert "IMPORTANT SECURITY RULES" in context  # Injection defense


# --- Refusal Reason Constants Tests ---


class TestRefusalReasonConstants:
    def test_constants_are_defined(self):
        from app.rag.domain.grounding import (
            REFUSAL_INSUFFICIENT_SOURCES,
            REFUSAL_COLLECTION_NOT_FOUND,
            REFUSAL_NO_RELEVANT_CONTENT,
            REFUSAL_GENERATION_ERROR,
        )
        
        assert REFUSAL_INSUFFICIENT_SOURCES == "insufficient_sources"
        assert REFUSAL_COLLECTION_NOT_FOUND == "collection_not_found"
        assert REFUSAL_NO_RELEVANT_CONTENT == "no_relevant_content"
        assert REFUSAL_GENERATION_ERROR == "generation_error"

    def test_refusal_with_custom_reason(self):
        from app.rag.domain.grounding import REFUSAL_COLLECTION_NOT_FOUND
        
        result = AnswerResult.refusal(REFUSAL_COLLECTION_NOT_FOUND)
        assert result.refusal_reason == "collection_not_found"
        assert result.is_refusal is True

