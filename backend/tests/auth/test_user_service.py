"""
Unit tests for the UserService class.

Uses an in-memory SQLite database via SQLAlchemy's async engine to
exercise every service method against a real (but ephemeral) database.
"""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.user_service import UserService
from app.database import Base
from app.models.user import User, UserRole


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def event_loop():
    """Create a fresh event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_session() -> AsyncSession:
    """Provide an async session backed by an in-memory SQLite database.

    All tables are created fresh at the start of each test function
    and dropped after the test completes, guaranteeing test isolation.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def service() -> UserService:
    """Return a fresh UserService instance."""
    return UserService()


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _seed_user(db: AsyncSession, **overrides) -> User:
    """Insert a user directly (bypassing the service) for test setup."""
    defaults = {
        "email": "test@example.com",
        "hashed_password": "hashed-placeholder",
        "role": UserRole.EDITOR,
        "is_active": True,
    }
    defaults.update(overrides)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


# ── create_user ─────────────────────────────────────────────────────────────


class TestCreateUser:
    """Tests for UserService.create_user."""

    async def test_create_user_succeeds(self, db_session: AsyncSession, service: UserService) -> None:
        """Creating a user with valid data returns a persisted User."""
        user = await service.create_user(
            db_session,
            email="new@example.com",
            password="secure123",
            role=UserRole.EDITOR,
        )
        assert isinstance(user, User)
        assert user.id is not None
        assert user.email == "new@example.com"

    async def test_create_user_hashes_password(self, db_session: AsyncSession, service: UserService) -> None:
        """The stored password must be a bcrypt hash, not plain text."""
        user = await service.create_user(
            db_session,
            email="hash@example.com",
            password="my-plain-password",
        )
        assert user.hashed_password != "my-plain-password"
        assert user.hashed_password.startswith("$2b$")

    async def test_create_user_sets_default_role_viewer(self, db_session: AsyncSession, service: UserService) -> None:
        """When no role is specified, default to VIEWER."""
        user = await service.create_user(
            db_session,
            email="viewer@example.com",
            password="pass123",
        )
        assert user.role == UserRole.VIEWER

    async def test_create_user_rejects_duplicate_email(self, db_session: AsyncSession, service: UserService) -> None:
        """Creating a second user with the same email raises ValueError."""
        await service.create_user(db_session, email="dup@example.com", password="pass1")
        with pytest.raises(ValueError, match="already exists"):
            await service.create_user(db_session, email="dup@example.com", password="pass2")

    async def test_create_user_rejects_invalid_role(self, db_session: AsyncSession, service: UserService) -> None:
        """Passing a role that is not a UserRole enum member must fail."""
        with pytest.raises(ValueError, match="Invalid role"):
            await service.create_user(
                db_session,
                email="badrole@example.com",
                password="pass",
                role="bogus_role",  # type: ignore[arg-type]
            )

    async def test_create_user_accepts_all_valid_roles(self, db_session: AsyncSession, service: UserService) -> None:
        """Every UserRole enum member should be accepted."""
        for role in UserRole:
            email = f"{role.value}@example.com"
            user = await service.create_user(
                db_session, email=email, password="pass", role=role
            )
            assert user.role == role


# ── get_by_id ───────────────────────────────────────────────────────────────


class TestGetById:
    """Tests for UserService.get_by_id."""

    async def test_get_by_id_returns_user_when_found(self, db_session: AsyncSession, service: UserService) -> None:
        """Lookup by existing ID returns the correct user."""
        seeded = await _seed_user(db_session, email="findme@example.com")
        found = await service.get_by_id(db_session, seeded.id)
        assert found is not None
        assert found.email == "findme@example.com"

    async def test_get_by_id_returns_none_when_not_found(self, db_session: AsyncSession, service: UserService) -> None:
        """Lookup by a nonexistent ID returns None."""
        found = await service.get_by_id(db_session, 99999)
        assert found is None


# ── get_by_email ────────────────────────────────────────────────────────────


class TestGetByEmail:
    """Tests for UserService.get_by_email."""

    async def test_get_by_email_returns_user_when_found(self, db_session: AsyncSession, service: UserService) -> None:
        """Lookup by exact email returns the correct user."""
        await _seed_user(db_session, email="bymail@example.com")
        found = await service.get_by_email(db_session, "bymail@example.com")
        assert found is not None
        assert found.email == "bymail@example.com"

    async def test_get_by_email_returns_none_when_not_found(self, db_session: AsyncSession, service: UserService) -> None:
        """Lookup for a nonexistent email returns None."""
        found = await service.get_by_email(db_session, "nope@example.com")
        assert found is None


# ── list_users ──────────────────────────────────────────────────────────────


class TestListUsers:
    """Tests for UserService.list_users."""

    async def test_list_users_returns_all_created_users(self, db_session: AsyncSession, service: UserService) -> None:
        """Listing should return every seeded user."""
        await _seed_user(db_session, email="a@example.com")
        await _seed_user(db_session, email="b@example.com")
        users = await service.list_users(db_session)
        assert len(users) == 2

    async def test_list_users_respects_limit_and_offset(self, db_session: AsyncSession, service: UserService) -> None:
        """Pagination via skip and limit should work correctly."""
        for i in range(5):
            await _seed_user(db_session, email=f"user{i}@example.com")

        page1 = await service.list_users(db_session, skip=0, limit=2)
        assert len(page1) == 2

        page2 = await service.list_users(db_session, skip=2, limit=2)
        assert len(page2) == 2
        assert page1[0].id != page2[0].id

    async def test_list_users_empty_database_returns_empty_list(self, db_session: AsyncSession, service: UserService) -> None:
        """With no users, list should return an empty list, not None."""
        users = await service.list_users(db_session)
        assert isinstance(users, list)
        assert len(users) == 0


# ── update_user ─────────────────────────────────────────────────────────────


class TestUpdateUser:
    """Tests for UserService.update_user."""

    async def test_update_user_changes_email(self, db_session: AsyncSession, service: UserService) -> None:
        """Updating email should persist the new value."""
        seeded = await _seed_user(db_session)
        updated = await service.update_user(db_session, seeded.id, email="updated@example.com")
        assert updated.email == "updated@example.com"

    async def test_update_user_hashes_new_password(self, db_session: AsyncSession, service: UserService) -> None:
        """Updating password should store a bcrypt hash."""
        seeded = await _seed_user(db_session)
        updated = await service.update_user(db_session, seeded.id, password="newpass")
        assert updated.hashed_password.startswith("$2b$")

    async def test_update_user_changes_role(self, db_session: AsyncSession, service: UserService) -> None:
        """Updating role should validate and persist the new role."""
        seeded = await _seed_user(db_session)
        updated = await service.update_user(db_session, seeded.id, role=UserRole.ADMIN)
        assert updated.role == UserRole.ADMIN

    async def test_update_user_rejects_invalid_role(self, db_session: AsyncSession, service: UserService) -> None:
        """Passing an invalid role string should raise ValueError."""
        seeded = await _seed_user(db_session)
        with pytest.raises(ValueError, match="Invalid role"):
            await service.update_user(db_session, seeded.id, role="superhero")

    async def test_update_user_raises_when_not_found(self, db_session: AsyncSession, service: UserService) -> None:
        """Updating a nonexistent user should raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            await service.update_user(db_session, 99999, email="ghost@example.com")

    async def test_update_user_multiple_fields_at_once(self, db_session: AsyncSession, service: UserService) -> None:
        """Multiple fields can be updated in a single call."""
        seeded = await _seed_user(db_session)
        updated = await service.update_user(
            db_session,
            seeded.id,
            email="multi@example.com",
            role=UserRole.SUPER_ADMIN,
        )
        assert updated.email == "multi@example.com"
        assert updated.role == UserRole.SUPER_ADMIN


# ── deactivate_user ─────────────────────────────────────────────────────────


class TestDeactivateUser:
    """Tests for UserService.deactivate_user."""

    async def test_deactivate_user_sets_is_active_false(self, db_session: AsyncSession, service: UserService) -> None:
        """Deactivation should flip is_active to False."""
        seeded = await _seed_user(db_session)
        deactivated = await service.deactivate_user(db_session, seeded.id)
        assert deactivated.is_active is False

    async def test_deactivate_user_raises_when_not_found(self, db_session: AsyncSession, service: UserService) -> None:
        """Deactivating a nonexistent user should raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            await service.deactivate_user(db_session, 99999)

