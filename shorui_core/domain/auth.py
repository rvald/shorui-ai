"""
Authentication and authorization domain models.

This module defines the core data structures for auth:
- Scope: Permission scopes for API access
- Principal: Authenticated identity (from API key)
- AuthContext: Request-scoped auth context
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Scope(str, Enum):
    """Authorization scopes for API access."""

    INGEST_WRITE = "ingest:write"
    COMPLIANCE_READ = "compliance:read"
    AUDIT_READ = "audit:read"
    RAG_READ = "rag:read"
    ADMIN = "admin"  # Full access


@dataclass(frozen=True)
class Principal:
    """Authenticated identity derived from API key."""

    tenant_id: str
    key_id: str
    key_name: str | None
    scopes: frozenset[str]


@dataclass
class AuthContext:
    """Request-scoped authentication context.

    Attached to request.state.auth by the auth middleware.
    """

    principal: Principal
    authenticated_at: datetime
    request_id: str

    @property
    def tenant_id(self) -> str:
        """Get tenant_id from principal."""
        return self.principal.tenant_id

    def has_scope(self, scope: str | Scope) -> bool:
        """Check if principal has the required scope.

        Args:
            scope: The scope to check (string or Scope enum).

        Returns:
            True if principal has the scope or admin scope.
        """
        scope_str = scope.value if isinstance(scope, Scope) else scope
        return (
            scope_str in self.principal.scopes
            or Scope.ADMIN.value in self.principal.scopes
        )
