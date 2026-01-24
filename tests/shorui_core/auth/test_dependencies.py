"""Unit tests for auth dependencies."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from shorui_core.auth.dependencies import (
    get_auth_context,
    get_tenant_id,
    require_scope,
)
from shorui_core.domain.auth import AuthContext, Principal, Scope


class TestGetAuthContext:
    """Tests for get_auth_context dependency."""

    def test_returns_auth_context_from_request_state(self):
        """get_auth_context returns AuthContext from request.state."""
        mock_request = MagicMock()
        mock_request.state.auth = AuthContext(
            principal=Principal(
                tenant_id="test-tenant",
                key_id="key-123",
                key_name="Test Key",
                scopes=frozenset(["ingest:write"]),
            ),
            authenticated_at=datetime.now(timezone.utc),
            request_id="req-123",
        )

        result = get_auth_context(mock_request)

        assert result.tenant_id == "test-tenant"
        assert result.principal.key_id == "key-123"

    def test_raises_401_when_not_authenticated(self):
        """get_auth_context raises 401 when auth is missing."""
        mock_request = MagicMock()
        mock_request.state = MagicMock(spec=[])  # No 'auth' attribute

        with pytest.raises(HTTPException) as exc_info:
            get_auth_context(mock_request)

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail


class TestGetTenantId:
    """Tests for get_tenant_id dependency."""

    def test_returns_tenant_id_from_auth_context(self):
        """get_tenant_id returns tenant_id from AuthContext."""
        auth = AuthContext(
            principal=Principal(
                tenant_id="my-tenant",
                key_id="key-123",
                key_name=None,
                scopes=frozenset([]),
            ),
            authenticated_at=datetime.now(timezone.utc),
            request_id="req-123",
        )

        result = get_tenant_id(auth)

        assert result == "my-tenant"


class TestRequireScope:
    """Tests for require_scope dependency factory."""

    def test_passes_when_scope_present(self):
        """require_scope passes when scope is in principal."""
        auth = AuthContext(
            principal=Principal(
                tenant_id="test-tenant",
                key_id="key-123",
                key_name=None,
                scopes=frozenset(["ingest:write", "rag:read"]),
            ),
            authenticated_at=datetime.now(timezone.utc),
            request_id="req-123",
        )

        check_fn = require_scope(Scope.INGEST_WRITE)
        result = check_fn(auth)

        assert result == auth

    def test_passes_when_admin_scope_present(self):
        """require_scope passes when admin scope is present."""
        auth = AuthContext(
            principal=Principal(
                tenant_id="test-tenant",
                key_id="key-123",
                key_name=None,
                scopes=frozenset(["admin"]),
            ),
            authenticated_at=datetime.now(timezone.utc),
            request_id="req-123",
        )

        check_fn = require_scope(Scope.INGEST_WRITE)
        result = check_fn(auth)

        assert result == auth

    def test_raises_403_when_scope_missing(self):
        """require_scope raises 403 when scope is missing."""
        auth = AuthContext(
            principal=Principal(
                tenant_id="test-tenant",
                key_id="key-123",
                key_name=None,
                scopes=frozenset(["rag:read"]),  # Missing ingest:write
            ),
            authenticated_at=datetime.now(timezone.utc),
            request_id="req-123",
        )

        check_fn = require_scope(Scope.INGEST_WRITE)

        with pytest.raises(HTTPException) as exc_info:
            check_fn(auth)

        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in exc_info.value.detail

    def test_accepts_string_scope(self):
        """require_scope accepts string scope argument."""
        auth = AuthContext(
            principal=Principal(
                tenant_id="test-tenant",
                key_id="key-123",
                key_name=None,
                scopes=frozenset(["custom:scope"]),
            ),
            authenticated_at=datetime.now(timezone.utc),
            request_id="req-123",
        )

        check_fn = require_scope("custom:scope")
        result = check_fn(auth)

        assert result == auth
