"""
User service for email/password authentication.

Handles user registration, authentication, and management.
Passwords are hashed using bcrypt with cost factor 12.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import TypedDict

import bcrypt
import psycopg

from shorui_core.config import settings


class UserRecord(TypedDict):
    """User record from database."""

    user_id: str
    tenant_id: str
    email: str
    role: str
    created_at: str
    last_login_at: str | None
    is_active: bool


class UserService:
    """Service for user authentication and management."""

    BCRYPT_COST = 12
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

    def __init__(self, dsn: str | None = None):
        """Initialize the user service.

        Args:
            dsn: PostgreSQL connection string. Defaults to settings.POSTGRES_DSN.
        """
        self.dsn = dsn or settings.POSTGRES_DSN

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt.

        Args:
            password: Plain text password.

        Returns:
            Bcrypt hash string.
        """
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(self.BCRYPT_COST)).decode()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash.

        Args:
            password: Plain text password.
            password_hash: Stored bcrypt hash.

        Returns:
            True if password matches.
        """
        return bcrypt.checkpw(password.encode(), password_hash.encode())

    def _validate_email(self, email: str) -> bool:
        """Validate email format.

        Args:
            email: Email address to validate.

        Returns:
            True if email format is valid.
        """
        return bool(self.EMAIL_PATTERN.match(email))

    def _validate_password(self, password: str) -> tuple[bool, str | None]:
        """Validate password strength.

        Args:
            password: Password to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters"
        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"
        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"
        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit"
        return True, None

    def _generate_tenant_id(self, tenant_name: str) -> str:
        """Generate a tenant_id from tenant name.

        Args:
            tenant_name: Human-readable tenant name.

        Returns:
            URL-safe tenant_id.
        """
        # Convert to lowercase, replace spaces with hyphens, remove special chars
        base = re.sub(r"[^a-z0-9-]", "", tenant_name.lower().replace(" ", "-"))
        # Truncate and add uniqueness suffix
        base = base[:50] if len(base) > 50 else base
        suffix = hashlib.sha256(f"{base}{datetime.now().isoformat()}".encode()).hexdigest()[:8]
        return f"{base}-{suffix}" if base else suffix

    def register(
        self,
        email: str,
        password: str,
        tenant_name: str,
    ) -> UserRecord:
        """Register a new user.

        Creates a new tenant if tenant_name is new. The user is assigned to
        the tenant and can immediately log in.

        Args:
            email: User's email address.
            password: Plain text password (will be hashed).
            tenant_name: Name of the organization/tenant.

        Returns:
            UserRecord with user details.

        Raises:
            ValueError: If email format is invalid or password is weak.
            RuntimeError: If email already exists.
        """
        # Validate inputs
        if not self._validate_email(email):
            raise ValueError("Invalid email format")

        is_valid, error = self._validate_password(password)
        if not is_valid:
            raise ValueError(error)

        # Hash password
        password_hash = self._hash_password(password)
        user_id = str(uuid.uuid4())

        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                # Check if email already exists
                cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
                if cur.fetchone():
                    raise RuntimeError("Email already registered")

                # Check if tenant exists, create if not
                cur.execute("SELECT tenant_id FROM tenants WHERE name = %s", (tenant_name,))
                row = cur.fetchone()
                if row:
                    tenant_id = row[0]
                else:
                    tenant_id = self._generate_tenant_id(tenant_name)
                    cur.execute(
                        "INSERT INTO tenants (tenant_id, name) VALUES (%s, %s)",
                        (tenant_id, tenant_name),
                    )

                # Create user
                cur.execute(
                    """
                    INSERT INTO users (user_id, tenant_id, email, password_hash)
                    VALUES (%s, %s, %s, %s)
                    RETURNING created_at
                    """,
                    (user_id, tenant_id, email, password_hash),
                )
                created_at = cur.fetchone()[0]
                conn.commit()

        return UserRecord(
            user_id=user_id,
            tenant_id=tenant_id,
            email=email,
            role="user",
            created_at=created_at.isoformat(),
            last_login_at=None,
            is_active=True,
        )

    def authenticate(self, email: str, password: str) -> UserRecord | None:
        """Authenticate a user by email and password.

        Args:
            email: User's email address.
            password: Plain text password.

        Returns:
            UserRecord if authentication succeeds, None otherwise.
        """
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, tenant_id, email, password_hash, role,
                           created_at, last_login_at, is_active
                    FROM users WHERE email = %s
                    """,
                    (email,),
                )
                row = cur.fetchone()

                if not row:
                    return None

                (
                    user_id,
                    tenant_id,
                    db_email,
                    password_hash,
                    role,
                    created_at,
                    last_login_at,
                    is_active,
                ) = row

                if not is_active:
                    return None

                if not self._verify_password(password, password_hash):
                    return None

                # Update last_login_at
                cur.execute(
                    "UPDATE users SET last_login_at = NOW() WHERE user_id = %s",
                    (user_id,),
                )
                conn.commit()

                return UserRecord(
                    user_id=str(user_id),
                    tenant_id=tenant_id,
                    email=db_email,
                    role=role,
                    created_at=created_at.isoformat() if created_at else None,
                    last_login_at=datetime.now(timezone.utc).isoformat(),
                    is_active=is_active,
                )

    def get_by_id(self, user_id: str) -> UserRecord | None:
        """Get a user by their ID.

        Args:
            user_id: The user's UUID.

        Returns:
            UserRecord if found, None otherwise.
        """
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, tenant_id, email, role,
                           created_at, last_login_at, is_active
                    FROM users WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()

                if not row:
                    return None

                return UserRecord(
                    user_id=str(row[0]),
                    tenant_id=row[1],
                    email=row[2],
                    role=row[3],
                    created_at=row[4].isoformat() if row[4] else None,
                    last_login_at=row[5].isoformat() if row[5] else None,
                    is_active=row[6],
                )
