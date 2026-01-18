from __future__ import annotations
"""
Retrieval service implementing the Retriever protocol.
"""

import asyncio
from typing import Any

from loguru import logger

from app.ingestion.services.embedding import EmbeddingService
from app.rag.protocols import GraphRetriever, QueryAnalyzer, Reranker, Retriever
from shorui_core.infrastructure.qdrant import QdrantDatabaseConnector


class PipelineRetriever(Retriever):
    """
    Full RAG retrieval pipeline with dependency injection.
    """

    def __init__(
        self,
        query_analyzer: QueryAnalyzer,
        reranker: Reranker,
        graph_retriever: GraphRetriever,
    ):
        """
        Initialize the retrieval service.

        Args:
            query_analyzer: Service for keyword extraction & query expansion.
            reranker: Service for result reranking.
            graph_retriever: Service for graph integration.
        """
        self._query_analyzer = query_analyzer
        self._reranker = reranker
        self._graph_retriever = graph_retriever
        
        self._client = None
        self._embedding_service = None

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
        """Full retrieval pipeline."""
        logger.info(f"Full retrieval for: '{query}' in project '{project_id}'")

        # 1. Pre-retrieval: extract keywords and expand queries (PARALLEL)
        query_info = await self._query_analyzer.process_async(query, expand_to_n=expand_queries)
        keywords = query_info["keywords"]
        is_gap_query = query_info["is_gap_query"]
        expanded_queries = query_info["expanded_queries"]

        logger.info(
            f"Keywords: {keywords}, Intent: {query_info['intent']}, Queries: {len(expanded_queries)}"
        )

        # 2. Retrieval: search with all expanded queries IN PARALLEL
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
            # Note: format_references/gap_report are static methods on the original class,
            # but protocols don't support static methods well usually.
            # We'll assume the helper format methods are accessible on the instance or class.
            # For now, let's just use the instance method call if we can, or keep using
            # the original class import if needed for static helpers.
            # Actually, the protocol defined retrieve_and_reason. We can ask the graph retriever
            # for formatting helpers if we expose them, or just do it here if we want to decouple.
            # Let's import the specific implementation class just for the static helpers?
            # Or better, move formatting logic here or into a helper module.
            # For simplicity, we'll assume the graph_retriever instance can do it or we rely on the
            # return values.
            # Wait, `retrieve_and_reason` returns raw data. We need to format it into "content".
            
            refs, gaps = await self._graph_retriever.retrieve_and_reason(
                unique_results, project_id=project_id, is_gap_query=is_gap_query
            )

            # We need to format these refs/gaps into "content" strings for the context.
            # Let's re-implement the simple formatting here or import the class.
            # Importing the class `GraphRetrieverService` just for static methods is a bit weird
            # if we are trying to decouple, but acceptable.
            from app.rag.services.graph_retriever import GraphRetrieverService

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
        if project_id in collection_names:
            collection_name = project_id
        else:
            collection_name = f"project_{project_id}"

        if collection_name not in collection_names:
            # Silent fail / return empty if collection doesn't exist
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
        """Simple search wrapper."""
        result = await self.retrieve(
            query=query,
            project_id=project_id,
            k=k,
            expand_queries=1,  # Don't expand
            include_graph=False,  # Don't use graph
            rerank=False,  # Don't rerank
        )
        return result["documents"]
