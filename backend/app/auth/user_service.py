"""
User service layer — async CRUD operations with role validation and password hashing.

Provides a UserService class whose methods accept a database session via
dependency injection, keeping callers in control of transaction boundaries.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.hashing import hash_password
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

_VALID_ROLE_VALUES: set[str] = {role.value for role in UserRole}


# ── UserService ────────────────────────────────────────────────────────────


class UserService:
    """Async service for user CRUD operations.

    All methods accept ``db`` as the first positional argument (dependency
    injection) so that callers control session lifecycle and transaction
    boundaries.

    Usage:
        service = UserService()

        user = await service.create_user(db, email, password, role=UserRole.EDITOR)
        found = await service.get_by_email(db, "someone@example.com")
    """

    # ── Create ──────────────────────────────────────────────────────────────

    async def create_user(
        self,
        db: AsyncSession,
        email: str,
        password: str,
        role: UserRole = UserRole.VIEWER,
        is_active: bool = True,
    ) -> User:
        """Create a new user with hashed password and validated role.

        Checks email uniqueness before inserting and hashes the password
        with bcrypt (via ``hash_password``) prior to storage.

        Args:
            db: Active database session.
            email: User's email address (must be unique, case-sensitive).
            password: Plain-text password — never stored or logged as-is.
            role: UserRole enum value. Defaults to VIEWER.
            is_active: Whether the account is active. Defaults to True.

        Returns:
            The newly created User ORM instance with ``id`` populated.

        Raises:
            ValueError: If the email is already in use or role is not a
                        recognised UserRole enum member.
        """
        # Validate role
        if not isinstance(role, UserRole):
            raise ValueError(
                f"Invalid role: {role!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_ROLE_VALUES))}."
            )

        # Guard: email uniqueness
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"A user with email {email!r} already exists.")

        hashed_pw: str = hash_password(password)

        user = User(
            email=email,
            hashed_password=hashed_pw,
            role=role,
            is_active=is_active,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

        logger.info("Created user %r (id=%d, role=%s)", email, user.id, role.value)
        return user

    # ── Read ────────────────────────────────────────────────────────────────

    async def get_by_id(self, db: AsyncSession, user_id: int) -> User | None:
        """Fetch a user by primary key.

        Args:
            db: Active database session.
            user_id: The user's primary key (integer ID).

        Returns:
            The matching User instance, or ``None`` if not found.
        """
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        """Fetch a user by email address.

        Args:
            db: Active database session.
            email: The user's exact (case-sensitive) email address.

        Returns:
            The matching User instance, or ``None`` if not found.
        """
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def list_users(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
    ) -> list[User]:
        """Return a paginated list of all users ordered by ID.

        Args:
            db: Active database session.
            skip: Number of records to skip (offset). Default 0.
            limit: Maximum number of records to return. Default 100.

        Returns:
            A (possibly empty) list of User instances.
        """
        result = await db.execute(
            select(User).offset(skip).limit(limit).order_by(User.id)
        )
        return list(result.scalars().all())

    # ── Update ──────────────────────────────────────────────────────────────

    async def update_user(
        self, db: AsyncSession, user_id: int, **kwargs: Any
    ) -> User:
        """Update one or more user fields selectively.

        Accepts keyword arguments for any updatable field. When
        ``password`` is supplied it is hashed before storage.
        When ``role`` is supplied it is validated against ``UserRole``.

        Args:
            db: Active database session.
            user_id: The user's primary key.
            **kwargs: Fields to update. Supported keys: ``email``,
                      ``password``, ``role``, ``is_active``.

        Returns:
            The refreshed User instance after the update.

        Raises:
            ValueError: If the user is not found or ``role`` is invalid.
        """
        user = await self._require_user(db, user_id)

        # Hash password before storing
        if "password" in kwargs:
            kwargs["hashed_password"] = hash_password(kwargs.pop("password"))

        # Validate role
        if "role" in kwargs:
            role_val = kwargs["role"]
            if not isinstance(role_val, UserRole):
                raise ValueError(
                    f"Invalid role: {role_val!r}. "
                    f"Must be one of: {', '.join(sorted(_VALID_ROLE_VALUES))}."
                )

        for field, value in kwargs.items():
            if hasattr(user, field):
                setattr(user, field, value)

        await db.flush()
        await db.refresh(user)

        logger.info("Updated user id=%d", user_id)
        return user

    # ── Deactivate ──────────────────────────────────────────────────────────

    async def deactivate_user(self, db: AsyncSession, user_id: int) -> User:
        """Deactivate a user by setting ``is_active`` to ``False``.

        The user record is preserved — this is a soft-delete.

        Args:
            db: Active database session.
            user_id: The user's primary key.

        Returns:
            The refreshed User instance with ``is_active=False``.

        Raises:
            ValueError: If the user is not found.
        """
        user = await self._require_user(db, user_id)
        user.is_active = False
        await db.flush()
        await db.refresh(user)

        logger.info("Deactivated user id=%d", user_id)
        return user

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _require_user(self, db: AsyncSession, user_id: int) -> User:
        """Fetch a user by ID or raise ValueError if not found."""
        user = await self.get_by_id(db, user_id)
        if user is None:
            raise ValueError(f"User with id={user_id!r} not found.")
        return user

