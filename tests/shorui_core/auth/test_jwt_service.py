"""Unit tests for JwtService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
import pytest

from shorui_core.auth.jwt_service import JwtService


class TestAccessToken:
    """Tests for access token generation and verification."""

    def test_create_access_token_returns_string(self):
        """Access token should be a JWT string."""
        service = JwtService(dsn="mock://", secret="test-secret-key-256-bits-long-ok")
        token = service.create_access_token(
            user_id="user-123",
            tenant_id="tenant-abc",
            email="test@example.com",
            role="user",
        )

        assert isinstance(token, str)
        assert len(token) > 0
        # JWT has 3 parts separated by dots
        assert token.count(".") == 2

    def test_verify_access_token_returns_payload(self):
        """Valid token should return decoded payload."""
        service = JwtService(dsn="mock://", secret="test-secret-key-256-bits-long-ok")
        token = service.create_access_token(
            user_id="user-123",
            tenant_id="tenant-abc",
            email="test@example.com",
            role="admin",
            scopes=["admin"],
        )

        payload = service.verify_access_token(token)

        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["tenant_id"] == "tenant-abc"
        assert payload["email"] == "test@example.com"
        assert payload["role"] == "admin"
        assert "admin" in payload["scopes"]

    def test_verify_access_token_invalid_returns_none(self):
        """Invalid token should return None."""
        service = JwtService(dsn="mock://", secret="test-secret-key-256-bits-long-ok")

        payload = service.verify_access_token("invalid.token.here")

        assert payload is None

    def test_verify_access_token_wrong_secret_returns_none(self):
        """Token signed with different secret should return None."""
        service1 = JwtService(dsn="mock://", secret="secret-one-long-enough-for-256")
        service2 = JwtService(dsn="mock://", secret="secret-two-long-enough-for-256")

        token = service1.create_access_token(
            user_id="user-123",
            tenant_id="tenant-abc",
            email="test@example.com",
        )

        payload = service2.verify_access_token(token)

        assert payload is None

    def test_access_token_contains_expiry(self):
        """Token payload should include exp claim."""
        service = JwtService(dsn="mock://", secret="test-secret-key-256-bits-long-ok")
        token = service.create_access_token(
            user_id="user-123",
            tenant_id="tenant-abc",
            email="test@example.com",
        )

        payload = service.verify_access_token(token)

        assert payload is not None
        assert "exp" in payload
        assert "iat" in payload
        assert payload["exp"] > payload["iat"]


class TestRefreshToken:
    """Tests for refresh token operations."""

    def test_create_refresh_token_returns_string(self):
        """Refresh token should be a URL-safe string."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        service = JwtService(dsn="mock://", secret="test-secret-key-256-bits-long-ok")

        with patch("psycopg.connect", return_value=mock_conn):
            token = service.create_refresh_token("user-123")

        assert isinstance(token, str)
        assert len(token) > 50  # URL-safe base64 of 64 bytes

    def test_create_refresh_token_inserts_to_db(self):
        """Refresh token creation should insert hash to database."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        service = JwtService(dsn="mock://", secret="test-secret-key-256-bits-long-ok")

        with patch("psycopg.connect", return_value=mock_conn):
            service.create_refresh_token("user-123")

        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "INSERT INTO refresh_tokens" in sql

    def test_verify_refresh_token_valid(self):
        """Valid refresh token should return user_id."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            "user-123",
            datetime.now(timezone.utc) + timedelta(days=1),  # expires_at
            None,  # revoked_at
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        service = JwtService(dsn="mock://", secret="test-secret-key-256-bits-long-ok")

        with patch("psycopg.connect", return_value=mock_conn):
            user_id = service.verify_refresh_token("some-token")

        assert user_id == "user-123"

    def test_verify_refresh_token_expired(self):
        """Expired refresh token should return None."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            "user-123",
            datetime.now(timezone.utc) - timedelta(days=1),  # expired
            None,
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        service = JwtService(dsn="mock://", secret="test-secret-key-256-bits-long-ok")

        with patch("psycopg.connect", return_value=mock_conn):
            user_id = service.verify_refresh_token("some-token")

        assert user_id is None

    def test_verify_refresh_token_revoked(self):
        """Revoked refresh token should return None."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            "user-123",
            datetime.now(timezone.utc) + timedelta(days=1),
            datetime.now(timezone.utc),  # revoked_at is set
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        service = JwtService(dsn="mock://", secret="test-secret-key-256-bits-long-ok")

        with patch("psycopg.connect", return_value=mock_conn):
            user_id = service.verify_refresh_token("some-token")

        assert user_id is None

    def test_verify_refresh_token_not_found(self):
        """Unknown refresh token should return None."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        service = JwtService(dsn="mock://", secret="test-secret-key-256-bits-long-ok")

        with patch("psycopg.connect", return_value=mock_conn):
            user_id = service.verify_refresh_token("unknown-token")

        assert user_id is None


class TestTokenRevocation:
    """Tests for token revocation."""

    def test_revoke_refresh_token_updates_db(self):
        """Revoking token should set revoked_at in database."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        service = JwtService(dsn="mock://", secret="test-secret-key-256-bits-long-ok")

        with patch("psycopg.connect", return_value=mock_conn):
            result = service.revoke_refresh_token("some-token")

        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        assert "UPDATE refresh_tokens" in sql
        assert "revoked_at" in sql

    def test_revoke_all_for_user(self):
        """Revoking all tokens for user should update multiple rows."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 3  # 3 tokens revoked

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        service = JwtService(dsn="mock://", secret="test-secret-key-256-bits-long-ok")

        with patch("psycopg.connect", return_value=mock_conn):
            count = service.revoke_all_for_user("user-123")

        assert count == 3


class TestConfiguration:
    """Tests for service configuration."""

    def test_missing_secret_raises(self):
        """Missing JWT_SECRET should raise ValueError."""
        with patch("shorui_core.auth.jwt_service.settings") as mock_settings:
            mock_settings.POSTGRES_DSN = "mock://"
            mock_settings.JWT_SECRET = ""

            with pytest.raises(ValueError, match="JWT_SECRET"):
                JwtService()
