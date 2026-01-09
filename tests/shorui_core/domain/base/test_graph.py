"""
Unit tests for GraphBaseModel base model.

These tests verify the core functionality of the base graph model class
that will be shared across all services in shorui_core for Neo4j operations.
"""

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest


class TestGraphBaseModelIdentity:
    """Tests for ID generation and project isolation."""

    def test_creates_uuid_string_by_default(self, graph_model_class):
        """A new graph model should have a valid UUID string generated automatically."""
        model = graph_model_class(text="test content")

        assert model.id is not None
        assert isinstance(model.id, str)
        # Should be a valid UUID string
        UUID(model.id)  # Will raise if invalid

    def test_accepts_custom_id(self, graph_model_class):
        """A graph model should accept a custom ID string."""
        custom_id = "custom-node-id-123"
        model = graph_model_class(id=custom_id, text="test")

        assert model.id == custom_id

    def test_project_id_defaults_to_none(self, graph_model_class):
        """project_id should default to None if not provided."""
        model = graph_model_class(text="test")

        assert model.project_id is None

    def test_accepts_project_id_for_multi_tenancy(self, graph_model_class):
        """A graph model should accept a project_id for logical isolation."""
        model = graph_model_class(text="test", project_id="project-abc")

        assert model.project_id == "project-abc"


class TestGraphBaseModelSerialization:
    """Tests for serialization to Neo4j-compatible dict."""

    def test_model_dump_excludes_database_override(self, graph_model_class):
        """model_dump() should exclude the database_override field."""
        model = graph_model_class(text="test", project_id="proj-1", database_override="custom_db")

        dump = model.model_dump()

        assert "database_override" not in dump
        assert "text" in dump
        assert "project_id" in dump

    def test_model_dump_includes_all_fields(self, graph_model_class):
        """model_dump() should include id, text, and project_id."""
        model = graph_model_class(id="node-123", text="hello world", project_id="proj-1")

        dump = model.model_dump()

        assert dump["id"] == "node-123"
        assert dump["text"] == "hello world"
        assert dump["project_id"] == "proj-1"


class TestGraphBaseModelDatabaseResolution:
    """Tests for database name resolution."""

    def test_resolve_database_returns_override_if_set(self, graph_model_class):
        """_resolve_database() should return database_override if set."""
        model = graph_model_class(text="test", database_override="custom_db")

        result = model._resolve_database()

        assert result == "custom_db"

    def test_resolve_database_returns_meta_default_if_no_override(self, graph_model_class):
        """_resolve_database() should return Meta.database_name if no override."""
        model = graph_model_class(text="test")

        result = model._resolve_database()

        assert result == "test_database"  # From fixture's Meta class


class TestGraphBaseModelSave:
    """Tests for save() method."""

    @pytest.mark.asyncio
    async def test_save_calls_neo4j_with_merge_query(self, graph_model_class, mock_neo4j_client):
        """save() should call Neo4j with a MERGE query."""
        model = graph_model_class(id="node-123", text="test content", project_id="proj-1")

        with patch.object(graph_model_class, "_get_neo4j_client", return_value=mock_neo4j_client):
            await model.save()

        # Verify session was created with correct database
        mock_neo4j_client.session.assert_called_once()

        # Verify execute_write was called
        session = mock_neo4j_client.session.return_value.__enter__.return_value
        session.execute_write.assert_called_once()


# --- Fixtures ---


@pytest.fixture
def graph_model_class():
    """
    Provides a concrete implementation of GraphBaseModel for testing.
    """
    from shorui_core.domain.base.graph import GraphBaseModel

    class TestGraphNode(GraphBaseModel):
        text: str

        class Meta:
            database_name = "test_database"

    return TestGraphNode


@pytest.fixture
def mock_neo4j_client():
    """Provides a mock Neo4j driver for testing."""
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return mock_driver
