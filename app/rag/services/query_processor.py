from __future__ import annotations
"""
Query analysis service implementing the QueryAnalyzer protocol.
"""

import asyncio
import json
from typing import Any

from loguru import logger

from app.rag.protocols import QueryAnalyzer
from shorui_core.config import settings
from shorui_core.infrastructure.openai_client import get_openai_client


# --- Prompt Templates ---

SELF_QUERY_SYSTEM = """You are a query analyzer for healthcare compliance document search.
Given a user question, extract:
1. keywords: Key terms for vector search (HIPAA terms, PHI identifiers, regulations)
2. intent: "compliance_check" (rules/violations), "policy_lookup" (procedures), "phi_analysis" (PHI handling), or "general"

Respond with valid JSON only. Example format:
{"keywords": ["hipaa", "privacy_rule", "phi"], "intent": "compliance_check"}
"""

QUERY_EXPANSION_SYSTEM = """You are a search query generator.
Given a user question, generate {n} alternative ways to phrase the question
that would help find relevant documents.

Output each alternative on a new line, separated by '#'.
Example:
Alternative 1
#
Alternative 2
#
Alternative 3
"""


class LLMQueryAnalyzer(QueryAnalyzer):
    """
    Query analyzer using LLM (OpenAI) for keyword extraction and expansion.
    """

    def __init__(self, model: str = None):
        """
        Initialize the analyzer.

        Args:
            model: OpenAI model to use (defaults to config).
        """
        self._model = model or settings.OPENAI_MODEL_ID

    def _call_openai(
        self, system_prompt: str, user_message: str, temperature: float = 0, json_mode: bool = False
    ) -> str:
        """Call OpenAI API using the singleton client."""
        client = get_openai_client()

        kwargs = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def extract_keywords(self, query: str) -> dict[str, Any]:
        """Extract keywords and intent from a query."""
        logger.info(f"Extracting keywords from: '{query}'")

        try:
            response = self._call_openai(
                system_prompt=SELF_QUERY_SYSTEM,
                user_message=query,
                temperature=0,
                json_mode=True,
            )

            data = json.loads(response)

            keywords = data.get("keywords", [])
            intent = data.get("intent", "general")
            is_gap_query = intent == "gap_analysis"

            logger.info(f"Extracted keywords: {keywords}, intent: {intent}")

            return {"keywords": keywords, "intent": intent, "is_gap_query": is_gap_query}

        except Exception as e:
            logger.warning(f"Keyword extraction failed, using fallback: {e}")
            return {"keywords": query.split()[:5], "intent": "general", "is_gap_query": False}

    def expand_query(self, query: str, n: int = 3) -> list[str]:
        """Expand a query into multiple search queries."""
        logger.info(f"Expanding query to {n} variations")

        try:
            response = self._call_openai(
                system_prompt=QUERY_EXPANSION_SYSTEM.format(n=n - 1),
                user_message=query,
                temperature=0.3,
            )

            # Parse response (separated by #)
            alternatives = [alt.strip() for alt in response.split("#") if alt.strip()]

            # Include original first
            expanded = [query] + alternatives[: n - 1]

            logger.info(f"Generated {len(expanded)} query variations")
            return expanded

        except Exception as e:
            logger.warning(f"Query expansion failed, using original only: {e}")
            return [query]

    def process(self, query: str, expand_to_n: int = 3) -> dict[str, Any]:
        """Full query processing (synchronous)."""
        # Extract keywords and intent
        extraction = self.extract_keywords(query)

        # Expand queries
        expanded = self.expand_query(query, n=expand_to_n)

        return {**extraction, "expanded_queries": expanded, "original_query": query}

    async def process_async(self, query: str, expand_to_n: int = 3) -> dict[str, Any]:
        """Async query processing: runs keyword extraction and query expansion in PARALLEL."""
        
        # Run both LLM calls in parallel using thread pool
        extraction_task = asyncio.to_thread(self.extract_keywords, query)
        expansion_task = asyncio.to_thread(self.expand_query, query, expand_to_n)

        extraction, expanded = await asyncio.gather(extraction_task, expansion_task)

        return {**extraction, "expanded_queries": expanded, "original_query": query}
