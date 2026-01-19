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
        self, 
        hits: list[dict[str, Any]], 
        project_id: str, 
        is_gap_query: bool = False,
        query_analysis: dict[str, Any] | None = None
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Reason over search hits using Neo4j graph."""
        if not hits:
            return [], []

        logger.info(f"Graph reasoning for {len(hits)} hits in project '{project_id}'")

        try:
            # Build list of IDs to check
            # We check both the direct hit IDs and any section_ids in payload
            item_ids = []
            for hit in hits:
                # Direct ID
                if hit.get("id"):
                    item_ids.append(hit["id"])
                
                # Prefixed ID (for transcripts/blocks)
                block_id = hit.get("block_id") or hit.get("id")
                if block_id:
                    item_ids.append(f"{project_id}:{block_id}")
                
                # Section ID from regulation payload
                section_id = hit.get("section_id")
                if section_id:
                    item_ids.append(section_id)

            # Add keywords from query analysis
            if query_analysis and query_analysis.get("keywords"):
                item_ids.extend(query_analysis["keywords"])

            if not item_ids:
                logger.warning("No valid IDs found in hits or keywords")
                return [], []
            
            logger.info(f"Graph searching for IDs: {item_ids}")

            # Get expanded context from graph
            expanded_refs = await self._get_expanded_references(item_ids, project_id)

            # Get gaps (either for specific hits or all project gaps)
            gaps = await self._get_gaps(item_ids, project_id, is_gap_query)

            logger.info(f"Graph reasoning found {len(expanded_refs)} refs and {len(gaps)} gaps")

            return expanded_refs, gaps

        except Exception as e:
            logger.warning(f"Graph reasoning failed: {e}")
            return [], []

    async def _get_expanded_references(
        self, hit_ids: list[str], project_id: str
    ) -> list[dict[str, Any]]:
        """Get related HIPAA regulations for transcripts/spans."""
        # Query for regulations linked to transcripts or PHI spans
        query = """
        MATCH (t:Transcript)-[:CONTAINS_PHI]->(p:PHISpan)-[v:VIOLATES]->(r:Regulation)
        WHERE (t.id IN $hit_ids OR p.id IN $hit_ids OR r.id IN $hit_ids OR t.filename IN $hit_ids) AND t.project_id = $project_id
        RETURN r.id AS reg_id, r.title AS title, p.category AS category, t.filename AS source
        """

        try:
            client = get_neo4j_client()
            with client.session(database=self._database) as session:
                result = session.run(query, hit_ids=hit_ids, project_id=project_id)
                refs = []
                for record in result:
                    reg_id = record["reg_id"]
                    title = record["title"] or "Regulation"
                    source = record["source"]
                    category = record["category"]
                    
                    refs.append(
                        {
                            "type": "reference",
                            "source": source,
                            "reg_id": reg_id,
                            "title": title,
                            "category": category,
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
            # Gaps in this context could be missing redactions or pending reviews
            query = """
            MATCH (t:Transcript {project_id: $project_id})
            WHERE t.phi_extraction_complete = false OR t.phi_count > 0
            RETURN t.id AS id, 'PENDING_REDACTION' AS type, t.filename AS evidence, t.id AS source_id
            """
            params = {"project_id": project_id}
        else:
            # Find specific violations/gaps for given hits
            query = """
            MATCH (t:Transcript)-[:CONTAINS_PHI]->(p:PHISpan)
            WHERE (t.id IN $hit_ids OR p.id IN $hit_ids) AND t.project_id = $project_id
            AND NOT (p)-[:HAS_DECISION]->()
            RETURN p.id AS id, p.category AS type, 'Missing compliance decision' AS evidence, t.id AS source_id
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

        lines = ["## GRAPH-EXPANDED REFERENCES (Knowledge Graph Findings)"]
        # Group by source and regulation for clarity
        grouped = {}
        for ref in refs:
            # Use tuple as key
            key = (ref.get("source", "Unknown Source"), ref.get("reg_id", "Unknown Reg"))
            if key not in grouped:
                grouped[key] = {"title": ref.get("title", "Regulation"), "categories": set()}
            if ref.get("category"):
                grouped[key]["categories"].add(ref["category"])

        for (source, reg_id), data in grouped.items():
            cats = ", ".join(sorted(data["categories"])) if data["categories"] else "Unknown"
            lines.append(
                f"- Transcript '{source}' has been verified in the Knowledge Graph to violate Regulation [{reg_id}] ({data['title']}). Violation types found: {cats}."
            )
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
