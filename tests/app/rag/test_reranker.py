from __future__ import annotations
"""
Tests for CrossEncoderReranker.
"""

from unittest.mock import MagicMock

import pytest

from app.rag.services.reranker import CrossEncoderReranker


def test_reranker_sorts_correctly(mocker):
    # Mock the CrossEncoder model
    mock_model = MagicMock()
    # Predict returns scores for pairs [("q", "c1"), ("q", "c2")]
    # Let's say doc 2 is better than doc 1
    mock_model.predict.return_value = [0.1, 0.9]
    
    # Patch the class-level singleton or _get_model
    # Since _get_model checks instance, we can patch the class attr
    mocker.patch.object(CrossEncoderReranker, "_model_instance", mock_model)
    # Also need to ensure HAS_CROSS_ENCODER is True if we want to bypass import check,
    # or just assume the test runs in env with it. If not, we mock the module.
    mocker.patch("app.rag.services.reranker.HAS_CROSS_ENCODER", True)

    reranker = CrossEncoderReranker()
    
    docs = [
        {"id": "1", "content": "c1"},
        {"id": "2", "content": "c2"}
    ]
    
    results = reranker.rerank("q", docs, top_k=2)

    assert len(results) == 2
    assert results[0]["id"] == "2"  # Higher score first
    assert results[0]["rerank_score"] == 0.9
    assert results[1]["id"] == "1"
