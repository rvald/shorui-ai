from __future__ import annotations
"""
Graph retriever service implementing the GraphRetriever protocol.
"""

from typing import Any

from loguru import logger

from app.rag.protocols import GraphRetriever
from shorui_core.infrastructure.neo4j import get_neo4j_client


class GraphRetrieverService(GraphRetriever):
    """
    Graph-based context expansion and gap detection.
    """

    def __init__(self, database: str = "neo4j"):
        """
        Initialize the graph retriever.

        Args:
            database: Neo4j database name.
        """
        self._database = database

    async def retrieve_and_reason(
        self, hits: list[dict[str, Any]], project_id: str, is_gap_query: bool = False
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Reason over search hits using Neo4j graph."""
        if not hits:
            return [], []

        logger.info(f"Graph reasoning for {len(hits)} hits in project '{project_id}'")

        try:
            # Build list of prefixed IDs
            prefixed_hit_ids = []
            for hit in hits:
                block_id = hit.get("block_id") or hit.get("id")
                if block_id:
                    prefixed_id = f"{project_id}:{block_id}"
                    prefixed_hit_ids.append(prefixed_id)

            if not prefixed_hit_ids:
                logger.warning("No valid IDs found in hits")
                return [], []

            # Get expanded context from graph
            expanded_refs = await self._get_expanded_references(prefixed_hit_ids, project_id)

            # Get gaps (either for specific hits or all project gaps)
            gaps = await self._get_gaps(prefixed_hit_ids, project_id, is_gap_query)

            logger.info(f"Graph reasoning found {len(expanded_refs)} refs and {len(gaps)} gaps")

            return expanded_refs, gaps

        except Exception as e:
            logger.warning(f"Graph reasoning failed: {e}")
            return [], []

    async def _get_expanded_references(
        self, hit_ids: list[str], project_id: str
    ) -> list[dict[str, Any]]:
        """Get SEE_DETAIL relationships for hits."""
        query = """
        MATCH (tb:TextBlock)-[:SEE_DETAIL]->(d:Detail)
        WHERE tb.id IN $hit_ids AND tb.project_id = $project_id
        RETURN d.sheet_id AS sheet, d.detail AS detail, tb.id AS source_id
        """

        try:
            client = get_neo4j_client()
            with client.session(database=self._database) as session:
                result = session.run(query, hit_ids=hit_ids, project_id=project_id)
                refs = []
                for record in result:
                    refs.append(
                        {
                            "type": "reference",
                            "source_id": record["source_id"],
                            "target": f"Detail {record['detail']} on {record['sheet']}",
                        }
                    )
                return refs
        except Exception as e:
            logger.warning(f"Failed to get references: {e}")
            return []

    async def _get_gaps(
        self, hit_ids: list[str], project_id: str, is_gap_query: bool
    ) -> list[dict[str, Any]]:
        """Get gaps (missing references) from the graph."""
        if is_gap_query:
            # Get ALL gaps for the project
            query = """
            MATCH (g:Gap {project_id: $project_id})
            OPTIONAL MATCH (tb:TextBlock {project_id: $project_id})-[:INDICATES_GAP]->(g)
            RETURN g.gap_id AS id, g.gap_type AS type, g.evidence_text AS evidence, tb.id AS source_id
            """
            params = {"project_id": project_id}
        else:
            # Get gaps for specific hits only
            query = """
            MATCH (tb:TextBlock)-[:INDICATES_GAP]->(g:Gap)
            WHERE tb.id IN $hit_ids AND tb.project_id = $project_id
            RETURN g.gap_id AS id, g.gap_type AS type, g.evidence_text AS evidence, tb.id AS source_id
            """
            params = {"hit_ids": hit_ids, "project_id": project_id}

        try:
            client = get_neo4j_client()
            with client.session(database=self._database) as session:
                result = session.run(query, **params)
                gaps = []
                for record in result:
                    gaps.append(
                        {
                            "id": record["id"],
                            "type": record["type"],
                            "evidence": record["evidence"],
                            "source_id": record["source_id"],
                        }
                    )
                return gaps
        except Exception as e:
            logger.warning(f"Failed to get gaps: {e}")
            return []

    @staticmethod
    def format_references(refs: list[dict[str, Any]]) -> str:
        """Format references for context."""
        if not refs:
            return ""

        lines = ["## GRAPH-EXPANDED REFERENCES"]
        for ref in refs:
            lines.append(f"- {ref['target']} (from {ref['source_id']})")

        return "\n".join(lines)

    @staticmethod
    def format_gap_report(gaps: list[dict[str, Any]]) -> str:
        """Format gaps as a report for context."""
        if not gaps:
            return ""

        lines = ["## COORDINATION GAPS & MISSING INFORMATION"]
        for gap in gaps:
            lines.append(f"- [{gap['type']}] {gap.get('evidence', 'No evidence')[:200]}")
        lines.append("\n**Recommendation:** Consider issuing an RFI to resolve these gaps.")

        return "\n".join(lines)
