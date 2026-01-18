from __future__ import annotations
"""
Tests for LLMQueryAnalyzer.
"""

import json

import pytest

from app.rag.services.query_processor import LLMQueryAnalyzer


@pytest.mark.asyncio
async def test_analyzer_extraction(mocker):
    # Mock OpenAI client response for keywords
    mock_client = mocker.Mock()
    mock_response = mocker.Mock()
    mock_response.choices = [
        mocker.Mock(
            message=mocker.Mock(
                content=json.dumps({"keywords": ["k1", "k2"], "intent": "general"})
            )
        )
    ]
    mock_client.chat.completions.create.return_value = mock_response

    mocker.patch("app.rag.services.query_processor.get_openai_client", return_value=mock_client)

    analyzer = LLMQueryAnalyzer()
    result = analyzer.extract_keywords("query")

    assert result["keywords"] == ["k1", "k2"]
    assert result["intent"] == "general"


@pytest.mark.asyncio
async def test_analyzer_expansion(mocker):
    # Mock OpenAI response for expansion
    mock_client = mocker.Mock()
    mock_response = mocker.Mock()
    # Returns "Alternative 1 # Alternative 2"
    mock_response.choices = [
        mocker.Mock(
            message=mocker.Mock(content="Alt 1 # Alt 2")
        )
    ]
    mock_client.chat.completions.create.return_value = mock_response
    
    mocker.patch("app.rag.services.query_processor.get_openai_client", return_value=mock_client)

    analyzer = LLMQueryAnalyzer()
    expanded = analyzer.expand_query("orig", n=3)

    assert len(expanded) == 3
    assert expanded[0] == "orig"
    assert expanded[1] == "Alt 1"
