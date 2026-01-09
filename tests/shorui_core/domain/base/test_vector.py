"""
Unit tests for VectorBaseDocument base model.

These tests verify the core functionality of the base document class
that will be shared across all services in shorui_core.
"""

from unittest.mock import MagicMock
from uuid import UUID

import pytest


class TestVectorBaseDocumentIdentity:
    """Tests for ID generation and equality."""

    def test_creates_uuid_by_default(self, vector_document_class):
        """A new document should have a valid UUID generated automatically."""
        doc = vector_document_class(content="test", embedding=[0.1, 0.2])

        assert doc.id is not None
        assert isinstance(doc.id, UUID)

    def test_accepts_custom_uuid(self, vector_document_class):
        """A document should accept a custom UUID."""
        custom_id = UUID("12345678-1234-5678-1234-567812345678")
        doc = vector_document_class(id=custom_id, content="test", embedding=[0.1, 0.2])

        assert doc.id == custom_id

    def test_two_documents_with_same_id_are_equal(self, vector_document_class):
        """Documents with the same ID should be considered equal."""
        shared_id = UUID("12345678-1234-5678-1234-567812345678")
        doc1 = vector_document_class(id=shared_id, content="test1", embedding=[0.1])
        doc2 = vector_document_class(id=shared_id, content="test2", embedding=[0.2])

        assert doc1 == doc2

    def test_two_documents_with_different_ids_are_not_equal(self, vector_document_class):
        """Documents with different IDs should not be equal."""
        doc1 = vector_document_class(content="test", embedding=[0.1])
        doc2 = vector_document_class(content="test", embedding=[0.1])

        assert doc1 != doc2

    def test_document_is_hashable(self, vector_document_class):
        """Documents should be hashable (for use in sets/dicts)."""
        doc = vector_document_class(content="test", embedding=[0.1])

        # Should not raise
        doc_set = {doc}
        assert doc in doc_set


class TestVectorBaseDocumentSerialization:
    """Tests for serialization to Qdrant PointStruct."""

    def test_to_point_returns_point_struct(self, vector_document_class):
        """to_point() should return a PointStruct with id, vector, and payload."""
        doc = vector_document_class(content="hello world", embedding=[0.1, 0.2, 0.3])

        point = doc.to_point()

        assert point.id == str(doc.id)
        assert point.vector == [0.1, 0.2, 0.3]
        assert "content" in point.payload

    def test_to_point_excludes_embedding_from_payload(self, vector_document_class):
        """The embedding should be in vector, not duplicated in payload."""
        doc = vector_document_class(content="test", embedding=[0.1, 0.2])

        point = doc.to_point()

        assert "embedding" not in point.payload

    def test_to_point_converts_uuid_to_string(self, vector_document_class):
        """UUIDs in the payload should be converted to strings."""
        doc = vector_document_class(content="test", embedding=[0.1])

        point = doc.to_point()

        # The id in the point should be a string, not UUID
        assert isinstance(point.id, str)


class TestVectorBaseDocumentDeserialization:
    """Tests for deserializing from Qdrant ScoredPoint."""

    def test_from_record_creates_document(self, vector_document_class, mock_scored_point):
        """from_record() should create a document from a ScoredPoint."""
        doc = vector_document_class.from_record(mock_scored_point)

        assert doc.content == "test content"
        assert doc.id == UUID(mock_scored_point.id)

    def test_from_record_handles_missing_content_field(self, vector_document_class):
        """from_record() should handle payloads with alternate content field names."""
        point = MagicMock()
        point.id = "12345678-1234-5678-1234-567812345678"
        point.payload = {"cleaned_text": "cleaned content"}
        point.vector = [0.1, 0.2]

        doc = vector_document_class.from_record(point)

        assert doc.content == "cleaned content"

    def test_from_record_falls_back_to_text_field(self, vector_document_class):
        """from_record() should fall back to 'text' if 'content' is missing."""
        point = MagicMock()
        point.id = "12345678-1234-5678-1234-567812345678"
        point.payload = {"text": "text content"}
        point.vector = [0.1, 0.2]

        doc = vector_document_class.from_record(point)

        assert doc.content == "text content"


# --- Fixtures ---


@pytest.fixture
def vector_document_class():
    """
    Provides a concrete implementation of VectorBaseDocument for testing.

    Note: This imports from shorui_core which we will create.
    For now, this fixture will fail until implementation exists.
    """
    from shorui_core.domain.base.vector import VectorBaseDocument

    class TestDocument(VectorBaseDocument):
        content: str
        embedding: list[float] | None = None

        class Config:
            name = "test_collection"
            use_vector_index = True

    return TestDocument


@pytest.fixture
def mock_scored_point():
    """Provides a mock ScoredPoint for deserialization tests."""
    point = MagicMock()
    point.id = "12345678-1234-5678-1234-567812345678"
    point.payload = {"content": "test content"}
    point.vector = [0.1, 0.2, 0.3]
    return point
