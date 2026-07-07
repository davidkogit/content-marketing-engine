"""
Pydantic request/response schemas for user management endpoints.

Defines schemas for listing users, inviting new users, changing roles,
and deactivating accounts — all restricted to the SUPER_ADMIN role.
"""


from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.auth.schemas import RoleDTO


# ── Request Schemas ─────────────────────────────────────────────────────────


class InviteUserRequest(BaseModel):
    """Request body for creating (inviting) a new user.

    Email and role are required. An initial password is auto-generated
    server-side — the invited user must reset it on first login.
    """

    email: EmailStr = Field(
        ...,
        description="Email address for the new user account.",
    )
    role: RoleDTO = Field(
        ...,
        description="Access role for the new account.",
    )


class ChangeRoleRequest(BaseModel):
    """Request body for changing a user's role."""

    role: RoleDTO = Field(
        ...,
        description="The new role to assign to the user.",
    )


# ── Response Schemas ────────────────────────────────────────────────────────


class UserListItem(BaseModel):
    """Lightweight user representation for the user list view."""

    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Paginated response wrapper for the user list."""

    items: list[UserListItem]
    total: int


class UserActionResponse(BaseModel):
    """Generic response for user management actions (role change, deactivation)."""

    message: str
    user_id: int
    email: str
    role: str
    is_active: bool
