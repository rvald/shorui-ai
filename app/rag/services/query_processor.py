"""
QueryProcessor: Pre-retrieval processing for RAG queries.

This service handles:
1. SelfQuery: Extract keywords and detect intent
2. QueryExpansion: Generate multiple search queries
"""

import json
from typing import Any

from loguru import logger

from shorui_core.config import settings

try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False


# --- Prompt Templates ---

SELF_QUERY_SYSTEM = """You are a query analyzer for healthcare compliance document search.
Given a user question, extract:
1. keywords: Key terms for vector search (HIPAA terms, PHI identifiers, regulations)
2. intent: "compliance_check" (rules/violations), "policy_lookup" (procedures), "phi_analysis" (PHI handling), or "general"

Respond with valid JSON only. Example format:
{{"keywords": ["hipaa", "privacy_rule", "phi"], "intent": "compliance_check"}}
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

    Usage:
        processor = QueryProcessor()
        result = processor.process("What materials for foundation?", expand_to_n=3)
        # result: {"keywords": [...], "intent": "general", "expanded_queries": [...]}
    """

    def __init__(self, mock: bool = False, model: str = None, api_key: str | None = None):
        """
        Initialize the query processor.

        Args:
            mock: If True, skip LLM calls and return defaults.
            model: OpenAI model to use (defaults to config).
            api_key: OpenAI API key (uses config if not provided).
        """
        self._mock = mock
        self._model = model or settings.OPENAI_MODEL_ID
        self._api_key = api_key or settings.OPENAI_API_KEY

    def _get_llm(self, temperature: float = 0, json_mode: bool = False):
        """Get a configured LLM instance."""
        if not HAS_LANGCHAIN:
            raise ImportError("langchain-openai is required for QueryProcessor")

        kwargs = {"model": self._model, "api_key": self._api_key, "temperature": temperature}
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

        return ChatOpenAI(**kwargs)

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
            prompt = ChatPromptTemplate.from_messages(
                [("system", SELF_QUERY_SYSTEM), ("user", "{question}")]
            )

            llm = self._get_llm(temperature=0, json_mode=True)
            chain = prompt | llm

            response = chain.invoke({"question": query})
            data = json.loads(response.content)

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
            prompt = ChatPromptTemplate.from_messages(
                [("system", QUERY_EXPANSION_SYSTEM.format(n=n - 1)), ("user", "{question}")]
            )

            llm = self._get_llm(temperature=0.3)
            chain = prompt | llm

            response = chain.invoke({"question": query})

            # Parse response (separated by #)
            alternatives = [alt.strip() for alt in response.content.split("#") if alt.strip()]

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
