"""Unit tests for UserService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from shorui_core.auth.user_service import UserService


class TestPasswordHashing:
    """Tests for password hashing functionality."""

    def test_hash_password_returns_bcrypt_hash(self):
        """Password hash should be bcrypt format."""
        service = UserService(dsn="mock://")
        hash_result = service._hash_password("testpass123")

        assert hash_result.startswith("$2b$")
        assert len(hash_result) == 60  # bcrypt hash length

    def test_verify_password_correct(self):
        """Correct password should verify."""
        service = UserService(dsn="mock://")
        password = "SecurePass123!"
        hash_result = service._hash_password(password)

        assert service._verify_password(password, hash_result) is True

    def test_verify_password_incorrect(self):
        """Incorrect password should not verify."""
        service = UserService(dsn="mock://")
        hash_result = service._hash_password("correct")

        assert service._verify_password("wrong", hash_result) is False


class TestEmailValidation:
    """Tests for email validation."""

    def test_valid_email(self):
        """Valid email should pass."""
        service = UserService(dsn="mock://")

        assert service._validate_email("user@example.com") is True
        assert service._validate_email("test.user+tag@domain.co.uk") is True

    def test_invalid_email(self):
        """Invalid email should fail."""
        service = UserService(dsn="mock://")

        assert service._validate_email("not-an-email") is False
        assert service._validate_email("@missing.local") is False
        assert service._validate_email("missing@domain") is False


class TestPasswordValidation:
    """Tests for password strength validation."""

    def test_valid_password(self):
        """Strong password should pass."""
        service = UserService(dsn="mock://")
        is_valid, error = service._validate_password("SecurePass123!")

        assert is_valid is True
        assert error is None

    def test_password_too_short(self):
        """Short password should fail."""
        service = UserService(dsn="mock://")
        is_valid, error = service._validate_password("Short1")

        assert is_valid is False
        assert "8 characters" in error

    def test_password_no_uppercase(self):
        """Password without uppercase should fail."""
        service = UserService(dsn="mock://")
        is_valid, error = service._validate_password("lowercase123")

        assert is_valid is False
        assert "uppercase" in error

    def test_password_no_lowercase(self):
        """Password without lowercase should fail."""
        service = UserService(dsn="mock://")
        is_valid, error = service._validate_password("UPPERCASE123")

        assert is_valid is False
        assert "lowercase" in error

    def test_password_no_digit(self):
        """Password without digit should fail."""
        service = UserService(dsn="mock://")
        is_valid, error = service._validate_password("NoDigitsHere")

        assert is_valid is False
        assert "digit" in error


class TestTenantIdGeneration:
    """Tests for tenant ID generation."""

    def test_generates_url_safe_id(self):
        """Generated tenant ID should be URL-safe."""
        service = UserService(dsn="mock://")
        tenant_id = service._generate_tenant_id("Acme Corp")

        assert "-" in tenant_id  # Contains hyphen separator
        assert " " not in tenant_id
        assert all(c.isalnum() or c == "-" for c in tenant_id)

    def test_handles_special_characters(self):
        """Special characters should be stripped."""
        service = UserService(dsn="mock://")
        tenant_id = service._generate_tenant_id("Test & Co. (Inc)")

        assert "&" not in tenant_id
        assert "." not in tenant_id
        assert "(" not in tenant_id


class TestUserRegistration:
    """Tests for user registration."""

    def test_register_creates_user(self):
        """Registration should create user record."""
        service = UserService(dsn="mock://")

        mock_cursor = MagicMock()
        # Email check returns None (not exists)
        mock_cursor.fetchone.side_effect = [None, None, (MagicMock(),)]

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("psycopg.connect", return_value=mock_conn):
            user = service.register(
                email="test@example.com",
                password="SecurePass123!",
                tenant_name="Test Org",
            )

        assert user["email"] == "test@example.com"
        assert "user_id" in user
        assert "tenant_id" in user

    def test_register_invalid_email_raises(self):
        """Invalid email should raise ValueError."""
        service = UserService(dsn="mock://")

        with pytest.raises(ValueError, match="Invalid email"):
            service.register(
                email="not-valid",
                password="SecurePass123!",
                tenant_name="Test",
            )

    def test_register_weak_password_raises(self):
        """Weak password should raise ValueError."""
        service = UserService(dsn="mock://")

        with pytest.raises(ValueError, match="8 characters"):
            service.register(
                email="test@example.com",
                password="weak",
                tenant_name="Test",
            )


class TestUserAuthentication:
    """Tests for user authentication."""

    def test_authenticate_valid_credentials(self):
        """Valid credentials should return user."""
        service = UserService(dsn="mock://")
        password_hash = service._hash_password("SecurePass123!")

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            "user-id-123",
            "tenant-abc",
            "test@example.com",
            password_hash,
            "user",
            MagicMock(),  # created_at
            None,  # last_login_at
            True,  # is_active
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("psycopg.connect", return_value=mock_conn):
            user = service.authenticate("test@example.com", "SecurePass123!")

        assert user is not None
        assert user["user_id"] == "user-id-123"
        assert user["tenant_id"] == "tenant-abc"

    def test_authenticate_wrong_password(self):
        """Wrong password should return None."""
        service = UserService(dsn="mock://")
        password_hash = service._hash_password("correct")

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            "user-id-123",
            "tenant-abc",
            "test@example.com",
            password_hash,
            "user",
            None,
            None,
            True,
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("psycopg.connect", return_value=mock_conn):
            user = service.authenticate("test@example.com", "wrong")

        assert user is None

    def test_authenticate_user_not_found(self):
        """Unknown email should return None."""
        service = UserService(dsn="mock://")

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("psycopg.connect", return_value=mock_conn):
            user = service.authenticate("unknown@example.com", "password")

        assert user is None

    def test_authenticate_inactive_user(self):
        """Inactive user should return None."""
        service = UserService(dsn="mock://")
        password_hash = service._hash_password("SecurePass123!")

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            "user-id-123",
            "tenant-abc",
            "test@example.com",
            password_hash,
            "user",
            None,
            None,
            False,  # is_active = False
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("psycopg.connect", return_value=mock_conn):
            user = service.authenticate("test@example.com", "SecurePass123!")

        assert user is None
