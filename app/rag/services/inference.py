"""
InferenceService: Service layer for LLM inference.

This service handles generating answers using LLM with retrieved context.
Supports both OpenAI and RunPod backends.
"""

from typing import Any

import requests
from loguru import logger

from shorui_core.config import settings

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# HIPAA Compliance system prompt
HIPAA_SYSTEM_PROMPT = """You are an expert HIPAA compliance assistant. Your task is to help users understand HIPAA regulations, identify PHI, and ensure compliance with healthcare privacy and security rules.

When answering questions:
- Reference specific HIPAA rules and sections when applicable (e.g., Privacy Rule, Security Rule, 45 CFR 164)
- Identify the 18 HIPAA identifiers when discussing PHI
- Explain compliance requirements clearly and accurately
- Highlight potential violations and their consequences
- Recommend best practices for PHI handling
- If the context doesn't contain the answer, clearly state that

Be accurate, thorough, and cite relevant regulations when possible."""

GENERAL_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on the provided context.
Answer the question using ONLY the information from the context below.
If the context doesn't contain the answer, say "I don't have enough information to answer that question."
Be concise and precise in your answers."""


class InferenceService:
    """
    Service for LLM-based answer generation.

    Supports:
    - OpenAI API (default)
    - RunPod (custom endpoint)

    Usage:
        # OpenAI
        service = InferenceService()

        # RunPod
        service = InferenceService(backend="runpod")
    """

    def __init__(
        self,
        backend: str = "openai",
        model: str = None,
        api_key: str | None = None,
        base_url: str | None = None,
        use_hipaa_prompt: bool = True,
    ):
        """
        Initialize the inference service.

        Args:
            backend: "openai" or "runpod"
            model: Model name (defaults to config)
            api_key: API key (uses env vars if not provided)
            base_url: Custom API base URL
            use_hipaa_prompt: Use HIPAA compliance system prompt (default True)
        """
        self.backend = backend
        self.model = model or settings.OPENAI_MODEL_ID
        self._api_key = api_key
        self._base_url = base_url
        self._client = None

        self.system_prompt = (
            HIPAA_SYSTEM_PROMPT if use_hipaa_prompt else GENERAL_SYSTEM_PROMPT
        )

    def _get_openai_client(self):
        """Get the OpenAI client (uses singleton for connection reuse)."""
        if self._client is None:
            if OpenAI is None:
                raise ImportError("openai package is required for InferenceService")

            # Use custom settings if provided, otherwise use singleton
            if self._api_key or self._base_url:
                kwargs = {}
                if self._api_key:
                    kwargs["api_key"] = self._api_key
                if self._base_url:
                    kwargs["base_url"] = self._base_url
                self._client = OpenAI(**kwargs)
            else:
                from shorui_core.infrastructure.openai_client import get_openai_client
                self._client = get_openai_client()
        return self._client

    async def generate(
        self, query: str, context: str | None = None, max_tokens: int = 2048
    ) -> dict[str, Any]:
        """
        Generate an answer using the LLM.

        Args:
            query: The user's question.
            context: Retrieved context from documents.
            max_tokens: Maximum tokens in response.

        Returns:
            Dict with 'answer' key.
        """
        if self.backend == "runpod":
            return await self._generate_runpod(query, context, max_tokens)
        else:
            return await self._generate_openai(query, context, max_tokens)

    async def _generate_openai(
        self, query: str, context: str | None, max_tokens: int
    ) -> dict[str, Any]:
        """Generate using OpenAI API."""
        client = self._get_openai_client()

        # Build the user prompt
        if context:
            user_prompt = f"""Context:
{context}

Question: {query}

Answer:"""
        else:
            user_prompt = f"""Question: {query}

Note: No context was provided. Answer based on general knowledge or indicate that specific information is not available.

Answer:"""

        logger.info(f"Generating answer (OpenAI) for: '{query[:50]}...'")

        # Call the LLM
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )

        answer = response.choices[0].message.content

        logger.info(f"Generated answer with {len(answer)} characters")

        return {
            "answer": answer,
            "model": self.model,
            "backend": "openai",
            "tokens_used": getattr(response.usage, "total_tokens", None)
            if hasattr(response, "usage")
            else None,
        }

    async def _generate_runpod(
        self, query: str, context: str | None, max_tokens: int
    ) -> dict[str, Any]:
        """Generate using RunPod API."""
        api_url = self._base_url or settings.RUNPOD_API_URL
        api_token = self._api_key or settings.RUNPOD_API_TOKEN
        model = settings.MODEL_INFERENCE

        if not api_url or not api_token:
            raise ValueError("RUNPOD_API_URL and RUNPOD_API_TOKEN required for RunPod backend")

        # Build prompt
        if context:
            input_text = f"""Use the following context as your learned knowledge.
Context: {context}
When answering the user:
- If you don't know the answer, simply state that you don't know.
- If you're unsure, seek clarification.
- Avoid mentioning that the information was sourced from the context.
- Respond in accordance with the language of the user's question.
Given the context information, address the query.
Query: {query}"""
        else:
            input_text = query

        payload = {
            "input": input_text,
            "instructions": self.system_prompt,
            "model": model,
            "max_output_tokens": settings.MAX_OUTPUT_TOKENS_INFERENCE,
            "top_p": settings.TOP_P_INFERENCE,
            "temperature": settings.TEMPERATURE_INFERENCE,
        }

        logger.info(f"Generating answer (RunPod) for: '{query[:50]}...'")

        try:
            response = requests.post(
                api_url, headers={"Authorization": f"Bearer {api_token}"}, json=payload, timeout=120
            )
            response.raise_for_status()
            result = response.json()

            # Extract answer from RunPod response
            answer = (
                result.get("answer") or result.get("response") or result.get("text") or str(result)
            )

            logger.info(f"Generated answer with {len(answer)} characters")

            return {"answer": answer, "model": model, "backend": "runpod", "raw_response": result}

        except requests.exceptions.RequestException as e:
            logger.error(f"RunPod request failed: {e}")
            raise
