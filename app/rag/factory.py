from __future__ import annotations
"""
Factory for creating RAG components.
"""

from app.rag.protocols import GenerativeModel, Retriever
from app.rag.services.graph_retriever import GraphRetrieverService
from app.rag.services.inference import OpenAIGenerator, RunPodGenerator
from app.rag.services.query_processor import LLMQueryAnalyzer
from app.rag.services.reranker import CrossEncoderReranker
from app.rag.services.retrieval import PipelineRetriever


def get_retriever() -> Retriever:
    """
    Create a fully configured Retriever instance.
    """
    # Instantiate dependencies
    query_analyzer = LLMQueryAnalyzer()
    reranker = CrossEncoderReranker()
    graph_retriever = GraphRetrieverService()

    # Wire them up
    return PipelineRetriever(
        query_analyzer=query_analyzer,
        reranker=reranker,
        graph_retriever=graph_retriever,
    )


def get_generator(backend: str = "openai") -> GenerativeModel:
    """
    Get a GenerativeModel for the specified backend.

    Args:
        backend: "openai" or "runpod"
    """
    if backend == "runpod":
        return RunPodGenerator()
    else:
        return OpenAIGenerator()
