"""
Unit tests for MinIO infrastructure client.

The MinIO client should follow the same patterns as Qdrant and Neo4j:
- Singleton pattern for connection reuse
- Settings-based configuration from shorui_core.config
"""

from unittest.mock import MagicMock, patch

import pytest


class TestMinioClientConnector:
    """Tests for MinIO singleton connector."""

    def test_get_instance_returns_minio_client(self, mock_minio_module):
        """get_instance() should return a MinIO client."""
        from shorui_core.infrastructure.minio import MinioClientConnector

        # Reset singleton
        MinioClientConnector._instance = None

        client = MinioClientConnector.get_instance()

        assert client is not None

    def test_returns_same_instance_on_multiple_calls(self, mock_minio_module):
        """Multiple calls should return the same instance (singleton)."""
        from shorui_core.infrastructure.minio import MinioClientConnector

        # Reset singleton
        MinioClientConnector._instance = None

        client1 = MinioClientConnector.get_instance()
        client2 = MinioClientConnector.get_instance()

        assert client1 is client2

    def test_uses_settings_for_configuration(self, mock_minio_module):
        """Should use settings from shorui_core.config."""
        from shorui_core.infrastructure.minio import MinioClientConnector

        # Reset singleton
        MinioClientConnector._instance = None

        with patch("shorui_core.infrastructure.minio.settings") as mock_settings:
            mock_settings.MINIO_ENDPOINT = "minio.example.com:9000"
            mock_settings.MINIO_ACCESS_KEY = "myaccess"
            mock_settings.MINIO_SECRET_KEY = "mysecret"
            mock_settings.MINIO_SECURE = False

            MinioClientConnector.get_instance()

            # Verify Minio was called with correct endpoint
            mock_minio_module.assert_called_once()
            call_kwargs = mock_minio_module.call_args[1]
            assert call_kwargs["endpoint"] == "minio.example.com:9000"


class TestGetMinioClientFunction:
    """Tests for the convenience function."""

    def test_get_minio_client_returns_client(self, mock_minio_module):
        """get_minio_client() should return a client."""
        from shorui_core.infrastructure.minio import MinioClientConnector, get_minio_client

        # Reset singleton
        MinioClientConnector._instance = None

        client = get_minio_client()

        assert client is not None


# --- Fixtures ---


@pytest.fixture
def mock_minio_module():
    """Mock the Minio class from minio package."""
    with patch("shorui_core.infrastructure.minio.Minio") as mock_minio:
        mock_client = MagicMock()
        mock_minio.return_value = mock_client
        yield mock_minio
