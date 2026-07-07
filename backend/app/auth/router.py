"""
Auth API router — registration, login, token refresh, and profile endpoints.

Mounts under ``/auth`` and exposes:
- ``POST /auth/register`` — create account, get tokens
- ``POST /auth/login`` — authenticate, get tokens
- ``GET  /auth/me`` — current user profile
- ``POST /auth/refresh`` — exchange refresh token for new pair
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.hashing import verify_password
from app.auth.jwt_service import JWTService, TokenExpiredError, TokenInvalidError
from app.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RoleDTO,
    TokenResponse,
    UserResponse,
)
from app.auth.user_service import UserService
from app.database import get_db
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Singletons ──────────────────────────────────────────────────────────────

_jwt_service = JWTService()
_user_service = UserService()

_ROLE_DTO_TO_ORM: dict[RoleDTO, UserRole] = {
    RoleDTO.SUPER_ADMIN: UserRole.SUPER_ADMIN,
    RoleDTO.ADMIN: UserRole.ADMIN,
    RoleDTO.EDITOR: UserRole.EDITOR,
    RoleDTO.VIEWER: UserRole.VIEWER,
}


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _issue_token_pair(user: User) -> TokenResponse:
    """Create and return a new access + refresh token pair for *user*."""
    access_token = await _jwt_service.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )
    refresh_token = await _jwt_service.create_refresh_token(user_id=user.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ── POST /auth/register ─────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Create a new user account and return access + refresh tokens.

    The email must be unique across all accounts. Password must be at
    least 8 characters. New accounts default to the VIEWER role unless
    another role is explicitly requested.

    Returns:
        A ``TokenResponse`` containing access and refresh tokens.

    Raises:
        HTTPException 409: If the email is already registered.
    """
    orm_role = _ROLE_DTO_TO_ORM[body.role]

    try:
        user = await _user_service.create_user(
            db,
            email=body.email,
            password=body.password,
            role=orm_role,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    logger.info("Registered new user id=%d email=%r", user.id, user.email)
    return await _issue_token_pair(user)


# ── POST /auth/login ────────────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in with email and password",
)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate with email and password, returning tokens on success.

    Uses constant-time bcrypt comparison to verify the password.
    Deactivated accounts receive a 401 even with correct credentials.

    Returns:
        A ``TokenResponse`` with access and refresh tokens.

    Raises:
        HTTPException 401: If email not found, password incorrect, or
                           account deactivated.
    """
    user = await _user_service.get_by_email(db, body.email)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated.",
        )

    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    logger.info("User id=%d logged in", user.id)
    return await _issue_token_pair(user)


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
async def refresh_tokens(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair.

    The incoming refresh token is verified, and the associated user is
    confirmed to still exist and be active. A fresh token pair is then
    issued.  The old refresh token is **not** explicitly blacklisted in
    this v1 implementation — future versions may add a token blacklist
    table for immediate revocation.

    Returns:
        A ``TokenResponse`` with new access and refresh tokens.

    Raises:
        HTTPException 401: If refresh token is expired, invalid, not a
                           refresh-type token, or the user is not found
                           / deactivated.
    """
    # ── Decode and validate the refresh token ──────────────────────────────
    try:
        payload = await _jwt_service.decode_token(body.refresh_token)
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
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated.",
        )

    logger.info("Refreshed tokens for user id=%d", user.id)
    return await _issue_token_pair(user)
