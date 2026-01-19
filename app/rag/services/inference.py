from __future__ import annotations
"""
Inference services implementing the GenerativeModel protocol.
"""

from typing import Any

import requests
from loguru import logger

from app.rag.protocols import GenerativeModel
from shorui_core.config import settings
from shorui_core.infrastructure.openai_client import get_openai_client

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
- Use GRAPH-EXPANDED REFERENCES from the context to identify established links between specific transcripts/documents and HIPAA violations found by previous automated analysis.
- If the context doesn't contain the answer, clearly state that

Be accurate, thorough, and cite relevant regulations when possible."""

GENERAL_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on the provided context.
Answer the question using ONLY the information from the context below.
If the context doesn't contain the answer, say "I don't have enough information to answer that question."
Be concise and precise in your answers."""


class OpenAIGenerator(GenerativeModel):
    """GenerativeModel implementation using OpenAI API."""

    def __init__(
        self,
        model: str = None,
        api_key: str | None = None,
        base_url: str | None = None,
        use_hipaa_prompt: bool = True,
    ):
        self.model = model or settings.OPENAI_MODEL_ID
        self._api_key = api_key
        self._base_url = base_url
        self.system_prompt = (
            HIPAA_SYSTEM_PROMPT if use_hipaa_prompt else GENERAL_SYSTEM_PROMPT
        )
        self._client = None

    def _get_client(self):
        """Get the OpenAI client."""
        if self._client is None:
            if OpenAI is None:
                raise ImportError("openai package is required")

            # Use custom settings if provided, otherwise use singleton
            if self._api_key or self._base_url:
                kwargs = {}
                if self._api_key:
                    kwargs["api_key"] = self._api_key
                if self._base_url:
                    kwargs["base_url"] = self._base_url
                self._client = OpenAI(**kwargs)
            else:
                self._client = get_openai_client()
        return self._client

    async def generate(
        self, query: str, context: str | None = None, max_tokens: int = 2048
    ) -> dict[str, Any]:
        """Generate answer using OpenAI."""
        client = self._get_client()

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
        # Note: In a real async/production env, this should potentially run in a threadpool
        # if the client is synchronous. shorui_core.infrastructure.openai_client
        # typically provides a sync client, so we might need asyncio.to_thread here
        # but sticking to original pattern for now (which was sync call in async def).
        
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


class RunPodGenerator(GenerativeModel):
    """GenerativeModel implementation using RunPod."""

    def __init__(
        self,
        api_url: str | None = None,
        api_token: str | None = None,
        use_hipaa_prompt: bool = True,
    ):
        self.api_url = api_url or settings.RUNPOD_API_URL
        self.api_token = api_token or settings.RUNPOD_API_TOKEN
        self.model = settings.MODEL_INFERENCE
        self.system_prompt = (
            HIPAA_SYSTEM_PROMPT if use_hipaa_prompt else GENERAL_SYSTEM_PROMPT
        )

    async def generate(
        self, query: str, context: str | None = None, max_tokens: int = 2048
    ) -> dict[str, Any]:
        """Generate answer using RunPod."""
        if not self.api_url or not self.api_token:
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
            "model": self.model,
            "max_output_tokens": settings.MAX_OUTPUT_TOKENS_INFERENCE,
            "top_p": settings.TOP_P_INFERENCE,
            "temperature": settings.TEMPERATURE_INFERENCE,
        }

        logger.info(f"Generating answer (RunPod) for: '{query[:50]}...'")

        try:
            # Using synchronous requests here as per original implementation
            # Ideally should use httpx for async
            response = requests.post(
                self.api_url, 
                headers={"Authorization": f"Bearer {self.api_token}"}, 
                json=payload, 
                timeout=120
            )
            response.raise_for_status()
            result = response.json()

            # Extract answer from RunPod response
            answer = (
                result.get("answer") or result.get("response") or result.get("text") or str(result)
            )

            logger.info(f"Generated answer with {len(answer)} characters")

            return {
                "answer": answer, 
                "model": self.model, 
                "backend": "runpod", 
                "raw_response": result
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"RunPod request failed: {e}")
            raise
