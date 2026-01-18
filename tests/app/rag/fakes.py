from __future__ import annotations
"""
Fake implementations of RAG protocols for testing.
"""

from typing import Any

from app.rag.protocols import GenerativeModel, GraphRetriever, QueryAnalyzer, Reranker, Retriever


class FakeGenerativeModel(GenerativeModel):
    def __init__(self, answer: str = "Fake answer"):
        self.answer = answer
        self.last_query = None
        self.last_context = None

    async def generate(
        self, query: str, context: str | None = None, max_tokens: int = 2048
    ) -> dict[str, Any]:
        self.last_query = query
        self.last_context = context
        return {"answer": self.answer, "model": "fake-model", "backend": "fake"}


class FakeQueryAnalyzer(QueryAnalyzer):
    def __init__(self, keywords: list[str] = None, expanded: list[str] = None):
        self.keywords = keywords or ["fake", "keyword"]
        self.expanded = expanded
        self.process_calls = []

    def process(self, query: str, expand_to_n: int = 3) -> dict[str, Any]:
        self.process_calls.append(query)
        expanded = self.expanded or [query] * expand_to_n
        return {
            "keywords": self.keywords,
            "intent": "general",
            "is_gap_query": False,
            "expanded_queries": expanded,
            "original_query": query,
        }

    async def process_async(self, query: str, expand_to_n: int = 3) -> dict[str, Any]:
        return self.process(query, expand_to_n)


class FakeReranker(Reranker):
    def rerank(
        self, query: str, documents: list[dict[str, Any]], top_k: int = 5
    ) -> list[dict[str, Any]]:
        # Return documents as-is but with scores
        for i, doc in enumerate(documents):
            doc["rerank_score"] = 0.9 - (i * 0.1)
        return documents[:top_k]


class FakeGraphRetriever(GraphRetriever):
    def __init__(self, refs: list = None, gaps: list = None):
        self.refs = refs or []
        self.gaps = gaps or []

    async def retrieve_and_reason(
        self, hits: list[dict[str, Any]], project_id: str, is_gap_query: bool = False
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return self.refs, self.gaps


class FakeRetriever(Retriever):
    """Fake retriever that returns canned documents."""
    
    def __init__(self, documents: list[dict[str, Any]] = None):
        self.documents = documents or []
        self.last_query = None

    async def retrieve(
        self,
        query: str,
        project_id: str,
        k: int = 5,
        expand_queries: int = 3,
        include_graph: bool = True,
        rerank: bool = True,
    ) -> dict[str, Any]:
        self.last_query = query
        return {
            "documents": self.documents,
            "keywords": ["fake"],
            "intent": "fake",
            "is_gap_query": False,
            "num_queries": 1,
            "graph_refs": 0,
            "graph_gaps": 0,
        }

    async def search(
        self, query: str, project_id: str, k: int = 5, score_threshold: float | None = None
    ) -> list[dict[str, Any]]:
        self.last_query = query
        return self.documents[:k]
