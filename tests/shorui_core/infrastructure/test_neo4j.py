"""
Unit tests for Neo4j infrastructure client.

These tests verify the singleton pattern and connection behavior
of the shared Neo4j client.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestNeo4jClientConnector:
    """Tests for the Neo4j client singleton."""

    def test_get_instance_returns_driver(self, mock_neo4j_driver):
        """get_instance() should return a Neo4j driver."""
        from shorui_core.infrastructure.neo4j import Neo4jClientConnector

        # Reset singleton for test isolation
        Neo4jClientConnector._instance = None

        with patch("shorui_core.infrastructure.neo4j.GraphDatabase") as mock_gdb:
            mock_gdb.driver.return_value = mock_neo4j_driver

            driver = Neo4jClientConnector.get_instance()

            assert driver is not None
            mock_gdb.driver.assert_called_once()

    def test_get_instance_returns_same_instance_on_multiple_calls(self, mock_neo4j_driver):
        """get_instance() should return the same driver instance (singleton)."""
        from shorui_core.infrastructure.neo4j import Neo4jClientConnector

        # Reset singleton for test isolation
        Neo4jClientConnector._instance = None

        with patch("shorui_core.infrastructure.neo4j.GraphDatabase") as mock_gdb:
            mock_gdb.driver.return_value = mock_neo4j_driver

            driver1 = Neo4jClientConnector.get_instance()
            driver2 = Neo4jClientConnector.get_instance()

            assert driver1 is driver2
            # Should only call driver() once due to singleton
            assert mock_gdb.driver.call_count == 1

    def test_get_instance_uses_settings_for_connection(self, mock_neo4j_driver):
        """get_instance() should use settings for URI and credentials."""
        from shorui_core.infrastructure.neo4j import Neo4jClientConnector

        # Reset singleton for test isolation
        Neo4jClientConnector._instance = None

        with (
            patch("shorui_core.infrastructure.neo4j.GraphDatabase") as mock_gdb,
            patch("shorui_core.infrastructure.neo4j.settings") as mock_settings,
        ):
            mock_gdb.driver.return_value = mock_neo4j_driver
            mock_settings.NEO4J_URI = "bolt://test:7687"
            mock_settings.NEO4J_USER = "test_user"
            mock_settings.NEO4J_PASSWORD = "test_pass"

            Neo4jClientConnector.get_instance()

            mock_gdb.driver.assert_called_once_with(
                uri="bolt://test:7687", auth=("test_user", "test_pass")
            )


class TestGetNeo4jClient:
    """Tests for the convenience function."""

    def test_get_neo4j_client_returns_driver(self, mock_neo4j_driver):
        """get_neo4j_client() should return the singleton driver."""
        from shorui_core.infrastructure.neo4j import Neo4jClientConnector, get_neo4j_client

        # Reset singleton
        Neo4jClientConnector._instance = None

        with patch("shorui_core.infrastructure.neo4j.GraphDatabase") as mock_gdb:
            mock_gdb.driver.return_value = mock_neo4j_driver

            driver = get_neo4j_client()

            assert driver is mock_neo4j_driver


# --- Fixtures ---


@pytest.fixture
def mock_neo4j_driver():
    """Provides a mock Neo4j driver."""
    return MagicMock()
