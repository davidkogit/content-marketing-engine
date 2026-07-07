"""
Integration tests for the auth API endpoints.

Uses an in-memory SQLite database and httpx AsyncClient to exercise the
full FastAPI auth router: register, login, token refresh, and the /me
profile endpoint.
"""

from __future__ import annotations

import asyncio
import os

# ── Ensure required env vars are set BEFORE any app imports ─────────────
# The Settings singleton loads at import time — we must provide a SECRET_KEY
# that satisfies the minimum-length requirement (≥32 chars).
os.environ.setdefault(
    "SECRET_KEY",
    "test-secret-key-that-is-at-least-32-characters-long!!",
)

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.jwt_service import JWTService
from app.database import Base, get_db
from app.main import create_app
from app.models.user import UserRole

# ── Constants ───────────────────────────────────────────────────────────────

_TEST_SECRET: str = os.environ["SECRET_KEY"]


# ── Test Application Factory ────────────────────────────────────────────────


def _build_test_app(*, db_override=None):
    """Create a FastAPI app with auth router and an overridable DB dependency."""
    app = create_app()

    if db_override is not None:
        # Only override if test needs custom DB behaviour
        original_get_db = get_db
        app.dependency_overrides[original_get_db] = db_override

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
    """Return an httpx AsyncClient pointed at the test FastAPI app.

    The app's ``get_db`` dependency is overridden to return the per-test
    ``db_session`` so all endpoint database operations use the isolated
    in-memory database.
    """

    async def override_get_db():
        yield db_session

    app = _build_test_app(db_override=override_get_db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Helper ──────────────────────────────────────────────────────────────────


async def _register(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "securepass123",
    role: str = "editor",
) -> dict:
    """Register a user via the API and return the parsed JSON response."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "role": role},
    )
    return resp.json()


async def _login(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "securepass123",
) -> dict:
    """Log in and return the token response dict."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return resp.json()


# ── POST /auth/register ─────────────────────────────────────────────────────


class TestRegister:
    """Tests for POST /auth/register."""

    async def test_register_returns_201_and_tokens(self, client: AsyncClient) -> None:
        """Successful registration returns 201 with access and refresh tokens."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "new@example.com", "password": "securepass123"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        # Tokens should be non-empty strings with 3 JWT segments
        assert body["access_token"].count(".") == 2
        assert body["refresh_token"].count(".") == 2

    async def test_register_default_role_is_viewer(self, client: AsyncClient) -> None:
        """When no role is specified, the user gets VIEWER."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "viewer@example.com", "password": "securepass123"},
        )
        assert resp.status_code == 201

        # Login and fetch /me to verify role
        tokens = resp.json()
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert me_resp.json()["role"] == "viewer"

    async def test_register_sets_requested_role(self, client: AsyncClient) -> None:
        """Registering with an explicit role sets that role."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "admin@example.com", "password": "securepass123", "role": "admin"},
        )
        assert resp.status_code == 201

        tokens = resp.json()
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert me_resp.json()["role"] == "admin"

    async def test_register_duplicate_email_returns_409(self, client: AsyncClient) -> None:
        """Registering the same email twice returns 409 Conflict."""
        await _register(client, email="dup@example.com")
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "dup@example.com", "password": "anotherpass1"},
        )
        assert resp.status_code == 409

    async def test_register_short_password_returns_422(self, client: AsyncClient) -> None:
        """Password shorter than 8 characters is rejected by Pydantic validation."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "short@example.com", "password": "1234567"},
        )
        assert resp.status_code == 422

    async def test_register_invalid_email_returns_422(self, client: AsyncClient) -> None:
        """An invalid email format is rejected at the schema level."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "securepass123"},
        )
        assert resp.status_code == 422

    async def test_register_missing_password_returns_422(self, client: AsyncClient) -> None:
        """Missing required fields return 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "nopass@example.com"},
        )
        assert resp.status_code == 422


# ── POST /auth/login ────────────────────────────────────────────────────────


class TestLogin:
    """Tests for POST /auth/login."""

    async def test_login_returns_tokens(self, client: AsyncClient) -> None:
        """Successful login returns 200 with access and refresh tokens."""
        await _register(client, email="login@example.com")
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "securepass123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_wrong_password_returns_401(self, client: AsyncClient) -> None:
        """Wrong password returns 401 with a generic error message."""
        await _register(client, email="wrongpw@example.com")
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrongpw@example.com", "password": "WRONG"},
        )
        assert resp.status_code == 401
        assert "Invalid email or password" in resp.json()["detail"]

    async def test_login_nonexistent_email_returns_401(self, client: AsyncClient) -> None:
        """A non-existent email returns 401 without revealing user existence."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "whatever"},
        )
        assert resp.status_code == 401
        assert "Invalid email or password" in resp.json()["detail"]

    async def test_login_deactivated_account_returns_401(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """A deactivated account cannot log in, even with correct credentials."""
        # Register first, then manually deactivate via the service
        await _register(client, email="deactivated@example.com")

        from app.auth.user_service import UserService
        svc = UserService()
        user = await svc.get_by_email(db_session, "deactivated@example.com")
        await svc.deactivate_user(db_session, user.id)

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "deactivated@example.com", "password": "securepass123"},
        )
        assert resp.status_code == 401
        assert "deactivated" in resp.json()["detail"].lower()

    async def test_login_missing_email_returns_422(self, client: AsyncClient) -> None:
        """Missing required fields return 422."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"password": "securepass123"},
        )
        assert resp.status_code == 422


# ── GET /auth/me ────────────────────────────────────────────────────────────


class TestGetMe:
    """Tests for GET /auth/me."""

    async def test_get_me_returns_user_profile(self, client: AsyncClient) -> None:
        """Authenticated request returns the full user profile."""
        tokens = await _register(client, email="profile@example.com")
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200
        user = resp.json()
        assert user["email"] == "profile@example.com"
        assert user["role"] == "editor"
        assert user["is_active"] is True
        assert "id" in user
        assert "created_at" in user

    async def test_get_me_no_token_returns_401(self, client: AsyncClient) -> None:
        """Request without an Authorization header returns 401."""
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_get_me_invalid_token_returns_401(self, client: AsyncClient) -> None:
        """A garbled token returns 401."""
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not.a.real.jwt"},
        )
        assert resp.status_code == 401

    async def test_get_me_wrong_scheme_returns_401(self, client: AsyncClient) -> None:
        """Using Basic auth instead of Bearer returns 401."""
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == 401

    async def test_get_me_expired_token_returns_401(self, client: AsyncClient) -> None:
        """An expired token returns 401."""
        # Create a token with near-zero expiry using the same secret as the app
        jwt_svc = JWTService(
            secret_key=_TEST_SECRET,
            access_token_expiry_minutes=0,
        )
        token = await jwt_svc.create_access_token(
            user_id=9999,
            email="expired@example.com",
            role="viewer",
        )
        # Small delay to ensure expiry
        import time
        time.sleep(0.02)

        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401


# ── POST /auth/refresh ──────────────────────────────────────────────────────


class TestRefresh:
    """Tests for POST /auth/refresh."""

    async def test_refresh_returns_new_token_pair(self, client: AsyncClient) -> None:
        """Exchanging a valid refresh token returns new access + refresh tokens."""
        tokens = await _register(client, email="refresh@example.com")
        old_access = tokens["access_token"]
        old_refresh = tokens["refresh_token"]

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        # New tokens should differ from the old ones
        assert body["access_token"] != old_access
        assert body["refresh_token"] != old_refresh

    async def test_refresh_new_tokens_are_valid(self, client: AsyncClient) -> None:
        """The tokens returned from refresh should be usable for /me."""
        tokens = await _register(client, email="valid@example.com")
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        new_tokens = resp.json()

        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == "valid@example.com"

    async def test_refresh_with_access_token_returns_401(self, client: AsyncClient) -> None:
        """Using an access token (not refresh) for refresh returns 401."""
        tokens = await _register(client, email="accesstok@example.com")
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["access_token"]},
        )
        assert resp.status_code == 401
        assert "not a refresh token" in resp.json()["detail"].lower()

    async def test_refresh_with_invalid_token_returns_401(self, client: AsyncClient) -> None:
        """A garbled refresh token returns 401."""
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not-a-real-token"},
        )
        assert resp.status_code == 401

    async def test_refresh_with_empty_token_returns_422(self, client: AsyncClient) -> None:
        """An empty refresh token is rejected by schema validation."""
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": ""},
        )
        assert resp.status_code == 422

    async def test_refresh_expired_token_returns_401(self, client: AsyncClient) -> None:
        """An expired refresh token returns 401."""
        jwt_svc = JWTService(
            secret_key=_TEST_SECRET,
            refresh_token_expiry_days=0,
        )
        token = await jwt_svc.create_refresh_token(user_id=9999)
        import time
        time.sleep(0.02)

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": token},
        )
        assert resp.status_code == 401

    async def test_refresh_deleted_user_returns_401(self, client: AsyncClient) -> None:
        """Refreshing a token for a non-existent user returns 401."""
        jwt_svc = JWTService(secret_key=_TEST_SECRET)
        token = await jwt_svc.create_refresh_token(user_id=9999999)

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": token},
        )
        assert resp.status_code == 401


# ── Full Auth Flow Integration ──────────────────────────────────────────────


class TestFullAuthFlow:
    """End-to-end integration tests spanning multiple endpoints."""

    async def test_register_login_me_refresh_flow(self, client: AsyncClient) -> None:
        """Complete auth flow: register → login → /me → refresh → /me."""
        # 1. Register
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "flow@example.com", "password": "flowpass1234", "role": "editor"},
        )
        assert reg_resp.status_code == 201
        reg_tokens = reg_resp.json()

        # 2. Verify /me with registration tokens
        me1 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {reg_tokens['access_token']}"},
        )
        assert me1.status_code == 200
        assert me1.json()["email"] == "flow@example.com"

        # 3. Login separately (should get new tokens)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "flow@example.com", "password": "flowpass1234"},
        )
        assert login_resp.status_code == 200
        login_tokens = login_resp.json()

        # 4. Verify /me with login tokens
        me2 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login_tokens['access_token']}"},
        )
        assert me2.status_code == 200

        # 5. Refresh tokens
        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login_tokens["refresh_token"]},
        )
        assert refresh_resp.status_code == 200
        new_tokens = refresh_resp.json()

        # 6. Verify /me with refreshed tokens
        me3 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
        )
        assert me3.status_code == 200
        assert me3.json()["email"] == "flow@example.com"

    async def test_multiple_users_isolation(self, client: AsyncClient) -> None:
        """Tokens from one user should not give access to another user's data."""
        # Register two users
        tokens_a = await _register(client, email="userA@example.com", password="passA12345")
        tokens_b = await _register(client, email="userB@example.com", password="passB12345")

        # User A accesses their profile
        me_a = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens_a['access_token']}"},
        )
        assert me_a.json()["email"] == "userA@example.com"

        # User B accesses their profile
        me_b = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens_b['access_token']}"},
        )
        assert me_b.json()["email"] == "userB@example.com"

        assert me_a.json()["id"] != me_b.json()["id"]
