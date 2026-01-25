from __future__ import annotations
"""
Factory for creating RAG components.
"""

from loguru import logger

from app.rag.protocols import GenerativeModel, Retriever
from app.rag.services.graph_retriever import GraphRetrieverService
from app.rag.services.grounded_generator import GroundedGenerator
from app.rag.services.inference import OpenAIGenerator, RunPodGenerator
from app.rag.services.query_processor import LLMQueryAnalyzer
from app.rag.services.reranker import CrossEncoderReranker
from app.rag.services.retrieval import PipelineRetriever
from shorui_core.infrastructure.qdrant import QdrantDatabaseConnector


def get_qdrant_client():
    """Get the Qdrant client singleton."""
    return QdrantDatabaseConnector.get_instance()


def collection_exists(project_id: str) -> bool:
    """
    Check if a Qdrant collection exists for the project.
    
    Args:
        project_id: The project identifier
        
    Returns:
        True if collection exists, False otherwise
    """
    try:
        client = get_qdrant_client()
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]
        
        # Check both direct name and project_ prefix
        exists = project_id in collection_names or f"project_{project_id}" in collection_names
        
        if not exists:
            logger.debug(f"Collection not found for project '{project_id}'")
        
        return exists
    except Exception as e:
        logger.warning(f"Failed to check collection existence: {e}")
        # On error, don't block - let it proceed and fail naturally
        return True


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


def get_grounded_generator(
    backend: str = "openai",
    min_sources: int = 1,
    require_citations: bool = True,
) -> GroundedGenerator:
    """
    Get a GroundedGenerator that enforces citation-based grounding.

    Args:
        backend: LLM backend ("openai" or "runpod")
        min_sources: Minimum sources required to generate answer
        require_citations: Whether to validate citation presence
    """
    base_generator = get_generator(backend=backend)
    return GroundedGenerator(
        base_generator=base_generator,
        min_sources=min_sources,
        require_citations=require_citations,
    )

