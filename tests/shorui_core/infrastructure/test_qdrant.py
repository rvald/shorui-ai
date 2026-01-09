"""
Unit tests for Qdrant infrastructure client.

These tests verify the singleton pattern and connection behavior
of the shared Qdrant client.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestQdrantDatabaseConnector:
    """Tests for the Qdrant client singleton."""

    def test_creates_local_client_when_not_using_cloud(self, mock_qdrant_client):
        """Should create a local Qdrant client when USE_QDRANT_CLOUD is False."""
        from shorui_core.infrastructure.qdrant import QdrantDatabaseConnector

        # Reset singleton for test isolation
        QdrantDatabaseConnector._instance = None

        with (
            patch("shorui_core.infrastructure.qdrant.QdrantClient") as mock_client_cls,
            patch("shorui_core.infrastructure.qdrant.settings") as mock_settings,
        ):
            mock_settings.USE_QDRANT_CLOUD = False
            mock_settings.QDRANT_DATABASE_HOST = "localhost"
            mock_settings.QDRANT_DATABASE_PORT = 6334
            mock_client_cls.return_value = mock_qdrant_client

            client = QdrantDatabaseConnector.get_instance()

            mock_client_cls.assert_called_once_with(host="localhost", port=6334)
            assert client is mock_qdrant_client

    def test_creates_cloud_client_when_using_cloud(self, mock_qdrant_client):
        """Should create a cloud Qdrant client when USE_QDRANT_CLOUD is True."""
        from shorui_core.infrastructure.qdrant import QdrantDatabaseConnector

        # Reset singleton
        QdrantDatabaseConnector._instance = None

        with (
            patch("shorui_core.infrastructure.qdrant.QdrantClient") as mock_client_cls,
            patch("shorui_core.infrastructure.qdrant.settings") as mock_settings,
        ):
            mock_settings.USE_QDRANT_CLOUD = True
            mock_settings.QDRANT_CLOUD_URL = "https://cloud.qdrant.io"
            mock_settings.QDRANT_APIKEY = "test-api-key"
            mock_client_cls.return_value = mock_qdrant_client

            client = QdrantDatabaseConnector.get_instance()

            mock_client_cls.assert_called_once_with(
                url="https://cloud.qdrant.io", api_key="test-api-key"
            )
            assert client is mock_qdrant_client

    def test_returns_same_instance_on_multiple_calls(self, mock_qdrant_client):
        """get_instance() should return the same client instance (singleton)."""
        from shorui_core.infrastructure.qdrant import QdrantDatabaseConnector

        # Reset singleton
        QdrantDatabaseConnector._instance = None

        with (
            patch("shorui_core.infrastructure.qdrant.QdrantClient") as mock_client_cls,
            patch("shorui_core.infrastructure.qdrant.settings") as mock_settings,
        ):
            mock_settings.USE_QDRANT_CLOUD = False
            mock_settings.QDRANT_DATABASE_HOST = "localhost"
            mock_settings.QDRANT_DATABASE_PORT = 6334
            mock_client_cls.return_value = mock_qdrant_client

            client1 = QdrantDatabaseConnector.get_instance()
            client2 = QdrantDatabaseConnector.get_instance()

            assert client1 is client2
            assert mock_client_cls.call_count == 1


class TestGetConnectionFunction:
    """Tests for the module-level connection object."""

    def test_connection_is_qdrant_client(self, mock_qdrant_client):
        """The module-level 'connection' should be a QdrantClient."""
        from shorui_core.infrastructure.qdrant import QdrantDatabaseConnector

        # Reset singleton
        QdrantDatabaseConnector._instance = None

        with (
            patch("shorui_core.infrastructure.qdrant.QdrantClient") as mock_client_cls,
            patch("shorui_core.infrastructure.qdrant.settings") as mock_settings,
        ):
            mock_settings.USE_QDRANT_CLOUD = False
            mock_settings.QDRANT_DATABASE_HOST = "localhost"
            mock_settings.QDRANT_DATABASE_PORT = 6334
            mock_client_cls.return_value = mock_qdrant_client

            client = QdrantDatabaseConnector.get_instance()

            assert client is not None


# --- Fixtures ---


@pytest.fixture
def mock_qdrant_client():
    """Provides a mock Qdrant client."""
    return MagicMock()
