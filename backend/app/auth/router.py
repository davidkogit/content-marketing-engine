"""
Auth API router — login, token refresh, logout, and profile endpoints.

Mounts under ``/auth`` and exposes:
- ``POST /auth/login`` — authenticate, get access token + HttpOnly refresh cookie
- ``GET  /auth/me`` — current user profile
- ``POST /auth/refresh`` — exchange refresh cookie for new access token + cookie
- ``POST /auth/logout`` — clear the refresh cookie

Self-registration is disabled.  All accounts must be created via the
Super Admin invite flow at ``POST /settings/users/invite``.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.hashing import verify_password
from app.auth.jwt_service import JWTService, TokenExpiredError, TokenInvalidError
from app.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from app.auth.user_service import UserService
from app.database import get_db
from app.models.user import User
from app.config import settings
from app.rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Singletons ──────────────────────────────────────────────────────────────

_jwt_service = JWTService()
_user_service = UserService()

# ── Cookie constants ────────────────────────────────────────────────────────

_REFRESH_COOKIE_KEY = "refresh_token"
_REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"
_REFRESH_COOKIE_MAX_AGE = 604800  # 7 days in seconds


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _issue_token_pair(user: User) -> TokenResponse:
    """Create and return a new access + refresh token pair for *user*."""
    access_token = await _jwt_service.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )
    refresh_token = await _jwt_service.create_refresh_token(
        user_id=user.id,
        token_version=user.token_version,
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Attach the refresh token as an HttpOnly, SameSite=Strict cookie.

    The Secure flag is controlled by the SECURE_COOKIES setting —
    disabled when running on plain HTTP (e.g. IP-only deployments).
    """
    response.set_cookie(
        key=_REFRESH_COOKIE_KEY,
        value=token,
        httponly=True,
        secure=settings.SECURE_COOKIES,
        samesite="strict",
        path=_REFRESH_COOKIE_PATH,
        max_age=_REFRESH_COOKIE_MAX_AGE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Remove the refresh token cookie."""
    response.delete_cookie(key=_REFRESH_COOKIE_KEY, path=_REFRESH_COOKIE_PATH)


# ── POST /auth/login ────────────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in with email and password",
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
) -> TokenResponse:
    """Authenticate with email and password, returning an access token + HttpOnly refresh cookie.

    Uses constant-time bcrypt comparison to verify the password.
    A uniform error message is returned for all failure cases (unknown
    email, wrong password, deactivated account) to prevent account
    enumeration.

    Returns:
        A ``TokenResponse`` with the access token.  The refresh token is
        set as an HttpOnly cookie.

    Raises:
        HTTPException 401: On any authentication failure — always the same
                           "Invalid email or password." message.
    """
    user = await _user_service.get_by_email(db, body.email)

    # Always return the same error for non-existent users, deactivated
    # accounts, and wrong passwords to prevent account enumeration.
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    logger.info("User id=%d logged in", user.id)

    token_pair = await _issue_token_pair(user)
    _set_refresh_cookie(response, token_pair.refresh_token)
    return TokenResponse(access_token=token_pair.access_token)


# ── GET /auth/me ────────────────────────────────────────────────────────────


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return the authenticated user's profile information.

    Extracts the user from the JWT in the ``Authorization`` header.
    No additional database lookup is needed — the dependency already
    loaded the full user object.

    Returns:
        A ``UserResponse`` with id, email, role, is_active, and created_at.

    Raises:
        HTTPException 401: If token is missing, expired, or invalid.
    """
    return UserResponse.model_validate(current_user)


# ── POST /auth/refresh ──────────────────────────────────────────────────────


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
)
@limiter.limit("5/minute")
async def refresh_tokens(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    body: RefreshRequest | None = None,
) -> TokenResponse:
    """Exchange a valid refresh token (from HttpOnly cookie) for a new access token.

    The refresh token is read from the ``refresh_token`` HttpOnly cookie.
    On success the access token is returned in the response body and a
    **new** refresh token is set as an HttpOnly cookie.  All prior
    refresh tokens for this user are invalidated via ``token_version``
    increment.

    Returns:
        A ``TokenResponse`` with the new access token.

    Raises:
        HTTPException 401: If the cookie is absent, the token is expired,
                           invalid, or the user is not found / deactivated.
    """
    # ── Extract refresh token from HttpOnly cookie ─────────────────────────
    refresh_token: str | None = request.cookies.get(_REFRESH_COOKIE_KEY)

    # Fallback to request body for backward compatibility
    if not refresh_token and body and body.refresh_token:
        refresh_token = body.refresh_token

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is missing.",
        )

    # ── Decode and validate the refresh token ──────────────────────────────
    try:
        payload = await _jwt_service.decode_token(refresh_token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired.",
        )
    except TokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid.",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not a refresh token.",
        )

    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing user_id claim.",
        )

    # ── Verify user still exists and is active ─────────────────────────────
    user = await _user_service.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated.",
        )

    # ── Check token_version to detect invalidated tokens ───────────────────
    claim_version: int = payload.get("token_version", 0)
    if claim_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been invalidated (token version mismatch).",
        )

    # ── Increment token_version to invalidate all prior refresh tokens ─────
    user.token_version += 1
    await db.commit()

    logger.info("Refreshed tokens for user id=%d (version=%d)", user.id, user.token_version)

    token_pair = await _issue_token_pair(user)
    _set_refresh_cookie(response, token_pair.refresh_token)
    return TokenResponse(access_token=token_pair.access_token)


# ── POST /auth/logout ────────────────────────────────────────────────────────


@router.post(
    "/logout",
    summary="Log out and clear refresh token cookie",
)
async def logout(
    response: Response,
) -> dict[str, str]:
    """Clear the refresh token HttpOnly cookie.

    The access token (stored in-memory on the frontend) will be discarded
    by the client.  The refresh cookie is removed so no new tokens can be
    obtained without re-authentication.
    """
    _clear_refresh_cookie(response)
    logger.info("User logged out — refresh cookie cleared")
    return {"message": "Logged out successfully."}
