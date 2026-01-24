"""
Privacy-Aware Extraction Service for HIPAA compliance.

Uses Presidio for local PHI detection and OpenAI for compliance reasoning.

Flow:
- Presidio runs FIRST to detect and tag PHI locations (local, no external calls)
- OpenAI analyzes compliance and provides reasoning
- All PHI detections are logged to audit trail
"""

from __future__ import annotations
import asyncio
import hashlib
import time
from typing import Any

from loguru import logger

from app.compliance.protocols import AuditLogger, GraphIngestor, PHIDetector, RegulationRetriever
from app.compliance.services.context_optimizer import (
    build_compact_prompt,
    build_optimized_batches,
)
from shorui_core.domain.hipaa_schemas import (
    AuditEventType,
    PHIComplianceAnalysis,
    PHIExtractionResult,
    PHISpan,
    TranscriptComplianceResult,
)


class ExtractionError(Exception):
    """Raised when extraction fails."""

    pass


# --- Prompts ---

COMPLIANCE_SYSTEM_PROMPT = """HIPAA compliance analyst. Output JSON only.

Format:
{"overall_assessment": "...", "phi_analyses": [{"phi_span_index": 0, "is_violation": false, "severity": "LOW", "reasoning": "...", "regulation_citation": "45 CFR 164.514(b)", "recommended_action": "..."}], "requires_immediate_action": false}

severity: LOW/MEDIUM/HIGH/CRITICAL. Analyze each PHI span."""


# --- In-Memory PHI Cache: Deterministic violations skip LLM ---

# PHI types that are ALWAYS violations (no context needed)
DEFAULT_PHI_VIOLATIONS: dict[str, dict] = {
    "SSN": {
        "is_violation": True,
        "severity": "CRITICAL",
        "reasoning": "SSN is a direct identifier that must be removed for de-identification",
        "regulation_citation": "45 CFR 164.514(b)(2)(i)",
        "recommended_action": "Remove or fully mask SSN before any disclosure",
    },
    "MRN": {
        "is_violation": True,
        "severity": "HIGH",
        "reasoning": "Medical Record Number is a direct patient identifier",
        "regulation_citation": "45 CFR 164.514(b)(2)(i)(L)",
        "recommended_action": "Remove MRN or replace with study-specific code",
    },
    "HEALTH_PLAN_ID": {
        "is_violation": True,
        "severity": "HIGH",
        "reasoning": "Health plan beneficiary number identifies the patient",
        "regulation_citation": "45 CFR 164.514(b)(2)(i)(K)",
        "recommended_action": "Remove health plan ID before disclosure",
    },
    "ACCOUNT_NUMBER": {
        "is_violation": True,
        "severity": "HIGH",
        "reasoning": "Account numbers can identify patients",
        "regulation_citation": "45 CFR 164.514(b)(2)(i)(M)",
        "recommended_action": "Remove account numbers from disclosed documents",
    },
    "DEVICE_ID": {
        "is_violation": True,
        "severity": "MEDIUM",
        "reasoning": "Device/serial numbers can be linked to patients",
        "regulation_citation": "45 CFR 164.514(b)(2)(i)(O)",
        "recommended_action": "Remove device identifiers",
    },
    "VEHICLE_ID": {
        "is_violation": True,
        "severity": "MEDIUM",
        "reasoning": "Vehicle identifiers can be linked to patients",
        "regulation_citation": "45 CFR 164.514(b)(2)(i)(N)",
        "recommended_action": "Remove vehicle identifiers",
    },
}


class PrivacyAwareExtractionService:
    """
    HIPAA-compliant extraction service using Presidio for PHI detection
    and OpenAI for compliance reasoning.

    Flow:
    1. Presidio detects PHI locally (no external calls)
    2. OpenAI provides compliance reasoning
    3. Results logged to audit trail

    Usage:
        # Use factory to create instance
        service = get_compliance_service()
        result = await service.extract(transcript_text, transcript_id="abc123")
    """

    def __init__(
        self,
        phi_detector: PHIDetector,
        regulation_retriever: RegulationRetriever,
        audit_logger: AuditLogger | None = None,
        graph_ingestor: GraphIngestor | None = None,
    ):
        """
        Initialize the privacy-aware extraction service.

        Args:
            phi_detector: Service for detecting PHI
            regulation_retriever: Service for retrieving HIPAA regulations
            audit_logger: Service for audit logging (optional)
            graph_ingestor: Service for graph ingestion (optional)
        """
        self.phi_detector = phi_detector
        self._regulation_retriever = regulation_retriever
        self._audit_logger = audit_logger
        self.graph_ingestor = graph_ingestor

    async def extract(
        self,
        text: str,
        transcript_id: str | None = None,
        filename: str = "transcript.txt",
        project_id: str = "default",
        skip_llm: bool = False,
    ) -> PHIExtractionResult:
        """
        Extract PHI and analyze compliance.

        Args:
            text: Clinical transcript text to analyze
            transcript_id: Optional ID for linking results
            skip_llm: If True, only run Presidio detection (skip LLM analysis)

        Returns:
            PHIExtractionResult with detected spans and processing metadata
        """
        start_time = time.time()

        # Step 1: Local PHI detection with Presidio
        logger.info(f"Running PHI detection on transcript ({len(text)} chars)")
        phi_spans = self.phi_detector.detect(text, source_transcript_id=transcript_id)

        # Log detection event
        await self._log_audit_event(
            event_type=AuditEventType.PHI_DETECTED,
            description=f"Detected {len(phi_spans)} PHI spans in transcript",
            resource_type="Transcript",
            resource_id=transcript_id,
            metadata={"phi_count": len(phi_spans), "text_length": len(text)},
        )

        # Step 2: LLM compliance analysis (if enabled and spans found)
        compliance_result = None
        if not skip_llm and phi_spans:
            try:
                compliance_result = await self._analyze_compliance(text, phi_spans)
                # Merge LLM insights back into spans
                self._enrich_spans_with_compliance(phi_spans, compliance_result)
            except Exception as e:
                logger.warning(
                    f"LLM compliance analysis failed: {e}. Continuing with detection only."
                )

        processing_time_ms = int((time.time() - start_time) * 1000)

        result = PHIExtractionResult(
            transcript_id=transcript_id or "unknown",
            phi_spans=phi_spans,
            processing_time_ms=processing_time_ms,
            detector_versions={"presidio": "2.2", "llm": "gpt-4o-mini"},
            compliance_analysis=compliance_result,
        )

        # Step 3: Graph Ingestion (if enabled and result exists)
        logger.info(f"Checking for graph ingestor: {self.graph_ingestor is not None}, result exists: {result is not None}")
        if self.graph_ingestor and result:
            logger.info(f"Calling ingest_transcript (project: {project_id})")
            print(f"DEBUG: Calling ingest_transcript (project: {project_id})")
            try:
                await self.graph_ingestor.ingest_transcript(
                    text=text,
                    extraction_result=result,
                    filename=filename,
                    project_id=project_id,
                )
            except Exception as e:
                logger.warning(f"Graph ingestion failed: {e}")

        return result

    async def extract_batch(
        self,
        transcripts: list[dict[str, Any]],
        max_concurrency: int = 5,
    ) -> list[PHIExtractionResult]:
        """
        Extract PHI from multiple transcripts with controlled concurrency.

        Args:
            transcripts: List of dicts with 'text' and optional 'id' keys
            max_concurrency: Maximum concurrent extractions

        Returns:
            List of PHIExtractionResult in same order as input
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def process_one(transcript: dict[str, Any]) -> PHIExtractionResult:
            async with semaphore:
                return await self.extract(
                    text=transcript.get("text", ""),
                    transcript_id=transcript.get("id"),
                )

        return await asyncio.gather(*[process_one(t) for t in transcripts])

    async def _analyze_compliance(
        self, text: str, phi_spans: list[PHISpan]
    ) -> TranscriptComplianceResult:
        """
        Use LLM to analyze compliance of detected PHI.

        Uses cached templates for deterministic violations (SSN, MRN, etc.)
        and only calls LLM for context-dependent types (NAME, DATE, etc.).

        Uses token-aware batching with PHI deduplication for efficiency.

        Args:
            text: Full transcript text
            phi_spans: Detected PHI spans

        Returns:
            TranscriptComplianceResult with LLM analysis
        """
        # Separate spans: cached templates vs needs LLM
        cached_analyses = []
        llm_spans = []
        llm_span_indices = []

        for i, span in enumerate(phi_spans):
            category = span.category.value
            if category in DEFAULT_PHI_VIOLATIONS:
                template = DEFAULT_PHI_VIOLATIONS[category]
                cached_analyses.append(
                    PHIComplianceAnalysis(
                        phi_span_index=i,
                        is_violation=template["is_violation"],
                        severity=template["severity"],
                        reasoning=template["reasoning"],
                        regulation_citation=template["regulation_citation"],
                        recommended_action=template["recommended_action"],
                    )
                )
            else:
                llm_spans.append(span)
                llm_span_indices.append(i)

        logger.info(
            f"PHI analysis: {len(cached_analyses)} cached, {len(llm_spans)} need LLM"
        )

        if not llm_spans:
            return TranscriptComplianceResult(
                overall_assessment="All PHI types have deterministic violations",
                phi_analyses=cached_analyses,
                requires_immediate_action=any(
                    a.severity == "CRITICAL" for a in cached_analyses
                ),
            )

        # Retrieve relevant HIPAA regulations for RAG-grounded analysis
        regulations_context = ""
        try:
            regulations = self._regulation_retriever.retrieve_for_context(
                llm_spans, top_k=5
            )
            if regulations:
                regulations_context = self._regulation_retriever.format_for_prompt(
                    regulations, max_chars=2000
                )
                logger.info(
                    f"Retrieved {len(regulations)} HIPAA regulations for context"
                )
        except Exception as e:
            logger.warning(f"Failed to retrieve regulations (continuing without): {e}")

        # Build token-optimized batches with PHI deduplication
        batches = build_optimized_batches(
            phi_spans=llm_spans,
            text=text,
            max_input_tokens=1200,
            base_prompt_tokens=200,
        )

        all_analyses = list(cached_analyses)
        overall_assessments = []
        requires_action = any(a.severity == "CRITICAL" for a in cached_analyses)

        for batch_idx, batch in enumerate(batches):
            user_prompt, input_tokens = build_compact_prompt(
                contexts=batch,
                system_prompt=COMPLIANCE_SYSTEM_PROMPT,
            )

            # Append retrieved regulations to prompt for RAG-grounded analysis
            if regulations_context:
                user_prompt = f"{user_prompt}\n\n{regulations_context}"

            logger.debug(
                f"Batch {batch_idx + 1}/{len(batches)}: {len(batch)} PHI groups, {input_tokens} input tokens"
            )

            max_retries = 2

            for attempt in range(max_retries + 1):
                try:
                    batch_result = await self._call_llm(user_prompt)

                    if batch_result.phi_analyses:
                        for analysis in batch_result.phi_analyses:
                            local_idx = analysis.phi_span_index
                            if 0 <= local_idx < len(batch):
                                ctx = batch[local_idx]
                                analysis.phi_span_index = llm_span_indices[
                                    llm_spans.index(ctx.span)
                                ]
                            all_analyses.append(analysis)

                        overall_assessments.append(batch_result.overall_assessment)
                        if batch_result.requires_immediate_action:
                            requires_action = True

                        logger.debug(
                            f"Batch {batch_idx + 1}: Success - {len(batch_result.phi_analyses)} analyses"
                        )
                        break
                    else:
                        raise ValueError("Empty phi_analyses in response")

                except Exception as e:
                    if attempt < max_retries:
                        delay = 2**attempt
                        logger.warning(
                            f"Batch {batch_idx + 1} attempt {attempt + 1} failed: {e}. Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.warning(
                            f"Batch {batch_idx + 1} failed after {max_retries + 1} attempts: {e}"
                        )

        combined_assessment = (
            " | ".join(overall_assessments)
            if overall_assessments
            else "Unable to complete analysis"
        )

        return TranscriptComplianceResult(
            overall_assessment=combined_assessment,
            phi_analyses=all_analyses,
            requires_immediate_action=requires_action,
        )

    async def _call_llm(self, user_prompt: str) -> TranscriptComplianceResult:
        """
        Call OpenAI API with structured outputs.

        Uses GPT-4o-mini with responses.parse for guaranteed JSON schema compliance.
        """
        try:
            from shorui_core.infrastructure.openai_client import get_openai_client

            client = get_openai_client()

            logger.debug(f"OpenAI request: {len(user_prompt)} chars prompt")

            # Use responses.parse API with Pydantic model
            response = client.responses.parse(
                model="gpt-4o-mini",
                input=[
                    {"role": "system", "content": COMPLIANCE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                text_format=TranscriptComplianceResult,
                temperature=0.0,
            )

            result = response.output_parsed

            if result is None:
                logger.warning("OpenAI returned None parsed result")
                return TranscriptComplianceResult(
                    overall_assessment="Unable to parse response",
                    phi_analyses=[],
                    requires_immediate_action=False,
                )

            logger.debug(f"OpenAI response: {len(result.phi_analyses)} analyses")
            return result

        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise ExtractionError(f"OpenAI API call failed: {e}")

    def _enrich_spans_with_compliance(
        self, phi_spans: list[PHISpan], compliance_result: TranscriptComplianceResult
    ):
        """
        Enrich PHI spans with LLM compliance analysis.

        Note: This modifies the spans in place. For now we store
        compliance decisions separately, but this could be enhanced
        to link them via the storage_pointer.
        """
        # For now, just log the enrichment - actual linking happens in graph ingestion
        for analysis in compliance_result.phi_analyses:
            if 0 <= analysis.phi_span_index < len(phi_spans):
                span = phi_spans[analysis.phi_span_index]
                logger.debug(
                    f"Compliance analysis for PHI span {span.id}: "
                    f"violation={analysis.is_violation}, severity={analysis.severity}"
                )

    async def _log_audit_event(
        self,
        event_type: AuditEventType,
        description: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Log an audit event to PostgreSQL."""
        if not self._audit_logger:
            logger.warning(f"AuditLogger not available. Skipping log: {description}")
            return

        try:
            await self._audit_logger.log(
                event_type=event_type,
                description=description,
                resource_type=resource_type,
                resource_id=resource_id,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")


    @staticmethod
    def redact_text(text: str, phi_spans: list[PHISpan]) -> str:
        """
        Replace PHI spans in text with a category token (e.g., "[NAME]").

        Details:
            - Sorts spans descending by start position to safely modify string
            - Replaces content with a category tag
        """
        if not phi_spans:
            return text

        # Sort spans by start_char descending to avoid offset issues
        # We also need to handle overlapping spans if any (Presidio usually handles this, but good to be safe)
        # For simple redaction, we assume non-overlapping from detector.
        sorted_spans = sorted(phi_spans, key=lambda x: x.start_char, reverse=True)
        chars = list(text)

        for span in sorted_spans:
            replacement = f"[{span.category.value}]"
            # Ensure we don't go out of bounds or accidentally insert.
            start = max(0, min(span.start_char, len(chars)))
            end = max(start, min(span.end_char, len(chars)))
            if start >= len(chars) or end <= start:
                continue
            chars[start:end] = list(replacement)

        return "".join(chars)


def compute_phi_hash(text: str) -> str:
    """
    Compute a secure hash of PHI text for deduplication.

    Used to aggregate PHI nodes in the graph (same PHI = same node).
    """
    return hashlib.sha256(text.encode()).hexdigest()[:16]
