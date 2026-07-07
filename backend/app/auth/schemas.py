"""
Pydantic request/response schemas for auth endpoints.

Defines the RoleDTO enum with hierarchical ordering, request bodies for
registration, login, and token refresh, and response models for tokens
and user profiles.
"""


from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


# ── RoleDTO ─────────────────────────────────────────────────────────────────


class RoleDTO(str, Enum):
    """Role data transfer object with four hardcoded access levels.

    The hierarchy is: super_admin > admin > editor > viewer.
    Higher roles inherit all permissions of lower roles.
    """

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


# Hierarchy lookup — higher int means more privileges.
ROLE_HIERARCHY: dict[RoleDTO, int] = {
    RoleDTO.VIEWER: 0,
    RoleDTO.EDITOR: 1,
    RoleDTO.ADMIN: 2,
    RoleDTO.SUPER_ADMIN: 3,
}

# Shared mapping from RoleDTO to ORM UserRole — used by auth, settings,
# and dependencies modules to avoid duplication.
_ROLE_DTO_TO_ORM: dict[RoleDTO, UserRole] = {
    RoleDTO.SUPER_ADMIN: UserRole.SUPER_ADMIN,
    RoleDTO.ADMIN: UserRole.ADMIN,
    RoleDTO.EDITOR: UserRole.EDITOR,
    RoleDTO.VIEWER: UserRole.VIEWER,
}


# ── Request Schemas ─────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    """Request body for user login."""

    email: EmailStr
    password: str = Field(
        ...,
        min_length=1,
        description="Plain-text password attempt.",
    )


class RefreshRequest(BaseModel):
    """Request body for token refresh.

    The refresh token is now primarily read from an HttpOnly cookie.
    This field is retained for backward compatibility only.
    """

    refresh_token: str | None = Field(
        default=None,
        description="Deprecated: refresh token is now read from HttpOnly cookie.",
    )


# ── Response Schemas ────────────────────────────────────────────────────────


class ChangePasswordRequest(BaseModel):
    """Request body for changing password."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class TokenResponse(BaseModel):
    """Response containing access token (and optionally refresh token).

    In production the refresh_token is delivered via an HttpOnly cookie
    rather than in the JSON body — the field is retained for backward
    compatibility.
    """

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Response containing public user profile information."""

    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
