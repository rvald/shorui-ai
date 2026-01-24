"""
API Key service for authentication.

Handles API key generation, validation, and management.
Keys are stored as SHA-256 hashes in the database.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

import psycopg

from shorui_core.config import settings


class ApiKeyService:
    """Service for API key validation and management."""

    KEY_PREFIX = "shorui_"

    def __init__(self, dsn: str | None = None):
        """Initialize the API key service.

        Args:
            dsn: PostgreSQL connection string. Defaults to settings.POSTGRES_DSN.
        """
        self.dsn = dsn or settings.POSTGRES_DSN

    def _hash_key(self, raw_key: str) -> str:
        """Hash an API key using SHA-256.

        Args:
            raw_key: The raw API key string.

        Returns:
            Hexadecimal hash of the key.
        """
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def generate_key(self) -> tuple[str, str]:
        """Generate a new API key.

        Returns:
            Tuple of (raw_key, key_hash).
        """
        random_part = secrets.token_hex(32)
        raw_key = f"{self.KEY_PREFIX}{random_part}"
        return raw_key, self._hash_key(raw_key)

    def validate_key(self, raw_key: str) -> dict | None:
        """Validate an API key and return key record if valid.

        Args:
            raw_key: The raw API key from the request header.

        Returns:
            Key record dict with tenant_id, scopes, etc. or None if invalid.
        """
        key_hash = self._hash_key(raw_key)

        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT key_id, tenant_id, name, scopes, expires_at, is_active
                    FROM api_keys WHERE key_hash = %s
                    """,
                    (key_hash,),
                )
                row = cur.fetchone()

                if not row:
                    return None

                key_id, tenant_id, name, scopes, expires_at, is_active = row

                if not is_active:
                    return None

                if expires_at and expires_at < datetime.now(timezone.utc):
                    return None

                # Update last_used_at
                cur.execute(
                    "UPDATE api_keys SET last_used_at = NOW() WHERE key_id = %s",
                    (key_id,),
                )
                conn.commit()

                return {
                    "key_id": str(key_id),
                    "tenant_id": tenant_id,
                    "name": name,
                    "scopes": list(scopes) if scopes else [],
                }

    def create_key(
        self,
        tenant_id: str,
        scopes: list[str],
        name: str | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[str, str]:
        """Create a new API key for a tenant.

        Args:
            tenant_id: The tenant to create the key for.
            scopes: List of permission scopes.
            name: Optional human-readable name for the key.
            expires_at: Optional expiration datetime.

        Returns:
            Tuple of (raw_key, key_id). The raw_key is only returned once.
        """
        raw_key, key_hash = self.generate_key()
        key_prefix = raw_key[:12]
        key_id = str(uuid.uuid4())

        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO api_keys (key_id, key_hash, key_prefix, tenant_id, name, scopes, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (key_id, key_hash, key_prefix, tenant_id, name, scopes, expires_at),
                )
                conn.commit()

        return raw_key, key_id

    def revoke_key(self, key_id: str) -> bool:
        """Revoke an API key by setting is_active to False.

        Args:
            key_id: The key ID to revoke.

        Returns:
            True if key was revoked, False if not found.
        """
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE api_keys SET is_active = FALSE WHERE key_id = %s",
                    (key_id,),
                )
                conn.commit()
                return cur.rowcount > 0

    def list_keys(self, tenant_id: str) -> list[dict]:
        """List all API keys for a tenant (without hashes).

        Args:
            tenant_id: The tenant to list keys for.

        Returns:
            List of key records (excluding sensitive hash).
        """
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT key_id, key_prefix, name, scopes, created_at, expires_at, last_used_at, is_active
                    FROM api_keys WHERE tenant_id = %s
                    ORDER BY created_at DESC
                    """,
                    (tenant_id,),
                )
                rows = cur.fetchall()

                return [
                    {
                        "key_id": str(row[0]),
                        "key_prefix": row[1],
                        "name": row[2],
                        "scopes": list(row[3]) if row[3] else [],
                        "created_at": row[4].isoformat() if row[4] else None,
                        "expires_at": row[5].isoformat() if row[5] else None,
                        "last_used_at": row[6].isoformat() if row[6] else None,
                        "is_active": row[7],
                    }
                    for row in rows
                ]
