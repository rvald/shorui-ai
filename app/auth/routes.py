"""
Authentication routes for user login flow.

Provides endpoints for:
- User registration (self-service)
- Login (email/password → JWT + cookie)
- Token refresh (via HttpOnly cookie)
- Logout (revoke all tokens + agent sessions)
- Current user info
"""



from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, Body
from pydantic import BaseModel, EmailStr, Field

from shorui_core.auth import get_auth_context
from shorui_core.auth.user_service import UserService
from shorui_core.auth.jwt_service import JwtService
from shorui_core.config import settings
from shorui_core.domain.auth import AuthContext
from shorui_core.infrastructure.rate_limiter import limiter
from slowapi.util import get_remote_address


router = APIRouter(prefix="/auth", tags=["auth"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(..., min_length=8)
    tenant_name: str = Field(..., min_length=1, max_length=255)


class RegisterResponse(BaseModel):
    """User registration response."""

    user_id: str
    email: str
    tenant_id: str


class LoginRequest(BaseModel):
    """Login request."""

    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Login response."""

    access_token: str
    expires_in: int
    user: dict


class RefreshResponse(BaseModel):
    """Token refresh response."""

    access_token: str
    expires_in: int


class LogoutResponse(BaseModel):
    """Logout response."""

    message: str


class UserResponse(BaseModel):
    """Current user response."""

    user_id: str
    email: str
    tenant_id: str
    role: str


# =============================================================================
# Service Factories
# =============================================================================


def get_user_service() -> UserService:
    """Get user service instance."""
    return UserService()


def get_jwt_service() -> JwtService:
    """Get JWT service instance."""
    return JwtService()


# =============================================================================
# Routes
# =============================================================================


@router.post("/register", response_model=RegisterResponse, status_code=201)
@limiter.limit("5/minute")
async def register(
    request: Request,
    register_request: RegisterRequest = Body(...),
    user_service: UserService = Depends(get_user_service),
):
    """Register a new user.

    Creates a new tenant if the tenant_name is new. User must login
    separately after registration.
    """
    try:
        user = user_service.register(
            email=register_request.email,
            password=register_request.password,
            tenant_name=register_request.tenant_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        if "already registered" in str(e):
            raise HTTPException(status_code=409, detail="Email already registered")
        raise HTTPException(status_code=500, detail="Registration failed")

    return RegisterResponse(
        user_id=user["user_id"],
        email=user["email"],
        tenant_id=user["tenant_id"],
    )


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    login_request: LoginRequest = Body(...),
    user_service: UserService = Depends(get_user_service),
    jwt_service: JwtService = Depends(get_jwt_service),
):
    """Authenticate user and return tokens.

    Returns access token in response body and sets refresh token
    as HttpOnly cookie.
    """
    user = user_service.authenticate(login_request.email, login_request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Create tokens
    access_token = jwt_service.create_access_token(
        user_id=user["user_id"],
        tenant_id=user["tenant_id"],
        email=user["email"],
        role=user["role"],
    )
    refresh_token = jwt_service.create_refresh_token(user["user_id"])

    # Set refresh token as HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,  # Requires HTTPS in production
        samesite="strict",
        max_age=settings.JWT_REFRESH_TTL,
        path="/auth",  # Only sent to auth endpoints
    )

    return LoginResponse(
        access_token=access_token,
        expires_in=settings.JWT_ACCESS_TTL,
        user={
            "user_id": user["user_id"],
            "email": user["email"],
            "tenant_id": user["tenant_id"],
            "role": user["role"],
        },
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
    user_service: UserService = Depends(get_user_service),
    jwt_service: JwtService = Depends(get_jwt_service),
):
    """Refresh access token using refresh cookie.

    Returns new access token. Does not rotate refresh token.
    """
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token required")

    # Verify refresh token
    user_id = jwt_service.verify_refresh_token(refresh_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Get user info for new access token
    user = user_service.get_by_id(user_id)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Create new access token
    access_token = jwt_service.create_access_token(
        user_id=user["user_id"],
        tenant_id=user["tenant_id"],
        email=user["email"],
        role=user["role"],
    )

    return RefreshResponse(
        access_token=access_token,
        expires_in=settings.JWT_ACCESS_TTL,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    refresh_token: Annotated[str | None, Cookie()] = None,
    jwt_service: JwtService = Depends(get_jwt_service),
):
    """Logout and revoke all tokens.

    Revokes the refresh token and clears the cookie.
    Also invalidates any active agent sessions for the user.
    """
    # Revoke refresh token if present
    if refresh_token:
        jwt_service.revoke_refresh_token(refresh_token)

    # Extract user_id from auth context (for JWT auth, key_id is "user:{uuid}")
    if auth.principal.key_id.startswith("user:"):
        user_id = auth.principal.key_id[5:]
        # Revoke all refresh tokens for user
        jwt_service.revoke_all_for_user(user_id)

        # Invalidate agent sessions for user
        try:
            from app.agent.routes import get_service as get_agent_service
            agent_service = get_agent_service()
            await agent_service.invalidate_user_sessions(user_id)
        except Exception as e:
            # Don't fail logout if agent service is unavailable
            from loguru import logger
            logger.error(f"Failed to invalidate agent sessions for {user_id}: {e}")

    # Clear refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        path="/auth",
        httponly=True,
        secure=True,
        samesite="strict",
    )

    return LogoutResponse(message="Logged out successfully")


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    auth: AuthContext = Depends(get_auth_context),
    user_service: UserService = Depends(get_user_service),
):
    """Get current authenticated user.

    Requires Bearer token authentication.
    """
    # For JWT auth, extract user_id from principal
    if not auth.principal.key_id.startswith("user:"):
        raise HTTPException(
            status_code=400,
            detail="This endpoint requires user authentication, not API key",
        )

    user_id = auth.principal.key_id[5:]
    user = user_service.get_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        user_id=user["user_id"],
        email=user["email"],
        tenant_id=user["tenant_id"],
        role=user["role"],
    )
