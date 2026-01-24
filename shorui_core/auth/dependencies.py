"""
FastAPI dependencies for authorization.

Provides dependency injection for:
- Extracting auth context from requests
- Requiring specific scopes for endpoints
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from shorui_core.domain.auth import AuthContext, Scope


def get_auth_context(request: Request) -> AuthContext:
    """Get auth context from request state.

    Args:
        request: The FastAPI request object.

    Returns:
        AuthContext attached by auth middleware.

    Raises:
        HTTPException: 401 if not authenticated.
    """
    auth = getattr(request.state, "auth", None)
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return auth


def get_tenant_id(auth: AuthContext = Depends(get_auth_context)) -> str:
    """Get tenant_id from authenticated context.

    This is the canonical way to get tenant_id in routes.
    The tenant_id is derived from the API key, never from client input.

    Args:
        auth: The auth context from middleware.

    Returns:
        The authenticated tenant_id.
    """
    return auth.tenant_id


def require_scope(scope: str | Scope):
    """Dependency factory to require a specific scope.

    Usage:
        @router.post("/documents")
        async def upload(auth: AuthContext = Depends(require_scope(Scope.INGEST_WRITE))):
            ...

    Args:
        scope: The required scope (string or Scope enum).

    Returns:
        A dependency function that checks the scope.
    """

    def _check_scope(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if not auth.has_scope(scope):
            scope_str = scope.value if isinstance(scope, Scope) else scope
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required scope: {scope_str}",
            )
        return auth

    return _check_scope


# Convenience dependencies for common scopes
require_ingest_write = require_scope(Scope.INGEST_WRITE)
require_compliance_read = require_scope(Scope.COMPLIANCE_READ)
require_audit_read = require_scope(Scope.AUDIT_READ)
require_rag_read = require_scope(Scope.RAG_READ)
