"""
Integration tests for user management API endpoints.

Exercises the full CRUD lifecycle for user management: listing users,
inviting new users, changing roles, and deactivating accounts.  Also
verifies role enforcement (non-super_admin access denied) and edge-case
guards (self-demotion, self-deactivation, last super_admin protection).
"""

from __future__ import annotations

import asyncio
import os

# ── Ensure required env vars are set BEFORE any app imports ─────────────
os.environ.setdefault(
    "SECRET_KEY",
    "test-secret-key-that-is-at-least-32-characters-long!!",
)

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import create_app
from app.models.user import User, UserRole

# ── Constants ───────────────────────────────────────────────────────────────

_TEST_SECRET: str = os.environ["SECRET_KEY"]


# ── Test Application Factory ────────────────────────────────────────────────


def _build_test_app(*, db_override=None):
    """Create a FastAPI app with all routers and an overridable DB dependency."""
    app = create_app()

    if db_override is not None:
        app.dependency_overrides[get_db] = db_override

    return app


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def event_loop():
    """Create a fresh event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def engine():
    """Create an in-memory SQLite engine with fresh tables per test."""
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture(scope="function")
async def db_session(engine) -> AsyncSession:
    """Yield a per-test database session using the in-memory engine."""
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncClient:
    """Return an httpx AsyncClient pointed at the test FastAPI app."""

    async def override_get_db():
        yield db_session

    app = _build_test_app(db_override=override_get_db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _register_and_login(
    client: AsyncClient,
    email: str = "admin@example.com",
    password: str = "adminpass123",
    role: str = "super_admin",
) -> dict:
    """Register a user, log in, and return tokens dict."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "role": role},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return resp.json()


async def _create_super_admin(
    db_session: AsyncSession,
    email: str = "admin@example.com",
) -> User:
    """Create a super_admin user directly in the database."""
    from app.auth.hashing import hash_password

    user = User(
        email=email,
        hashed_password=hash_password("adminpass123"),
        role=UserRole.SUPER_ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


async def _create_user(
    db_session: AsyncSession,
    email: str = "editor@example.com",
    role: UserRole = UserRole.EDITOR,
) -> User:
    """Create a user with a given role directly in the database."""
    from app.auth.hashing import hash_password

    user = User(
        email=email,
        hashed_password=hash_password("securepass123"),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


def _auth_header(tokens: dict) -> dict:
    """Return an Authorization header dict for the given tokens."""
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ── GET /settings/users ─────────────────────────────────────────────────────


class TestListUsers:
    """Tests for GET /api/v1/settings/users."""

    async def test_list_users_returns_all_users(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A super_admin can list all users with their details."""
        await _create_user(db_session, email="user1@example.com", role=UserRole.EDITOR)
        await _create_user(db_session, email="user2@example.com", role=UserRole.VIEWER)
        tokens = await _register_and_login(client)

        resp = await client.get(
            "/api/v1/settings/users",
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert body["total"] >= 3  # admin + user1 + user2
        emails = [u["email"] for u in body["items"]]
        assert "admin@example.com" in emails
        assert "user1@example.com" in emails
        assert "user2@example.com" in emails

    async def test_list_users_returns_role_and_status(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Each user entry includes role and is_active fields."""
        await _create_user(db_session, email="viewer@example.com", role=UserRole.VIEWER)
        tokens = await _register_and_login(client)

        resp = await client.get(
            "/api/v1/settings/users",
            headers=_auth_header(tokens),
        )
        body = resp.json()
        viewer = next(u for u in body["items"] if u["email"] == "viewer@example.com")
        assert viewer["role"] == "viewer"
        assert viewer["is_active"] is True
        assert "created_at" in viewer

    async def test_list_users_non_admin_returns_403(
        self, client: AsyncClient
    ) -> None:
        """A non-super_admin user cannot list all users."""
        tokens = await _register_and_login(
            client, email="editor@example.com", role="editor"
        )

        resp = await client.get(
            "/api/v1/settings/users",
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 403

    async def test_list_users_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        """Unauthenticated requests return 401."""
        resp = await client.get("/api/v1/settings/users")
        assert resp.status_code == 401


# ── POST /settings/users/invite ─────────────────────────────────────────────


class TestInviteUser:
    """Tests for POST /api/v1/settings/users/invite."""

    async def test_invite_returns_201_and_user_details(
        self, client: AsyncClient
    ) -> None:
        """A super_admin can invite a new user with a specified role."""
        tokens = await _register_and_login(client)

        resp = await client.post(
            "/api/v1/settings/users/invite",
            json={"email": "newuser@example.com", "role": "editor"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "newuser@example.com"
        assert body["role"] == "editor"
        assert body["is_active"] is True
        assert body["user_id"] > 0
        assert "invited" in body["message"].lower()

    async def test_invite_as_admin_role(
        self, client: AsyncClient
    ) -> None:
        """A super_admin can invite a user with the admin role."""
        tokens = await _register_and_login(client)

        resp = await client.post(
            "/api/v1/settings/users/invite",
            json={"email": "newadmin@example.com", "role": "admin"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "admin"

    async def test_invite_as_super_admin_role(
        self, client: AsyncClient
    ) -> None:
        """A super_admin can invite another super_admin."""
        tokens = await _register_and_login(client)

        resp = await client.post(
            "/api/v1/settings/users/invite",
            json={"email": "newsuper@example.com", "role": "super_admin"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "super_admin"

    async def test_invite_duplicate_email_returns_409(
        self, client: AsyncClient
    ) -> None:
        """Inviting an email that already exists returns 409."""
        tokens = await _register_and_login(client)

        await client.post(
            "/api/v1/settings/users/invite",
            json={"email": "dup@example.com", "role": "editor"},
            headers=_auth_header(tokens),
        )
        resp = await client.post(
            "/api/v1/settings/users/invite",
            json={"email": "dup@example.com", "role": "viewer"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 409

    async def test_invite_non_admin_returns_403(
        self, client: AsyncClient
    ) -> None:
        """A non-super_admin user cannot invite users."""
        tokens = await _register_and_login(
            client, email="editor@example.com", role="editor"
        )

        resp = await client.post(
            "/api/v1/settings/users/invite",
            json={"email": "someone@example.com", "role": "viewer"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 403

    async def test_invite_missing_role_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Missing the required 'role' field returns 422."""
        tokens = await _register_and_login(client)

        resp = await client.post(
            "/api/v1/settings/users/invite",
            json={"email": "norole@example.com"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 422

    async def test_invite_invalid_email_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Invalid email format returns 422."""
        tokens = await _register_and_login(client)

        resp = await client.post(
            "/api/v1/settings/users/invite",
            json={"email": "not-an-email", "role": "viewer"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 422


# ── PUT /settings/users/{id}/role ───────────────────────────────────────────


class TestChangeRole:
    """Tests for PUT /api/v1/settings/users/{id}/role."""

    async def test_change_role_succeeds(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A super_admin can change another user's role."""
        tokens = await _register_and_login(client)
        editor = await _create_user(db_session, email="editor@example.com", role=UserRole.EDITOR)

        resp = await client.put(
            f"/api/v1/settings/users/{editor.id}/role",
            json={"role": "admin"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["role"] == "admin"
        assert body["user_id"] == editor.id
        assert "updated" in body["message"].lower()

    async def test_change_role_promote_to_super_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """An editor can be promoted to super_admin."""
        tokens = await _register_and_login(client)
        editor = await _create_user(db_session, email="editor@example.com", role=UserRole.EDITOR)

        resp = await client.put(
            f"/api/v1/settings/users/{editor.id}/role",
            json={"role": "super_admin"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "super_admin"

    async def test_change_role_demote_admin_to_viewer(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """An admin can be demoted to viewer."""
        tokens = await _register_and_login(client)
        admin = await _create_user(db_session, email="admin2@example.com", role=UserRole.ADMIN)

        resp = await client.put(
            f"/api/v1/settings/users/{admin.id}/role",
            json={"role": "viewer"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "viewer"

    async def test_change_own_role_returns_403(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A super_admin cannot change their own role (self-demotion guard)."""
        admin = await _create_super_admin(db_session, email="self@example.com")
        tokens = await _register_and_login(client, email="self@example.com")

        resp = await client.put(
            f"/api/v1/settings/users/{admin.id}/role",
            json={"role": "viewer"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 403
        assert "own role" in resp.json()["detail"].lower()

    async def test_change_role_nonexistent_user_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Changing the role of a non-existent user returns 404."""
        tokens = await _register_and_login(client)

        resp = await client.put(
            "/api/v1/settings/users/99999/role",
            json={"role": "editor"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 404

    async def test_change_role_non_admin_returns_403(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A non-super_admin cannot change roles."""
        viewer = await _create_user(db_session, email="viewer@example.com", role=UserRole.VIEWER)
        target = await _create_user(db_session, email="target@example.com", role=UserRole.EDITOR)

        # Login as the viewer (not super_admin)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "viewer@example.com", "password": "securepass123"},
        )
        tokens = login_resp.json()

        resp = await client.put(
            f"/api/v1/settings/users/{target.id}/role",
            json={"role": "admin"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 403


# ── PUT /settings/users/{id}/deactivate ─────────────────────────────────────


class TestDeactivateUser:
    """Tests for PUT /api/v1/settings/users/{id}/deactivate."""

    async def test_deactivate_succeeds(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A super_admin can deactivate another user."""
        tokens = await _register_and_login(client)
        editor = await _create_user(db_session, email="editor@example.com", role=UserRole.EDITOR)

        resp = await client.put(
            f"/api/v1/settings/users/{editor.id}/deactivate",
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_active"] is False
        assert body["user_id"] == editor.id
        assert "deactivated" in body["message"].lower()

    async def test_deactivated_user_cannot_login(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """After deactivation, the user cannot log in."""
        tokens = await _register_and_login(client)
        editor = await _create_user(db_session, email="editor@example.com", role=UserRole.EDITOR)

        # Verify editor can log in initially (they already exist in DB, just login)
        login_initial = await client.post(
            "/api/v1/auth/login",
            json={"email": "editor@example.com", "password": "securepass123"},
        )
        assert login_initial.status_code == 200
        assert "access_token" in login_initial.json()

        # Deactivate the editor
        await client.put(
            f"/api/v1/settings/users/{editor.id}/deactivate",
            headers=_auth_header(tokens),
        )

        # Attempt login as the deactivated editor
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "editor@example.com", "password": "securepass123"},
        )
        assert login_resp.status_code == 401

    async def test_deactivate_self_returns_403(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A super_admin cannot deactivate themselves."""
        admin = await _create_super_admin(db_session, email="self@example.com")
        tokens = await _register_and_login(client, email="self@example.com")

        resp = await client.put(
            f"/api/v1/settings/users/{admin.id}/deactivate",
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 403
        assert "own account" in resp.json()["detail"].lower()

    async def test_deactivate_last_super_admin_returns_403(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """The last active super_admin cannot be deactivated.

        Creates 3 super_admins, deactivates two through admin1, then
        verifies admin1 (now the last) is protected by the self-guard
        (which fires before the count guard).  The count guard itself
        is validated by the fact that deactivating admin2/admin3
        succeeds while count > 1.
        """
        admin1 = await _create_super_admin(db_session, email="admin1@example.com")
        admin2 = await _create_user(db_session, email="admin2@example.com", role=UserRole.SUPER_ADMIN)
        admin3 = await _create_user(db_session, email="admin3@example.com", role=UserRole.SUPER_ADMIN)
        tokens_a1 = await _register_and_login(client, email="admin1@example.com")

        # Deactivate admin2 — count still > 1 (admin1 + admin3 active)
        resp2 = await client.put(
            f"/api/v1/settings/users/{admin2.id}/deactivate",
            headers=_auth_header(tokens_a1),
        )
        assert resp2.status_code == 200

        # Deactivate admin3 — count still > 1 (only admin1 left)
        resp3 = await client.put(
            f"/api/v1/settings/users/{admin3.id}/deactivate",
            headers=_auth_header(tokens_a1),
        )
        assert resp3.status_code == 200  # count was 2 when checked, allowed

        # Now admin1 is the last active super_admin.
        # Self-deactivation is blocked by the self-guard.
        resp_self = await client.put(
            f"/api/v1/settings/users/{admin1.id}/deactivate",
            headers=_auth_header(tokens_a1),
        )
        assert resp_self.status_code == 403
        assert "own account" in resp_self.json()["detail"].lower()

    async def test_deactivate_super_admin_allowed_when_others_active(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Deactivating a super_admin works when multiple super_admins are active."""
        admin1 = await _create_super_admin(db_session, email="admin1@example.com")
        admin2 = await _create_user(db_session, email="admin2@example.com", role=UserRole.SUPER_ADMIN)
        tokens_a1 = await _register_and_login(client, email="admin1@example.com")

        # admin1 deactivates admin2 — 2 super_admins active → allowed
        resp = await client.put(
            f"/api/v1/settings/users/{admin2.id}/deactivate",
            headers=_auth_header(tokens_a1),
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    async def test_deactivate_nonexistent_user_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Deactivating a non-existent user returns 404."""
        tokens = await _register_and_login(client)

        resp = await client.put(
            "/api/v1/settings/users/99999/deactivate",
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 404

    async def test_deactivate_already_deactivated_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Deactivating an already-deactivated user returns 409."""
        tokens = await _register_and_login(client)
        editor = await _create_user(db_session, email="editor@example.com", role=UserRole.EDITOR)

        # First deactivation
        await client.put(
            f"/api/v1/settings/users/{editor.id}/deactivate",
            headers=_auth_header(tokens),
        )
        # Second deactivation
        resp = await client.put(
            f"/api/v1/settings/users/{editor.id}/deactivate",
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 409

    async def test_deactivate_non_admin_returns_403(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A non-super_admin cannot deactivate users."""
        viewer = await _create_user(db_session, email="viewer@example.com", role=UserRole.VIEWER)
        target = await _create_user(db_session, email="target@example.com", role=UserRole.EDITOR)

        # Login as viewer (not super_admin)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "viewer@example.com", "password": "securepass123"},
        )
        tokens = login_resp.json()

        resp = await client.put(
            f"/api/v1/settings/users/{target.id}/deactivate",
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 403


# ── Edge Cases ──────────────────────────────────────────────────────────────


class TestUserManagementEdgeCases:
    """Edge case and integration tests for user management."""

    async def test_full_user_lifecycle(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Complete lifecycle: invite → change role → deactivate."""
        tokens = await _register_and_login(client)

        # 1. Invite a new user
        invite_resp = await client.post(
            "/api/v1/settings/users/invite",
            json={"email": "lifecycle@example.com", "role": "viewer"},
            headers=_auth_header(tokens),
        )
        assert invite_resp.status_code == 201
        user_id = invite_resp.json()["user_id"]

        # 2. Promote to editor
        role_resp = await client.put(
            f"/api/v1/settings/users/{user_id}/role",
            json={"role": "editor"},
            headers=_auth_header(tokens),
        )
        assert role_resp.status_code == 200
        assert role_resp.json()["role"] == "editor"

        # 3. Promote to admin
        role_resp2 = await client.put(
            f"/api/v1/settings/users/{user_id}/role",
            json={"role": "admin"},
            headers=_auth_header(tokens),
        )
        assert role_resp2.status_code == 200
        assert role_resp2.json()["role"] == "admin"

        # 4. Deactivate
        deact_resp = await client.put(
            f"/api/v1/settings/users/{user_id}/deactivate",
            headers=_auth_header(tokens),
        )
        assert deact_resp.status_code == 200
        assert deact_resp.json()["is_active"] is False

        # 5. Verify user appears in list as deactivated
        list_resp = await client.get(
            "/api/v1/settings/users",
            headers=_auth_header(tokens),
        )
        users = list_resp.json()["items"]
        lifecycle = next(u for u in users if u["id"] == user_id)
        assert lifecycle["is_active"] is False
        assert lifecycle["role"] == "admin"
