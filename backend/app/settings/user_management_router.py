"""
User management API router — list, invite, change role, deactivate users.

Mounts under ``/settings/users`` (prefixed by ``/api/v1`` in main.py) and
exposes endpoints restricted to ``super_admin`` role only.  Self-demotion
and deactivation of the last super_admin are prevented.
"""

from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func as sql_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.schemas import RoleDTO
from app.auth.user_service import UserService
from app.database import get_db
from app.models.user import User, UserRole
from app.settings.user_management_schemas import (
    ChangeRoleRequest,
    InviteUserRequest,
    UserActionResponse,
    UserListItem,
    UserListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/users", tags=["settings"])

# ── Singletons ──────────────────────────────────────────────────────────────

_user_service = UserService()

_ROLE_DTO_TO_ORM: dict[RoleDTO, UserRole] = {
    RoleDTO.SUPER_ADMIN: UserRole.SUPER_ADMIN,
    RoleDTO.ADMIN: UserRole.ADMIN,
    RoleDTO.EDITOR: UserRole.EDITOR,
    RoleDTO.VIEWER: UserRole.VIEWER,
}


# ── Helpers ─────────────────────────────────────────────────────────────────


def _generate_password(length: int = 16) -> str:
    """Generate a cryptographically secure random password for invited users."""
    return secrets.token_urlsafe(length)


async def _count_active_super_admins(db: AsyncSession) -> int:
    """Return the number of active super_admin users in the system."""
    result = await db.execute(
        select(sql_func.count()).select_from(User).where(
            User.role == UserRole.SUPER_ADMIN,
            User.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one()


# ── GET /settings/users ─────────────────────────────────────────────────────


@router.get(
    "",
    response_model=UserListResponse,
    summary="List all users with roles and status",
)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.SUPER_ADMIN))],
) -> UserListResponse:
    """Return a complete list of all registered users.

    Each entry includes id, email, role, is_active, and created_at.
    Only super_admin users may access this endpoint.
    """
    users = await _user_service.list_users(db)
    return UserListResponse(
        items=[UserListItem.model_validate(u) for u in users],
        total=len(users),
    )


# ── POST /settings/users/invite ─────────────────────────────────────────────


@router.post(
    "/invite",
    response_model=UserActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user with email and role",
)
async def invite_user(
    body: InviteUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.SUPER_ADMIN))],
) -> UserActionResponse:
    """Create a new user account with a specified email and role.

    A secure random password is generated server-side.  The invited user
    should be prompted to reset their password on first login (password
    reset flow to be implemented in a future version).

    Raises:
        HTTPException 409: If a user with the given email already exists.
    """
    orm_role = _ROLE_DTO_TO_ORM[body.role]

    try:
        user = await _user_service.create_user(
            db,
            email=body.email,
            password=_generate_password(),
            role=orm_role,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    logger.info(
        "Super admin id=%d invited user id=%d email=%r role=%s",
        current_user.id,
        user.id,
        user.email,
        body.role.value,
    )
    return UserActionResponse(
        message="User invited successfully.",
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
    )


# ── PUT /settings/users/{user_id}/role ──────────────────────────────────────


@router.put(
    "/{user_id}/role",
    response_model=UserActionResponse,
    summary="Change a user's role",
)
async def change_user_role(
    user_id: int,
    body: ChangeRoleRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.SUPER_ADMIN))],
) -> UserActionResponse:
    """Change the role of an existing user.

    The requesting super_admin **cannot demote themselves**.  Attempting
    to change your own role — even to a higher role — is blocked to
    prevent accidental lockouts.

    Raises:
        HTTPException 403: If the caller attempts to change their own role.
        HTTPException 404: If the target user does not exist.
    """
    # Guard: cannot change own role
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot change your own role.",
        )

    orm_role = _ROLE_DTO_TO_ORM[body.role]

    try:
        user = await _user_service.update_user(db, user_id, role=orm_role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    logger.info(
        "Super admin id=%d changed user id=%d role to %s",
        current_user.id,
        user_id,
        orm_role.value,
    )
    return UserActionResponse(
        message=f"User role updated to {orm_role.value}.",
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
    )


# ── PUT /settings/users/{user_id}/deactivate ────────────────────────────────


@router.put(
    "/{user_id}/deactivate",
    response_model=UserActionResponse,
    summary="Deactivate a user account",
)
async def deactivate_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.SUPER_ADMIN))],
) -> UserActionResponse:
    """Deactivate a user account (soft-delete).

    The requesting super_admin **cannot deactivate themselves**.
    Additionally, the **last active super_admin** cannot be deactivated to
    prevent total administrative lockout.

    Raises:
        HTTPException 403: If the caller attempts to deactivate themselves
                           or the last active super_admin.
        HTTPException 404: If the target user does not exist.
        HTTPException 409: If the user is already deactivated.
    """
    # Guard: cannot deactivate self
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot deactivate your own account.",
        )

    # Fetch target user first to check role before deactivating
    target_user = await _user_service.get_by_id(db, user_id)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id={user_id} not found.",
        )

    if not target_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already deactivated.",
        )

    # Guard: cannot deactivate last active super_admin
    if target_user.role == UserRole.SUPER_ADMIN:
        active_super_admin_count = await _count_active_super_admins(db)
        if active_super_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot deactivate the last active super_admin.",
            )

    try:
        user = await _user_service.deactivate_user(db, user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    logger.info(
        "Super admin id=%d deactivated user id=%d email=%r",
        current_user.id,
        user_id,
        user.email,
    )
    return UserActionResponse(
        message="User account deactivated.",
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
    )
