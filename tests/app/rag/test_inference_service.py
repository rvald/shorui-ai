"""
Unit tests for InferenceService.

The InferenceService should:
1. Generate answers using LLM with context
2. Support configurable LLM backends (OpenAI, RunPod)
3. Handle missing context gracefully
4. Return structured responses
"""

from unittest.mock import MagicMock, patch

import pytest


class TestInferenceServiceGeneration:
    """Tests for LLM generation."""

    @pytest.mark.asyncio
    async def test_generate_returns_answer(self, mock_openai):
        """Generate should return an answer."""
        from app.rag.services.inference import InferenceService

        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="The foundation uses concrete."))]
        )

        service = InferenceService()
        result = await service.generate(
            query="What material is used for foundation?",
            context="Foundation specs: Use reinforced concrete for all foundations.",
        )

        assert "answer" in result
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_generate_includes_query_in_prompt(self, mock_openai):
        """The user query should be included in the LLM prompt."""
        from app.rag.services.inference import InferenceService

        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Answer"))]
        )

        service = InferenceService()
        await service.generate(
            query="What is the roofing material?", context="Roofing: Metal sheets"
        )

        # Check the prompt contains the query
        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        prompt_text = str(messages)

        assert "roofing material" in prompt_text.lower()

    @pytest.mark.asyncio
    async def test_generate_includes_context_in_prompt(self, mock_openai):
        """The context should be included in the LLM prompt."""
        from app.rag.services.inference import InferenceService

        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Answer"))]
        )

        service = InferenceService()
        await service.generate(
            query="What color?", context="The building exterior is painted blue."
        )

        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        prompt_text = str(messages)

        assert "blue" in prompt_text.lower()


class TestInferenceServiceEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_generate_handles_empty_context(self, mock_openai):
        """Generate should handle empty context gracefully."""
        from app.rag.services.inference import InferenceService

        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="I don't have enough information."))]
        )

        service = InferenceService()
        result = await service.generate(query="What is the budget?", context="")

        assert "answer" in result

    @pytest.mark.asyncio
    async def test_generate_handles_none_context(self, mock_openai):
        """Generate should handle None context."""
        from app.rag.services.inference import InferenceService

        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="No context provided."))]
        )

        service = InferenceService()
        result = await service.generate(query="Random question", context=None)

        assert "answer" in result


# --- Fixtures ---


@pytest.fixture
def mock_openai():
    """Mock OpenAI client for testing."""
    with patch("app.rag.services.inference.OpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Test answer"))]
        )
        yield mock_client
