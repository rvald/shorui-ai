"""
FastAPI auth middleware.

Authenticates requests via X-API-Key header and attaches AuthContext to request.state.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from shorui_core.auth.api_key_service import ApiKeyService
from shorui_core.domain.auth import AuthContext, Principal, Scope

# Endpoints that don't require authentication
PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/ingest/health",
        "/rag/health",
        "/compliance/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to authenticate requests via API key.

    When enabled (require_auth=True), all requests to non-public paths
    must include a valid X-API-Key header. The derived tenant_id and
    scopes are attached to request.state.auth as an AuthContext.

    When disabled (require_auth=False), a default dev context is injected.
    """

    def __init__(self, app, require_auth: bool = True):
        """Initialize auth middleware.

        Args:
            app: The FastAPI/Starlette application.
            require_auth: If True, enforce authentication. If False, inject dev context.
        """
        super().__init__(app)
        self.require_auth = require_auth
        self._api_key_service: ApiKeyService | None = None

    @property
    def api_key_service(self) -> ApiKeyService:
        """Lazily initialize API key service to avoid import-time DB connections."""
        if self._api_key_service is None:
            self._api_key_service = ApiKeyService()
        return self._api_key_service

    async def dispatch(self, request: Request, call_next):
        """Process incoming request for authentication."""
        # Generate request_id for correlation
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        request.state.request_id = request_id

        # Normalize path for comparison
        path = request.url.path.rstrip("/")

        # Skip auth for public paths
        if path in PUBLIC_PATHS or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # Skip auth if disabled (dev mode)
        if not self.require_auth:
            request.state.auth = AuthContext(
                principal=Principal(
                    tenant_id="default",
                    key_id="dev",
                    key_name="Development",
                    scopes=frozenset([Scope.ADMIN.value]),
                ),
                authenticated_at=datetime.now(timezone.utc),
                request_id=request_id,
            )
            return await call_next(request)

        # Extract API key from header
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            logger.warning(f"[{request_id}] Missing X-API-Key header for {path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing X-API-Key header"},
            )

        # Validate key
        try:
            key_record = self.api_key_service.validate_key(api_key)
        except Exception as e:
            logger.error(f"[{request_id}] API key validation error: {e}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Authentication service unavailable"},
            )

        if not key_record:
            logger.warning(f"[{request_id}] Invalid API key for {path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired API key"},
            )

        # Attach auth context to request
        request.state.auth = AuthContext(
            principal=Principal(
                tenant_id=key_record["tenant_id"],
                key_id=key_record["key_id"],
                key_name=key_record["name"],
                scopes=frozenset(key_record["scopes"]),
            ),
            authenticated_at=datetime.now(timezone.utc),
            request_id=request_id,
        )

        logger.debug(
            f"[{request_id}] Authenticated: tenant={key_record['tenant_id']} "
            f"key={key_record['name'] or key_record['key_id'][:8]}"
        )

        return await call_next(request)
