"""
Auth module for shorui-ai.

Provides API key authentication, middleware, and authorization dependencies.
"""

from shorui_core.auth.api_key_service import ApiKeyService
from shorui_core.auth.dependencies import (
    get_auth_context,
    get_tenant_id,
    require_scope,
    require_ingest_write,
    require_compliance_read,
    require_audit_read,
    require_rag_read,
)
from shorui_core.auth.middleware import AuthMiddleware

__all__ = [
    "ApiKeyService",
    "AuthMiddleware",
    "get_auth_context",
    "get_tenant_id",
    "require_scope",
    "require_ingest_write",
    "require_compliance_read",
    "require_audit_read",
    "require_rag_read",
]
