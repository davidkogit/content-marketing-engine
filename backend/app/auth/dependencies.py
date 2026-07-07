"""
FastAPI dependencies for authentication and role-based access control.

Provides ``get_current_user`` — extracts and validates JWTs from the
Authorization header — and ``require_role`` — a dependency factory that
enforces minimum role level on endpoints. Both raise appropriate HTTP
exceptions (401 Unauthorized, 403 Forbidden) when checks fail.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_service import JWTService, TokenExpiredError, TokenInvalidError
from app.auth.schemas import ROLE_HIERARCHY, _ROLE_DTO_TO_ORM, RoleDTO
from app.auth.user_service import UserService
from app.config import settings
from app.database import get_db
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)
"""Bearer scheme that does NOT auto-raise — we control the error response."""

_jwt_service = JWTService(access_token_expiry_minutes=settings.JWT_EXPIRY_MINUTES)
"""Module-level JWT service singleton — wired to configured expiry."""

_user_service = UserService()
"""Module-level user service singleton."""

# Reverse mapping derived from the shared _ROLE_DTO_TO_ORM in schemas.
_ORM_TO_ROLE_DTO: dict[UserRole, RoleDTO] = {
    v: k for k, v in _ROLE_DTO_TO_ORM.items()
}
"""Fast lookup from ORM UserRole enum to RoleDTO."""


# ── Helpers ─────────────────────────────────────────────────────────────────


def _map_role(role: UserRole) -> RoleDTO:
    """Map a UserRole ORM enum value to its corresponding RoleDTO."""
    return _ORM_TO_ROLE_DTO[role]


# ── get_current_user ────────────────────────────────────────────────────────


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ] = None,
) -> User:
    """Extract and validate the JWT from the Authorization header.

    Decodes the Bearer token, verifies its signature and expiry, looks up
    the user in the database, and confirms the account is active.

    Args:
        credentials: The parsed ``Authorization: Bearer <token>`` value,
                     or ``None`` if the header is absent.
        db: The per-request database session.

    Returns:
        The authenticated ``User`` ORM instance.

    Raises:
        HTTPException 401: If no credentials, token is expired/invalid,
                           user not found, or account deactivated.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide an Authorization header with a Bearer token.",
        )

    token: str = credentials.credentials

    try:
        payload: dict = await _jwt_service.decode_token(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        )
    except TokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid.",
        )

    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing user_id claim.",
        )

    user = await _user_service.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated.",
        )

    logger.debug("Authenticated user id=%d role=%s", user.id, user.role.value)
    return user


# ── require_role ────────────────────────────────────────────────────────────


def require_role(minimum_role: RoleDTO):
    """Create a FastAPI dependency that enforces a minimum role level.

    Uses the ``ROLE_HIERARCHY`` mapping to compare the current user's
    role against *minimum_role*. Higher-level roles (e.g. SUPER_ADMIN)
    automatically satisfy lower-level requirements.

    Usage::

        from app.auth.schemas import RoleDTO

        @router.get("/admin")
        async def admin_only(
            user: User = Depends(require_role(RoleDTO.ADMIN)),
        ):
            ...

    Args:
        minimum_role: The lowest ``RoleDTO`` allowed on the endpoint.

    Returns:
        An async FastAPI dependency that either returns the ``User`` or
        raises ``HTTPException 403``.
    """

    async def role_enforcer(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        user_dto = _map_role(current_user.role)
        required_level = ROLE_HIERARCHY[minimum_role]
        user_level = ROLE_HIERARCHY[user_dto]

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient permissions. "
                    f"Required role: {minimum_role.value} or higher."
                ),
            )

        return current_user

    return role_enforcer
