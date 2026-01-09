"""
HIPAA Regulation Service for indexing regulations into Qdrant.

This service handles:
1. Ingesting HIPAA regulation documents (PDF, TXT)
2. Chunking with section metadata
3. Embedding and indexing to Qdrant
4. Maintaining a dedicated collection for HIPAA regulations
"""

import re
from typing import Any

from loguru import logger

from app.ingestion.services.chunking import ChunkingService
from app.ingestion.services.embedding import EmbeddingService
from app.ingestion.services.indexing import IndexingService

# Common HIPAA section patterns for metadata extraction
SECTION_PATTERN = re.compile(r"§?\s*(\d{3}\.\d{3}(?:\([a-z]\)(?:\(\d+\))?)?)", re.IGNORECASE)

# Known HIPAA section titles for better metadata
HIPAA_SECTIONS = {
    "164.502": "Uses and Disclosures of PHI",
    "164.504": "Business Associates",
    "164.506": "Patient Consent",
    "164.508": "Authorization Requirements",
    "164.510": "Permitted Uses Without Authorization",
    "164.512": "Uses for Public Interest",
    "164.514": "De-identification Standard",
    "164.520": "Notice of Privacy Practices",
    "164.522": "Individual Rights",
    "164.524": "Access to PHI",
    "164.526": "Amendment of PHI",
    "164.528": "Accounting of Disclosures",
    "164.530": "Administrative Requirements",
    "164.308": "Administrative Safeguards",
    "164.310": "Physical Safeguards",
    "164.312": "Technical Safeguards",
    "164.314": "Organizational Requirements",
    "164.316": "Policies and Documentation",
}


class HIPAARegulationService:
    """
    Service for ingesting HIPAA regulation documents into Qdrant.

    Creates a dedicated collection for regulation text, enabling
    RAG-based retrieval during compliance analysis.

    Usage:
        service = HIPAARegulationService()
        stats = service.ingest_regulation(
            text="...",
            source="45 CFR 164.514",
            title="De-identification Standard"
        )
    """

    COLLECTION_NAME = "hipaa_regulations"

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ):
        """
        Initialize the HIPAA regulation service.

        Args:
            chunk_size: Maximum characters per chunk
            chunk_overlap: Overlap between chunks
        """
        self._chunking = ChunkingService(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self._embedding = EmbeddingService()
        self._indexing = IndexingService(default_collection=self.COLLECTION_NAME)

    def ingest_regulation(
        self,
        text: str,
        source: str,
        title: str | None = None,
        category: str = "privacy_rule",
    ) -> dict[str, Any]:
        """
        Ingest a HIPAA regulation document into Qdrant.

        Args:
            text: Full regulation text
            source: Source identifier (e.g., "45 CFR 164.514")
            title: Human-readable title
            category: Category (privacy_rule, security_rule, breach_notification)

        Returns:
            dict: Ingestion statistics
        """
        logger.info(f"Ingesting HIPAA regulation: {source}")

        # Extract section references from text
        sections_found = self._extract_sections(text)

        # Chunk the text
        chunks = self._chunking.chunk_with_metadata(text)

        if not chunks:
            logger.warning(f"No chunks created from regulation: {source}")
            return {"chunks_created": 0, "success": False}

        # Build texts and metadata for each chunk
        chunk_texts = []
        metadata_list = []

        for chunk in chunks:
            chunk_text = chunk["text"]

            # Find any section references in this chunk
            chunk_sections = self._extract_sections(chunk_text)
            primary_section = chunk_sections[0] if chunk_sections else None

            chunk_texts.append(chunk_text)
            metadata_list.append(
                {
                    "source": source,
                    "title": title or self._get_section_title(primary_section),
                    "category": category,
                    "section_id": primary_section,
                    "sections_referenced": chunk_sections[:5],  # Top 5 sections
                    "chunk_index": chunk["index"],
                    "doc_type": "hipaa_regulation",
                }
            )

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(chunk_texts)} chunks")
        embeddings = self._embedding.embed(chunk_texts)

        # Index to Qdrant
        self._indexing.index(
            chunks=chunk_texts,
            embeddings=embeddings,
            metadata=metadata_list,
            collection_name=self.COLLECTION_NAME,
        )

        logger.info(f"Indexed {len(chunks)} regulation chunks to {self.COLLECTION_NAME}")

        return {
            "chunks_created": len(chunks),
            "sections_found": sections_found,
            "source": source,
            "success": True,
        }

    def _extract_sections(self, text: str) -> list[str]:
        """Extract HIPAA section references from text."""
        matches = SECTION_PATTERN.findall(text)
        # Normalize and dedupe
        sections = []
        for match in matches:
            normalized = match.replace(" ", "").replace("§", "")
            if normalized not in sections:
                sections.append(normalized)
        return sections

    def _get_section_title(self, section_id: str | None) -> str | None:
        """Get the title for a known HIPAA section."""
        if not section_id:
            return None

        # Try to match base section (e.g., "164.514" from "164.514(b)(2)")
        base_section = section_id.split("(")[0] if "(" in section_id else section_id
        return HIPAA_SECTIONS.get(base_section)

    def get_collection_stats(self) -> dict[str, Any]:
        """Get statistics about the regulation collection."""
        try:
            client = self._indexing._get_client()

            if not client.collection_exists(self.COLLECTION_NAME):
                return {"exists": False, "points_count": 0}

            info = client.get_collection(self.COLLECTION_NAME)
            return {
                "exists": True,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"error": str(e)}
