"""
Regulation Retriever Service for HIPAA compliance analysis.

This service retrieves relevant HIPAA regulation sections from Qdrant
to ground compliance decisions in actual regulation text.

Usage:
    retriever = RegulationRetriever()
    regulations = await retriever.retrieve_for_phi_category(PHICategory.SSN, top_k=3)
"""

from typing import Any

from loguru import logger

from app.ingestion.services.embedding import EmbeddingService
from shorui_core.domain.hipaa_schemas import PHICategory, PHISpan
from shorui_core.infrastructure.qdrant import QdrantDatabaseConnector

# Mapping of PHI categories to relevant search queries
PHI_CATEGORY_QUERIES = {
    PHICategory.NAME: "HIPAA rules for patient name disclosure and de-identification",
    PHICategory.DATE: "HIPAA date disclosure rules Safe Harbor dates except year",
    PHICategory.SSN: "Social Security number SSN HIPAA de-identification requirement",
    PHICategory.MRN: "Medical record number MRN HIPAA unique identifier",
    PHICategory.PHONE: "Telephone phone number HIPAA privacy disclosure",
    PHICategory.FAX: "Fax number HIPAA privacy protection",
    PHICategory.EMAIL: "Email address electronic mail HIPAA disclosure",
    PHICategory.GEOGRAPHIC: "Geographic address HIPAA de-identification street city zip code",
    PHICategory.HEALTH_PLAN_ID: "Health plan beneficiary number HIPAA identifier",
    PHICategory.ACCOUNT_NUMBER: "Account number HIPAA de-identification",
    PHICategory.LICENSE_NUMBER: "Certificate license number HIPAA protected",
    PHICategory.VEHICLE_ID: "Vehicle identifier VIN license plate HIPAA",
    PHICategory.DEVICE_ID: "Device identifier serial number HIPAA",
    PHICategory.URL: "URL web address HIPAA protected information",
    PHICategory.IP_ADDRESS: "IP address HIPAA de-identification",
    PHICategory.BIOMETRIC: "Biometric identifier fingerprint voiceprint HIPAA",
    PHICategory.PHOTO: "Full face photo image HIPAA de-identification",
    PHICategory.OTHER_UNIQUE_ID: "Unique identifying number HIPAA protected identifier",
}


class RegulationRetriever:
    """
    Retrieves relevant HIPAA regulation sections for compliance analysis.

    Uses semantic search over the hipaa_regulations Qdrant collection
    to find regulation text relevant to detected PHI types.

    Usage:
        retriever = RegulationRetriever()

        # Get regulations for a specific PHI category
        regulations = retriever.retrieve_for_phi_category(PHICategory.SSN)

        # Get regulations for all detected PHI spans
        regulations = retriever.retrieve_for_context(phi_spans)
    """

    COLLECTION_NAME = "hipaa_regulations"

    def __init__(self):
        """Initialize the regulation retriever."""
        self._embedding = EmbeddingService()
        self._client = None

    def _get_client(self):
        """Get Qdrant client (lazy initialization)."""
        if self._client is None:
            self._client = QdrantDatabaseConnector.get_instance()
        return self._client

    def retrieve_for_phi_category(
        self,
        category: PHICategory,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Retrieve HIPAA regulations relevant to a PHI category.

        Args:
            category: The PHI category (e.g., SSN, NAME)
            top_k: Number of results to return

        Returns:
            List of regulation chunks with metadata:
            [
                {
                    "section_id": "164.514(b)(2)",
                    "title": "Safe Harbor De-identification",
                    "text": "...",
                    "source": "45 CFR 164.514",
                    "relevance_score": 0.92
                }
            ]
        """
        # Get the search query for this category
        query = PHI_CATEGORY_QUERIES.get(
            category, f"HIPAA regulation for {category.value} protected health information"
        )

        return self._search(query, top_k)

    def retrieve_for_context(
        self,
        phi_spans: list[PHISpan],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Retrieve regulations relevant to all detected PHI spans.

        Combines results for multiple PHI categories, deduped and ranked.

        Args:
            phi_spans: List of detected PHI spans
            top_k: Total number of results to return

        Returns:
            List of regulation chunks with metadata
        """
        if not phi_spans:
            return []

        # Get unique categories
        categories = list(set(span.category for span in phi_spans))

        # Build combined query from all categories
        queries = [
            PHI_CATEGORY_QUERIES.get(cat, f"HIPAA {cat.value}")
            for cat in categories[:5]  # Limit to top 5 categories
        ]
        combined_query = " ".join(queries)

        logger.debug(f"Retrieving regulations for categories: {[c.value for c in categories]}")

        return self._search(combined_query, top_k)

    def retrieve_by_section(
        self,
        section_id: str,
        top_k: int = 2,
    ) -> list[dict[str, Any]]:
        """
        Retrieve regulation chunks by section ID.

        Args:
            section_id: HIPAA section (e.g., "164.514")
            top_k: Number of results

        Returns:
            List of matching regulation chunks
        """
        query = f"HIPAA section {section_id} regulation requirement"

        results = self._search(query, top_k * 2)

        # Filter to prefer exact section matches
        exact_matches = [r for r in results if r.get("section_id", "").startswith(section_id)]

        if exact_matches:
            return exact_matches[:top_k]
        return results[:top_k]

    def _search(
        self,
        query: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """
        Perform semantic search on the regulations collection.

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of results with metadata
        """
        client = self._get_client()

        # Check if collection exists
        if not client.collection_exists(self.COLLECTION_NAME):
            logger.warning(
                f"Collection {self.COLLECTION_NAME} does not exist. "
                "Please ingest HIPAA regulations first."
            )
            return []

        # Generate embedding for query
        query_embedding = self._embedding.embed([query])[0]

        # Search Qdrant
        try:
            response = client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_embedding,
                limit=top_k,
            )
            results = response.points

            # Format results
            formatted = []
            for result in results:
                payload = result.payload or {}
                formatted.append(
                    {
                        "section_id": payload.get("section_id", "Unknown"),
                        "title": payload.get("title", ""),
                        "text": payload.get("content", ""),
                        "source": payload.get("source", ""),
                        "category": payload.get("category", ""),
                        "relevance_score": result.score,
                    }
                )

            return formatted

        except Exception as e:
            logger.error(f"Regulation retrieval failed: {e}")
            return []

    def format_for_prompt(
        self,
        regulations: list[dict[str, Any]],
        max_chars: int = 3000,
    ) -> str:
        """
        Format retrieved regulations for inclusion in LLM prompt.

        Args:
            regulations: List of regulation chunks
            max_chars: Maximum characters for output

        Returns:
            Formatted string for LLM prompt
        """
        if not regulations:
            return "No specific HIPAA regulations retrieved."

        lines = ["RELEVANT HIPAA REGULATIONS:", ""]
        total_chars = 0

        for i, reg in enumerate(regulations, 1):
            section = f"[{reg.get('section_id', 'N/A')}] {reg.get('title', '')}"
            text = reg.get("text", "")[:500]  # Truncate long texts
            source = f"Source: {reg.get('source', 'Unknown')}"

            entry = f"{i}. {section}\n   {text}...\n   {source}\n"

            if total_chars + len(entry) > max_chars:
                break

            lines.append(entry)
            total_chars += len(entry)

        return "\n".join(lines)
