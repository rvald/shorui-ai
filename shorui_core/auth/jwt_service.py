"""
JWT service for token generation and validation.

Handles access token (short-lived) and refresh token (long-lived) operations.
Refresh tokens are stored hashed in the database to enable revocation.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import TypedDict

import jwt
import psycopg

from shorui_core.config import settings


class TokenPayload(TypedDict):
    """Decoded JWT payload."""

    sub: str  # user_id
    tenant_id: str
    email: str
    role: str
    scopes: list[str]
    iat: int
    exp: int


class JwtService:
    """Service for JWT token generation and validation."""

    ALGORITHM = "HS256"

    def __init__(self, dsn: str | None = None, secret: str | None = None):
        """Initialize the JWT service.

        Args:
            dsn: PostgreSQL connection string. Defaults to settings.POSTGRES_DSN.
            secret: JWT signing secret. Defaults to settings.JWT_SECRET.
        """
        self.dsn = dsn or settings.POSTGRES_DSN
        self.secret = secret or settings.JWT_SECRET
        self.access_ttl = getattr(settings, "JWT_ACCESS_TTL", 900)  # 15 minutes
        self.refresh_ttl = getattr(settings, "JWT_REFRESH_TTL", 86400)  # 1 day

        if not self.secret:
            raise ValueError("JWT_SECRET must be configured")

    def _hash_token(self, token: str) -> str:
        """Hash a token using SHA-256.

        Args:
            token: Raw token string.

        Returns:
            Hexadecimal hash of the token.
        """
        return hashlib.sha256(token.encode()).hexdigest()

    def create_access_token(
        self,
        user_id: str,
        tenant_id: str,
        email: str,
        role: str = "user",
        scopes: list[str] | None = None,
    ) -> str:
        """Create a short-lived access token.

        Args:
            user_id: The user's UUID.
            tenant_id: The tenant ID.
            email: User's email.
            role: User's role (default: "user").
            scopes: Permission scopes.

        Returns:
            Encoded JWT string.
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "email": email,
            "role": role,
            "scopes": scopes or ["ingest:write", "rag:read", "compliance:read"],
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self.access_ttl)).timestamp()),
        }
        return jwt.encode(payload, self.secret, algorithm=self.ALGORITHM)

    def verify_access_token(self, token: str) -> TokenPayload | None:
        """Verify and decode an access token.

        Args:
            token: The JWT string.

        Returns:
            Decoded payload if valid, None otherwise.
        """
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.ALGORITHM])
            return TokenPayload(
                sub=payload["sub"],
                tenant_id=payload["tenant_id"],
                email=payload["email"],
                role=payload["role"],
                scopes=payload.get("scopes", []),
                iat=payload["iat"],
                exp=payload["exp"],
            )
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def create_refresh_token(self, user_id: str) -> str:
        """Create a long-lived refresh token.

        The token is stored hashed in the database and can be revoked.

        Args:
            user_id: The user's UUID.

        Returns:
            Raw refresh token string.
        """
        raw_token = secrets.token_urlsafe(64)
        token_hash = self._hash_token(raw_token)
        token_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.refresh_ttl)

        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO refresh_tokens (token_id, user_id, token_hash, expires_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (token_id, user_id, token_hash, expires_at),
                )
                conn.commit()

        return raw_token

    def verify_refresh_token(self, raw_token: str) -> str | None:
        """Verify a refresh token and return the user_id.

        Args:
            raw_token: The raw refresh token string.

        Returns:
            user_id if valid, None otherwise.
        """
        token_hash = self._hash_token(raw_token)

        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, expires_at, revoked_at
                    FROM refresh_tokens WHERE token_hash = %s
                    """,
                    (token_hash,),
                )
                row = cur.fetchone()

                if not row:
                    return None

                user_id, expires_at, revoked_at = row

                # Check if revoked
                if revoked_at is not None:
                    return None

                # Check if expired
                if expires_at < datetime.now(timezone.utc):
                    return None

                return str(user_id)

    def revoke_refresh_token(self, raw_token: str) -> bool:
        """Revoke a refresh token.

        Args:
            raw_token: The raw refresh token string.

        Returns:
            True if token was revoked, False if not found.
        """
        token_hash = self._hash_token(raw_token)

        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE refresh_tokens SET revoked_at = NOW()
                    WHERE token_hash = %s AND revoked_at IS NULL
                    """,
                    (token_hash,),
                )
                conn.commit()
                return cur.rowcount > 0

    def revoke_all_for_user(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user.

        Used on logout to invalidate all sessions.

        Args:
            user_id: The user's UUID.

        Returns:
            Number of tokens revoked.
        """
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE refresh_tokens SET revoked_at = NOW()
                    WHERE user_id = %s AND revoked_at IS NULL
                    """,
                    (user_id,),
                )
                conn.commit()
                return cur.rowcount
