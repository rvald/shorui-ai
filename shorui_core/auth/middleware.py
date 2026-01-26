"""
FastAPI auth middleware.

Authenticates requests via X-API-Key header or Authorization Bearer token,
and attaches AuthContext to request.state.
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
        "/metrics",
        # Auth endpoints are public (except /auth/me and /auth/logout)
        "/auth/register",
        "/auth/login",
        "/auth/refresh",
        "/test-limit",
    }
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to authenticate requests via API key or JWT.

    Authentication priority:
    1. X-API-Key header (for service-to-service)
    2. Authorization: Bearer {jwt} header (for user sessions)

    When enabled (require_auth=True), all requests to non-public paths
    must include valid credentials. The derived tenant_id and
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
        self._jwt_service = None  # Lazy init to avoid circular imports

    @property
    def api_key_service(self) -> ApiKeyService:
        """Lazily initialize API key service to avoid import-time DB connections."""
        if self._api_key_service is None:
            self._api_key_service = ApiKeyService()
        return self._api_key_service

    @property
    def jwt_service(self):
        """Lazily initialize JWT service to avoid import-time issues."""
        if self._jwt_service is None:
            from shorui_core.auth.jwt_service import JwtService
            from shorui_core.config import settings

            if settings.JWT_SECRET:
                self._jwt_service = JwtService()
            else:
                self._jwt_service = None
        return self._jwt_service

    def _try_api_key_auth(self, request: Request, request_id: str) -> AuthContext | None:
        """Try to authenticate via API key."""
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return None

        try:
            key_record = self.api_key_service.validate_key(api_key)
        except Exception as e:
            logger.error(f"[{request_id}] API key validation error: {e}")
            return None

        if not key_record:
            return None

        return AuthContext(
            principal=Principal(
                tenant_id=key_record["tenant_id"],
                key_id=key_record["key_id"],
                key_name=key_record["name"],
                scopes=frozenset(key_record["scopes"]),
            ),
            authenticated_at=datetime.now(timezone.utc),
            request_id=request_id,
        )

    def _try_bearer_auth(self, request: Request, request_id: str) -> AuthContext | None:
        """Try to authenticate via Bearer JWT token."""
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        if not self.jwt_service:
            logger.debug(f"[{request_id}] JWT service not configured")
            return None

        token = auth_header[7:]  # Strip "Bearer "

        try:
            payload = self.jwt_service.verify_access_token(token)
        except Exception as e:
            logger.error(f"[{request_id}] JWT verification error: {e}")
            return None

        if not payload:
            return None

        return AuthContext(
            principal=Principal(
                tenant_id=payload["tenant_id"],
                key_id=f"user:{payload['sub']}",
                key_name=payload["email"],
                scopes=frozenset(payload.get("scopes", [])),
            ),
            authenticated_at=datetime.now(timezone.utc),
            request_id=request_id,
        )

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

        # Try authentication methods in priority order
        # 1. API Key (service-to-service)
        auth_context = self._try_api_key_auth(request, request_id)

        # 2. Bearer JWT (user sessions)
        if not auth_context:
            auth_context = self._try_bearer_auth(request, request_id)

        # No valid auth found
        if not auth_context:
            # Check what was provided to give appropriate error
            if request.headers.get("X-API-Key"):
                logger.warning(f"[{request_id}] Invalid API key for {path}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired API key"},
                )
            elif request.headers.get("Authorization"):
                logger.warning(f"[{request_id}] Invalid Bearer token for {path}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"},
                )
            else:
                logger.warning(f"[{request_id}] Missing auth credentials for {path}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"},
                )

        # Attach auth context to request
        request.state.auth = auth_context

        logger.debug(
            f"[{request_id}] Authenticated: tenant={auth_context.tenant_id} "
            f"key={auth_context.principal.key_name or auth_context.principal.key_id[:8]}"
        )

        return await call_next(request)

