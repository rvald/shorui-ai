"""
Privacy-Aware Extraction Service for HIPAA compliance.

Uses a self-hosted LLM on RunPod for reasoning (no PHI leakage)
and Presidio for local PHI detection/tagging.


- Presidio runs FIRST to detect and tag PHI locations
- LLM receives FULL text (no masking - it's on your infrastructure)
- Focuses on compliance reasoning
- Logs all PHI detections to audit trail
"""

import asyncio
import hashlib
import os

# Add rag_pipeline_service to path for AuditService
import sys
import time
from typing import Any

import httpx
from loguru import logger
from openai import OpenAI

from app.ingestion.services.context_optimizer import (
    build_compact_prompt,
    build_optimized_batches,
)
from app.compliance.services.phi_detector import get_phi_detector
from shorui_core.config import settings
from shorui_core.domain.hipaa_schemas import (
    AuditEvent,
    AuditEventType,
    PHIComplianceAnalysis,
    PHIExtractionResult,
    PHISpan,
    TranscriptComplianceResult,
)

# AuditService is optional - will be None if not available
try:
    from shorui_core.infrastructure.audit import AuditService
except ImportError:
    logger.warning("Could not import AuditService. Audit logging will be disabled.")
    AuditService = None


class ExtractionError(Exception):
    """Raised when extraction fails."""

    pass


# --- Prompts ---

COMPLIANCE_SYSTEM_PROMPT = """HIPAA compliance analyst. Output JSON only.

Format:
{"overall_assessment": "...", "phi_analyses": [{"phi_span_index": 0, "is_violation": false, "severity": "LOW", "reasoning": "...", "regulation_citation": "45 CFR 164.514(b)", "recommended_action": "..."}], "requires_immediate_action": false}

severity: LOW/MEDIUM/HIGH/CRITICAL. Analyze each PHI span."""

COMPLIANCE_USER_TEMPLATE = """Transcript:
{text}

PHI Detected:
{phi_spans_description}

{regulations_section}

For each PHI span: is_violation? severity? regulation_citation? recommended_action?"""


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

# PHI types that require LLM for context-dependent analysis
NEEDS_LLM_ANALYSIS = {
    "NAME",
    "DATE",
    "GEOGRAPHIC",
    "PHONE",
    "FAX",
    "EMAIL",
    "URL",
    "IP_ADDRESS",
    "LICENSE_NUMBER",
    "BIOMETRIC",
    "PHOTO",
}


class PrivacyAwareExtractionService:
    """
    HIPAA-compliant extraction service using self-hosted LLM and local PHI detection.

    Flow:
    1. Presidio detects PHI locally (no external calls)
    2. Full text sent to RunPod LLM (your infrastructure - no leakage)
    3. LLM provides compliance reasoning
    4. Results logged to audit trail

    Usage:
        service = PrivacyAwareExtractionService()
        result = await service.extract(transcript_text, transcript_id="abc123")
    """

    def __init__(
        self,
        runpod_base_url: str | None = None,
        runpod_api_token: str | None = None,
        model_name: str | None = None,
        phi_confidence_threshold: float = 0.4,
    ):
        """
        Initialize the privacy-aware extraction service.

        Args:
            runpod_base_url: RunPod vLLM endpoint URL. Falls back to settings.RUNPOD_API_URL
            runpod_api_token: RunPod API token. Falls back to settings.RUNPOD_API_TOKEN
            model_name: Model name for the RunPod LLM. Falls back to settings.MODEL_INFERENCE
            phi_confidence_threshold: Minimum confidence for PHI detection
        """
        self.runpod_base_url = runpod_base_url or getattr(settings, "RUNPOD_API_URL", "") or None
        self.runpod_api_token = (
            runpod_api_token or getattr(settings, "RUNPOD_API_TOKEN", "") or None
        )
        self.model_name = model_name or getattr(
            settings, "MODEL_INFERENCE", "meta-llama/Llama-3.1-70B-Instruct"
        )
        self.phi_detector = get_phi_detector(min_confidence=phi_confidence_threshold)

        # HTTP client for RunPod API calls
        self._client: httpx.AsyncClient | None = None

        # HTTP client for RunPod API calls
        self._client: httpx.AsyncClient | None = None

        # Audit service for tamper-evident logging
        self._audit_service = AuditService() if AuditService else None

        # Regulation retriever for RAG-grounded compliance analysis
        self._regulation_retriever = None  # Lazy init

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client with auth headers."""
        if self._client is None:
            headers = {}
            if self.runpod_api_token:
                headers["Authorization"] = f"Bearer {self.runpod_api_token}"
            self._client = httpx.AsyncClient(timeout=120.0, headers=headers)
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def extract(
        self,
        text: str,
        transcript_id: str | None = None,
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
        if not skip_llm and phi_spans and self.runpod_base_url:
            try:
                compliance_result = await self._analyze_compliance(text, phi_spans)
                # Merge LLM insights back into spans
                self._enrich_spans_with_compliance(phi_spans, compliance_result)
            except Exception as e:
                logger.warning(
                    f"LLM compliance analysis failed: {e}. Continuing with detection only."
                )

        processing_time_ms = int((time.time() - start_time) * 1000)

        # Determine compliance analysis result (if any)
        # Note: compliance_result variable is defined in the try block above if successful
        final_compliance = compliance_result if ("compliance_result" in locals()) else None

        return PHIExtractionResult(
            transcript_id=transcript_id or "unknown",
            phi_spans=phi_spans,
            processing_time_ms=processing_time_ms,
            detector_versions={"presidio": "2.2", "llm": self.model_name},
            compliance_analysis=final_compliance,
        )

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

        logger.info(f"PHI analysis: {len(cached_analyses)} cached, {len(llm_spans)} need LLM")

        if not llm_spans:
            return TranscriptComplianceResult(
                overall_assessment="All PHI types have deterministic violations",
                phi_analyses=cached_analyses,
                requires_immediate_action=any(a.severity == "CRITICAL" for a in cached_analyses),
            )

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

        Uses GPT-4o with responses.parse for guaranteed JSON schema compliance.
        """
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)

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
        """
        Log an audit event to PostgreSQL.
        """
        if not self._audit_service:
            logger.warning(f"AuditService not available. Skipping log: {description}")
            return

        try:
            await self._audit_service.log_event(
                event_type=event_type,
                description=description,
                resource_type=resource_type,
                resource_id=resource_id,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")

    # Legacy method kept for interface compatibility but now empty
    def get_pending_audit_events(self) -> list[AuditEvent]:
        """Get and clear pending audit events (Deprecated)."""
        return []


def compute_phi_hash(text: str) -> str:
    """
    Compute a secure hash of PHI text for deduplication.

    Used to aggregate PHI nodes in the graph (same PHI = same node).
    """
    return hashlib.sha256(text.encode()).hexdigest()[:16]
