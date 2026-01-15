"""
QueryProcessor: Pre-retrieval processing for RAG queries.

This service handles:
1. SelfQuery: Extract keywords and detect intent
2. QueryExpansion: Generate multiple search queries

Uses OpenAI client singleton for connection reuse.
"""

import json
from typing import Any

from loguru import logger

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


class QueryProcessor:
    """
    Pre-retrieval query processing service.

    Combines SelfQuery (keyword/intent extraction) and
    QueryExpansion (multi-query generation) for better retrieval.

    Uses OpenAI client singleton for efficient connection reuse.

    Usage:
        processor = QueryProcessor()
        result = processor.process("What materials for foundation?", expand_to_n=3)
        # result: {"keywords": [...], "intent": "general", "expanded_queries": [...]}
    """

    def __init__(self, mock: bool = False, model: str = None):
        """
        Initialize the query processor.

        Args:
            mock: If True, skip LLM calls and return defaults.
            model: OpenAI model to use (defaults to config).
        """
        self._mock = mock
        self._model = model or settings.OPENAI_MODEL_ID

    def _call_openai(
        self, system_prompt: str, user_message: str, temperature: float = 0, json_mode: bool = False
    ) -> str:
        """
        Call OpenAI API using the singleton client.

        Args:
            system_prompt: System prompt for the LLM.
            user_message: User message to process.
            temperature: LLM temperature (0 = deterministic).
            json_mode: If True, request JSON response format.

        Returns:
            The LLM response content as a string.
        """
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
        """
        Extract keywords and intent from a query (SelfQuery).

        Args:
            query: The user's search query.

        Returns:
            Dict with keys: keywords (list), intent (str), is_gap_query (bool)
        """
        if self._mock:
            return {
                "keywords": query.split()[:5],  # Simple word split
                "intent": "general",
                "is_gap_query": False,
            }

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
        """
        Expand a query into multiple search queries (QueryExpansion).

        Args:
            query: The original query.
            n: Number of total queries to generate (including original).

        Returns:
            List of queries (original + alternatives).
        """
        if self._mock:
            return [query] * n

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
        """
        Full query processing: extract keywords + expand queries.

        Args:
            query: The user's search query.
            expand_to_n: Number of query variations to generate.

        Returns:
            Dict with: keywords, intent, is_gap_query, expanded_queries
        """
        # Extract keywords and intent
        extraction = self.extract_keywords(query)

        # Expand queries
        expanded = self.expand_query(query, n=expand_to_n)

        return {**extraction, "expanded_queries": expanded, "original_query": query}

    async def process_async(self, query: str, expand_to_n: int = 3) -> dict[str, Any]:
        """
        Async query processing: runs keyword extraction and query expansion in PARALLEL.

        Same as process() but uses asyncio to run both LLM calls concurrently,
        reducing latency by ~50% compared to sequential execution.

        Args:
            query: The user's search query.
            expand_to_n: Number of query variations to generate.

        Returns:
            Dict with: keywords, intent, is_gap_query, expanded_queries
        """
        import asyncio

        # Run both LLM calls in parallel using thread pool
        extraction_task = asyncio.to_thread(self.extract_keywords, query)
        expansion_task = asyncio.to_thread(self.expand_query, query, expand_to_n)

        extraction, expanded = await asyncio.gather(extraction_task, expansion_task)

        return {**extraction, "expanded_queries": expanded, "original_query": query}
