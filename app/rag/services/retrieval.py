"""
RetrievalService: Full RAG retrieval pipeline.

This service orchestrates the complete retrieval pipeline:
1. Pre-retrieval: Query expansion + keyword extraction
2. Retrieval: Multi-query vector search
3. Post-retrieval: Graph reasoning + reranking
"""

from typing import Any

from loguru import logger

from app.ingestion.services.embedding import EmbeddingService
from app.rag.services.graph_retriever import GraphRetrieverService
from app.rag.services.query_processor import QueryProcessor
from app.rag.services.reranker import RerankerService
from shorui_core.infrastructure.qdrant import QdrantDatabaseConnector


class RetrievalService:
    """
    Full RAG retrieval service with all pipeline stages.

    Pipeline:
    1. SelfQuery: extract keywords, detect intent
    2. QueryExpansion: generate N search queries
    3. Embed & Search: multi-query vector search
    4. Deduplicate: remove duplicate results
    5. GraphRetriever: expand context from Neo4j
    6. Reranker: re-score with CrossEncoder

    Usage:
        service = RetrievalService()
        result = await service.retrieve(
            query="What materials for foundation?",
            project_id="my-project",
            k=5
        )
    """

    def __init__(self, mock: bool = False):
        """
        Initialize the retrieval service.

        Args:
            mock: If True, skip LLM/model calls.
        """
        self._mock = mock
        self._client = None
        self._embedding_service = None
        self._query_processor = QueryProcessor(mock=mock)
        self._reranker = RerankerService(mock=mock)
        self._graph_retriever = GraphRetrieverService(mock=mock)

    def _get_client(self):
        """Get the Qdrant client (lazy initialization)."""
        if self._client is None:
            self._client = QdrantDatabaseConnector.get_instance()
        return self._client

    def _get_embedding_service(self):
        """Get the embedding service (lazy initialization)."""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService()
        return self._embedding_service

    async def retrieve(
        self,
        query: str,
        project_id: str,
        k: int = 5,
        expand_queries: int = 3,
        include_graph: bool = True,
        rerank: bool = True,
    ) -> dict[str, Any]:
        """
        Full retrieval pipeline.

        Args:
            query: User's search query.
            project_id: Project for multi-tenancy.
            k: Number of final results.
            expand_queries: Number of query variations.
            include_graph: Whether to use Neo4j reasoning.
            rerank: Whether to use CrossEncoder reranking.

        Returns:
            Dict with: documents, keywords, intent, is_gap_query
        """
        logger.info(f"Full retrieval for: '{query}' in project '{project_id}'")

        # 1. Pre-retrieval: extract keywords and expand queries (PARALLEL)
        query_info = await self._query_processor.process_async(query, expand_to_n=expand_queries)
        keywords = query_info["keywords"]
        is_gap_query = query_info["is_gap_query"]
        expanded_queries = query_info["expanded_queries"]

        logger.info(
            f"Keywords: {keywords}, Intent: {query_info['intent']}, Queries: {len(expanded_queries)}"
        )

        # 2. Retrieval: search with all expanded queries IN PARALLEL
        import asyncio
        
        search_tasks = [
            self._search_single(search_query, project_id, k)
            for search_query in expanded_queries
        ]
        search_results = await asyncio.gather(*search_tasks)
        
        # Flatten results from all queries
        all_results = []
        for results in search_results:
            all_results.extend(results)

        # 3. Deduplicate by ID
        seen_ids = set()
        unique_results = []
        for result in all_results:
            result_id = result.get("id")
            if result_id and result_id not in seen_ids:
                seen_ids.add(result_id)
                unique_results.append(result)

        logger.info(f"Retrieved {len(all_results)} results, {len(unique_results)} unique")

        # 4. Graph reasoning (if enabled)
        refs = []
        gaps = []
        if include_graph and unique_results:
            refs, gaps = await self._graph_retriever.retrieve_and_reason(
                unique_results, project_id=project_id, is_gap_query=is_gap_query
            )

            # Add graph context as special results
            if refs:
                unique_results.append(
                    {
                        "id": "graph_references",
                        "content": GraphRetrieverService.format_references(refs),
                        "score": 1.0,
                        "is_graph": True,
                    }
                )

            if gaps:
                unique_results.append(
                    {
                        "id": "gap_report",
                        "content": GraphRetrieverService.format_gap_report(gaps),
                        "score": 1.0,
                        "is_graph": True,
                    }
                )

        # 5. Rerank (if enabled)
        if rerank and len(unique_results) > k:
            # Keep graph results separate during reranking
            graph_results = [r for r in unique_results if r.get("is_graph")]
            vector_results = [r for r in unique_results if not r.get("is_graph")]

            reranked = self._reranker.rerank(query, vector_results, top_k=k)
            final_results = reranked + graph_results
        else:
            final_results = unique_results[: k + 2]  # Extra room for graph results

        logger.info(f"Final results: {len(final_results)}")

        return {
            "documents": final_results,
            "keywords": keywords,
            "intent": query_info["intent"],
            "is_gap_query": is_gap_query,
            "num_queries": len(expanded_queries),
            "graph_refs": len(refs),
            "graph_gaps": len(gaps),
        }

    async def _search_single(self, query: str, project_id: str, k: int) -> list[dict[str, Any]]:
        """Search with a single query."""

        client = self._get_client()
        embedding_service = self._get_embedding_service()

        # Embed the query
        query_embedding = embedding_service.embed([query])[0]

        # Get all collection names
        try:
            collections = client.get_collections()
            collection_names = [c.name for c in collections.collections]
        except Exception as e:
            logger.warning(f"Failed to check collections: {e}")
            return []

        # Build collection name - support both direct name and project_ prefix
        # First try direct match, then try with project_ prefix
        if project_id in collection_names:
            collection_name = project_id
        else:
            collection_name = f"project_{project_id}"

        if collection_name not in collection_names:
            logger.warning(
                f"Collection '{collection_name}' does not exist. Available: {collection_names}"
            )
            return []

        # Search using query_points
        try:
            search_results = client.query_points(
                collection_name=collection_name, query=query_embedding, limit=k, with_payload=True
            )
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            return []

        # Format results
        results = []
        for hit in search_results.points:
            results.append(
                {
                    "id": str(hit.id),
                    "score": hit.score,
                    "content": hit.payload.get("content", ""),
                    "filename": hit.payload.get("filename"),
                    "page_num": hit.payload.get("page_num"),
                    "project_id": hit.payload.get("project_id"),
                    "block_id": hit.payload.get("block_id"),
                    "bbox": hit.payload.get("bbox"),
                    "sheet_id": hit.payload.get("sheet_id"),
                }
            )

        return results

    async def search(
        self, query: str, project_id: str, k: int = 5, score_threshold: float | None = None
    ) -> list[dict[str, Any]]:
        """
        Simple search (backwards compatible API).

        For the full pipeline, use retrieve() instead.
        """
        result = await self.retrieve(
            query=query,
            project_id=project_id,
            k=k,
            expand_queries=1,  # Don't expand
            include_graph=False,  # Don't use graph
            rerank=False,  # Don't rerank
        )
        return result["documents"]

    async def search_with_context(self, query: str, project_id: str, k: int = 5) -> str:
        """
        Retrieve and format results as a context string.
        """
        result = await self.retrieve(query=query, project_id=project_id, k=k)

        documents = result["documents"]
        if not documents:
            return ""

        # Format as context
        context_parts = []
        for i, doc in enumerate(documents, 1):
            if doc.get("is_graph"):
                # Graph results are already formatted
                context_parts.append(doc["content"])
            else:
                source = doc.get("filename", "unknown")
                page = doc.get("page_num", "?")
                content = doc.get("content", "")
                context_parts.append(f"[Source {i}: {source}, page {page}]\n{content}")

        return "\n\n".join(context_parts)
