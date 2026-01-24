"""Unit tests for API key service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
import pytest

from shorui_core.auth.api_key_service import ApiKeyService


class TestApiKeyGeneration:
    """Tests for API key generation."""

    def test_generate_key_returns_tuple(self):
        """generate_key returns (raw_key, hash) tuple."""
        service = ApiKeyService(dsn="mock://")
        raw_key, key_hash = service.generate_key()

        assert isinstance(raw_key, str)
        assert isinstance(key_hash, str)

    def test_generate_key_has_prefix(self):
        """Generated key starts with 'shorui_' prefix."""
        service = ApiKeyService(dsn="mock://")
        raw_key, _ = service.generate_key()

        assert raw_key.startswith("shorui_")

    def test_generate_key_hash_is_sha256(self):
        """Key hash is 64 characters (SHA-256 hex)."""
        service = ApiKeyService(dsn="mock://")
        _, key_hash = service.generate_key()

        assert len(key_hash) == 64

    def test_hash_is_deterministic(self):
        """Same key produces same hash."""
        service = ApiKeyService(dsn="mock://")
        test_key = "shorui_test123456789"

        hash1 = service._hash_key(test_key)
        hash2 = service._hash_key(test_key)

        assert hash1 == hash2


class TestApiKeyValidation:
    """Tests for API key validation."""

    def test_validate_key_returns_record_on_match(self):
        """validate_key returns key record when key is valid."""
        service = ApiKeyService(dsn="mock://")

        # Mock database response
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            "key-id-123",
            "tenant-abc",
            "My API Key",
            ["ingest:write", "rag:read"],
            None,  # expires_at
            True,  # is_active
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("psycopg.connect", return_value=mock_conn):
            result = service.validate_key("shorui_test123")

        assert result is not None
        assert result["key_id"] == "key-id-123"
        assert result["tenant_id"] == "tenant-abc"
        assert result["name"] == "My API Key"
        assert "ingest:write" in result["scopes"]

    def test_validate_key_returns_none_for_unknown_key(self):
        """validate_key returns None when key not found."""
        service = ApiKeyService(dsn="mock://")

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("psycopg.connect", return_value=mock_conn):
            result = service.validate_key("shorui_invalid")

        assert result is None

    def test_validate_key_returns_none_for_inactive_key(self):
        """validate_key returns None when key is inactive."""
        service = ApiKeyService(dsn="mock://")

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            "key-id-123",
            "tenant-abc",
            "Revoked Key",
            ["admin"],
            None,
            False,  # is_active = False
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("psycopg.connect", return_value=mock_conn):
            result = service.validate_key("shorui_revoked")

        assert result is None

    def test_validate_key_returns_none_for_expired_key(self):
        """validate_key returns None when key is expired."""
        service = ApiKeyService(dsn="mock://")

        expired_time = datetime.now(timezone.utc) - timedelta(days=1)
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            "key-id-123",
            "tenant-abc",
            "Expired Key",
            ["admin"],
            expired_time,  # expires_at in the past
            True,
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("psycopg.connect", return_value=mock_conn):
            result = service.validate_key("shorui_expired")

        assert result is None


class TestApiKeyCreation:
    """Tests for API key creation."""

    def test_create_key_returns_raw_key_and_id(self):
        """create_key returns (raw_key, key_id) tuple."""
        service = ApiKeyService(dsn="mock://")

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("psycopg.connect", return_value=mock_conn):
            raw_key, key_id = service.create_key(
                tenant_id="test-tenant",
                scopes=["ingest:write"],
                name="Test Key",
            )

        assert raw_key.startswith("shorui_")
        assert len(key_id) == 36  # UUID format

    def test_create_key_inserts_to_database(self):
        """create_key inserts record into api_keys table."""
        service = ApiKeyService(dsn="mock://")

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("psycopg.connect", return_value=mock_conn):
            service.create_key(
                tenant_id="test-tenant",
                scopes=["compliance:read", "rag:read"],
                name="My Key",
            )

        # Verify INSERT was called
        mock_cursor.execute.assert_called_once()
        sql, params = mock_cursor.execute.call_args[0]
        assert "INSERT INTO api_keys" in sql
        assert "test-tenant" in params
