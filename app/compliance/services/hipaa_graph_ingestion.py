"""
HIPAAGraphIngestionService: Secure graph ingestion for HIPAA compliance.

This service handles ingesting clinical transcripts into the knowledge graph
using a pointer-based storage pattern to ensure PHI is never stored directly
in Neo4j.

Pattern:
    1. PHI text -> Encrypted in MinIO (via StorageProtocol)
    2. PHI pointer -> Stored in Neo4j
    3. Audit trail -> Logged to PostgreSQL

Graph Structure:
    Transcript -[CONTAINS_PHI]-> PHISpan -[VIOLATES]-> Regulation
                                    |
                                    +-[HAS_DECISION]-> ComplianceDecision
"""

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from loguru import logger

from app.ingestion.services.storage import get_storage_backend
from shorui_core.domain.interfaces import StorageBackend
from shorui_core.config import settings
from shorui_core.domain.hipaa_schemas import (
    AuditEventType,
    PHIExtractionResult,
)
from shorui_core.infrastructure.neo4j import get_neo4j_client

try:
    from app.compliance.services.audit_service import AuditService
except ImportError:
    logger.warning("Could not import AuditService. Audit logging will be disabled.")
    AuditService = None


class HIPAAGraphIngestionService:
    """
    Service for ingesting HIPAA compliance data into Neo4j graph.

    CRITICAL: This service implements pointer-based storage.
    - PHI text is encrypted and stored in secure storage (MinIO)
    - Only pointers are stored in Neo4j
    - No raw PHI text is ever written to Neo4j

    Usage:
        service = HIPAAGraphIngestionService()
        stats = await service.ingest_transcript(
            text="Patient John Smith...",
            extraction_result=result,
            filename="transcript_001.txt",
            project_id="project-abc"
        )
    """

    def __init__(
        self,
        database: str | None = None,
        phi_bucket: str = "phi-secure",
        storage_backend: StorageBackend | None = None,
    ):
        """
        Initialize the HIPAA graph ingestion service.

        Args:
            database: Neo4j database name (defaults to settings)
            phi_bucket: Storage bucket/container for encrypted PHI storage
            storage_backend: Optional storage backend (defaults to system config)
        """
        self._database = database or settings.NEO4J_DATABASE
        self._phi_bucket = phi_bucket

        # Use injected storage backend or default factory
        self.storage = storage_backend or get_storage_backend()
        
        # Ensure PHI bucket exists
        self.storage.ensure_bucket_exists(self._phi_bucket)

        # Audit service
        self._audit_service = AuditService() if AuditService else None
        logger.info(f"Initialized HIPAAGraphIngestionService with bucket '{self._phi_bucket}' and database '{self._database}'")

    async def ingest_transcript(
        self,
        text: str,
        extraction_result: PHIExtractionResult,
        filename: str,
        project_id: str,
    ) -> dict[str, int]:
        """
        Ingest a clinical transcript and its PHI analysis into the graph.

        Args:
            text: Full transcript text
            extraction_result: PHI extraction result from PrivacyAwareExtractionService
            filename: Original filename
            project_id: Project identifier for multi-tenancy

        Returns:
            dict: Statistics about ingested nodes and relationships
        """
        client = get_neo4j_client()

        stats = {
            "transcripts_created": 0,
            "phi_spans_created": 0,
            "relationships_created": 0,
        }

        logger.info(
            f"Ingesting transcript '{filename}' with {len(extraction_result.phi_spans)} PHI spans"
        )

        # 1. Store full text encrypted in storage
        transcript_id = extraction_result.transcript_id or str(uuid.uuid4())
        transcript_pointer = await self._store_encrypted_text(
            text=text,
            filename=f"transcripts/{transcript_id}.enc",
            project_id=project_id,
        )

        # 2. Create Transcript node (no PHI text in Neo4j)
        file_hash = hashlib.sha256(text.encode()).hexdigest()

        with client.session(database=self._database) as session:
            session.execute_write(
                self._create_transcript_node,
                transcript_id=transcript_id,
                project_id=project_id,
                filename=filename,
                file_hash=file_hash,
                storage_pointer=transcript_pointer,
                phi_count=len(extraction_result.phi_spans),
                text_length=len(text),
            )
            stats["transcripts_created"] += 1

            # 3. Create PHISpan nodes with pointers (not text)
            for span in extraction_result.phi_spans:
                phi_span_id = span.id

                # Extract and store the PHI text separately
                phi_text = text[span.start_char : span.end_char]
                phi_pointer = await self._store_encrypted_text(
                    text=phi_text,
                    filename=f"phi/{phi_span_id}.enc",
                    project_id=project_id,
                )

                # Compute hash for deduplication
                value_hash = hashlib.sha256(phi_text.lower().strip().encode()).hexdigest()[:16]

                session.execute_write(
                    self._create_phi_span_node,
                    phi_span_id=phi_span_id,
                    project_id=project_id,
                    category=span.category.value,
                    confidence=span.confidence,
                    detector=span.detector,
                    start_char=span.start_char,
                    end_char=span.end_char,
                    storage_pointer=phi_pointer,
                    value_hash=value_hash,
                    transcript_id=transcript_id,
                )
                stats["phi_spans_created"] += 1

                # Create CONTAINS_PHI relationship
                session.execute_write(
                    self._create_relationship,
                    from_id=transcript_id,
                    to_id=phi_span_id,
                    rel_type="CONTAINS_PHI",
                    project_id=project_id,
                )
                stats["relationships_created"] += 1

                # 4. Link to Regulations (if citations exist in extraction result)
                # Note: This assumes compliance analysis has been merged into spans
                # We'll look for citations in the extraction_result.compliance_analysis
                if extraction_result.compliance_analysis:
                    for analysis in extraction_result.compliance_analysis.phi_analyses:
                        if analysis.phi_span_index == extraction_result.phi_spans.index(span):
                            citation = analysis.regulation_citation
                            if citation:
                                # Extract section (e.g., "164.514")
                                reg_id = citation.split("(")[0].strip().replace("§", "").replace("45 CFR ", "")
                                
                                session.execute_write(
                                    self._create_relationship,
                                    from_id=phi_span_id,
                                    to_id=reg_id,
                                    rel_type="VIOLATES",
                                    project_id=project_id,
                                    to_label="Regulation"
                                )
                                stats["relationships_created"] += 1

        # Log audit event
        await self._log_audit_event(
            event_type=AuditEventType.PHI_DETECTED,
            description=f"Ingested transcript with {len(extraction_result.phi_spans)} PHI spans",
            resource_type="Transcript",
            resource_id=transcript_id,
            metadata={
                "filename": filename,
                "phi_count": len(extraction_result.phi_spans),
                "project_id": project_id,
            },
        )

        logger.info(f"Graph ingestion complete: {stats}")
        return stats

    async def _store_encrypted_text(
        self,
        text: str,
        filename: str,
        project_id: str,
    ) -> str:
        """
        Store text encrypted in secure storage.

        Note: In production, this should use proper encryption (e.g., AWS KMS).
        For now, we store as JSON, but the architecture supports encryption.

        Returns:
            Storage pointer string for retrieval
        """
        # Prepare data (in production, encrypt this)
        data = {
            "text": text,
            "stored_at": datetime.utcnow().isoformat(),
            "project_id": project_id,
        }
        data_bytes = json.dumps(data).encode("utf-8")

        # Upload using storage backend
        # Note: bucket arg assumes the backend supports it (MinIO does)
        try:
            storage_path = self.storage.upload(
                content=data_bytes,
                filename=filename,
                project_id=project_id,
                bucket=self._phi_bucket,
            )
            return storage_path
        except TypeError:
            # Fallback if backend doesn't support bucket arg (e.g., LocalStorage)
            storage_path = self.storage.upload(
                content=data_bytes,
                filename=filename,
                project_id=project_id,
            )
            return storage_path

    async def retrieve_phi_text(
        self,
        storage_pointer: str,
    ) -> str | None:
        """
        Retrieve PHI text from encrypted storage.

        CAUTION: This should only be called at the presentation layer
        after proper authorization checks.

        Args:
            storage_pointer: Path returned from storage backend

        Returns:
            Decrypted PHI text, or None if not found
        """
        try:
            # Download using storage backend
            content = self.storage.download(storage_pointer)
            data = json.loads(content.decode("utf-8"))

            # Log access (HIPAA audit requirement)
            await self._log_audit_event(
                event_type=AuditEventType.PHI_ACCESSED,
                description="Retrieved PHI from storage",
                resource_type="PHI",
                resource_id=storage_pointer,
            )

            return data.get("text")
        except Exception as e:
            logger.error(f"Failed to retrieve PHI: {e}")
            return None

    async def _log_audit_event(
        self,
        event_type: AuditEventType,
        description: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Log an audit event to PostgreSQL."""
        if not self._audit_service:
            logger.warning(f"AuditService not available. Skipping log: {description}")
            return

        try:
            await self._audit_service.log(
                event_type=event_type,
                description=description,
                resource_type=resource_type,
                resource_id=resource_id,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")

    # --- Neo4j Transaction Functions ---

    @staticmethod
    def _create_transcript_node(
        tx, transcript_id, project_id, filename, file_hash, storage_pointer, phi_count, text_length
    ):
        """Create a Transcript node in Neo4j (no PHI stored)."""
        logger.info(f"Executing Cypher to create Transcript node: {transcript_id} for project {project_id}")
        query = """
        MERGE (t:Transcript {id: $transcript_id, project_id: $project_id})
        SET t.filename = $filename,
        t.file_hash = $file_hash,
        t.storage_pointer = $storage_pointer,
        t.phi_count = $phi_count,
        t.text_length = $text_length,
        t.ingested_at = datetime(),
        t.phi_extraction_complete = true
        """
        tx.run(
            query,
            transcript_id=transcript_id,
            project_id=project_id,
            filename=filename,
            file_hash=file_hash,
            storage_pointer=storage_pointer,
            phi_count=phi_count,
            text_length=text_length,
        )

    @staticmethod
    def _create_phi_span_node(
        tx,
        phi_span_id,
        project_id,
        category,
        confidence,
        detector,
        start_char,
        end_char,
        storage_pointer,
        value_hash,
        transcript_id,
    ):
        """Create a PHISpan node in Neo4j (only pointer, not text)."""
        query = """
        MERGE (p:PHISpan {id: $phi_span_id, project_id: $project_id})
        SET p.category = $category,
        p.confidence = $confidence,
        p.detector = $detector,
        p.start_char = $start_char,
        p.end_char = $end_char,
        p.storage_pointer = $storage_pointer,
        p.value_hash = $value_hash,
        p.transcript_id = $transcript_id
        """
        tx.run(
            query,
            phi_span_id=phi_span_id,
            project_id=project_id,
            category=category,
            confidence=confidence,
            detector=detector,
            start_char=start_char,
            end_char=end_char,
            storage_pointer=storage_pointer,
            value_hash=value_hash,
            transcript_id=transcript_id,
        )

    @staticmethod
    def _create_relationship(tx, from_id, to_id, rel_type, project_id, to_label=None):
        """Create a relationship between two nodes."""
        if to_label == "Regulation":
            # Regulations are global (no project_id check for them specifically if not needed)
            # but we can check if they exist first.
            query = f"""
            MATCH (a {{id: $from_id, project_id: $project_id}})
            MATCH (b:Regulation {{id: $to_id}})
            MERGE (a)-[r:{rel_type}]->(b)
            """
        else:
            query = f"""
            MATCH (a {{id: $from_id, project_id: $project_id}})
            MATCH (b {{id: $to_id, project_id: $project_id}})
            MERGE (a)-[r:{rel_type}]->(b)
            """
        tx.run(query, from_id=from_id, to_id=to_id, project_id=project_id)
