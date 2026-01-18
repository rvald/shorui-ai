from __future__ import annotations
"""
Tests for GenerativeModel implementations.
"""

import pytest

from app.rag.services.inference import OpenAIGenerator, RunPodGenerator


@pytest.mark.asyncio
async def test_openai_generator(mocker):
    # Mock OpenAI client
    mock_client = mocker.Mock()
    mock_response = mocker.Mock()
    mock_response.choices = [mocker.Mock(message=mocker.Mock(content="Mocked answer"))]
    mock_client.chat.completions.create.return_value = mock_response

    # Patch get_openai_client at module level or where it's imported
    mocker.patch("app.rag.services.inference.get_openai_client", return_value=mock_client)

    generator = OpenAIGenerator()
    result = await generator.generate("What is X?")

    assert result["answer"] == "Mocked answer"
    assert result["backend"] == "openai"


@pytest.mark.asyncio
async def test_runpod_generator(mocker):
    # Mock requests.post
    mock_post = mocker.patch("requests.post")
    mock_post.return_value.json.return_value = {"answer": "RunPod Answer"}
    mock_post.return_value.raise_for_status = mocker.Mock()

    # Use dummy creds to avoid error during init if env vars missing
    generator = RunPodGenerator(api_url="http://fake", api_token="fake")
    result = await generator.generate("What is Y?")

    assert result["answer"] == "RunPod Answer"
    assert result["backend"] == "runpod"
