"""
Pydantic request/response schemas for auth endpoints.

Defines the RoleDTO enum with hierarchical ordering, request bodies for
registration, login, and token refresh, and response models for tokens
and user profiles.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


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


# ── Request Schemas ─────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """Request body for user registration.

    The email must be unique across the system. Password must be at least
    8 characters. Role defaults to VIEWER when not specified.
    """

    email: EmailStr
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Plain-text password (8–128 characters).",
    )
    role: RoleDTO = Field(
        default=RoleDTO.VIEWER,
        description="Access role for the new account.",
    )


class LoginRequest(BaseModel):
    """Request body for user login."""

    email: EmailStr
    password: str = Field(
        ...,
        min_length=1,
        description="Plain-text password attempt.",
    )


class RefreshRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str = Field(
        ...,
        min_length=1,
        description="A previously issued refresh token.",
    )


# ── Response Schemas ────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    """Response containing access and refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Response containing public user profile information."""

    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
