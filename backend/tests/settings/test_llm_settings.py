"""
Integration tests for the LLM settings API endpoints.

Uses an in-memory SQLite database and httpx AsyncClient to exercise
the full settings router: get config, update config, test connection,
and role enforcement.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

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
from app.models.user import UserRole

# ── Constants ───────────────────────────────────────────────────────────────

_BASE = "/api/v1/settings/llm"
_SUPER_ADMIN_EMAIL = "super@example.com"
_SUPER_ADMIN_PASSWORD = "superpass123"


# ── Helpers ─────────────────────────────────────────────────────────────────


def _auth_headers(token: str) -> dict[str, str]:
    """Build an Authorization header dict from a JWT token."""
    return {"Authorization": f"Bearer {token}"}


async def _register_super_admin(client: AsyncClient) -> dict:
    """Register a super_admin user and return the token response."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": _SUPER_ADMIN_EMAIL,
            "password": _SUPER_ADMIN_PASSWORD,
            "role": "super_admin",
        },
    )
    assert resp.status_code == 201, f"Register failed: {resp.text}"
    return resp.json()


async def _register_editor(client: AsyncClient) -> dict:
    """Register an editor user and return the token response."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "editor@example.com",
            "password": "editor12345",
            "role": "editor",
        },
    )
    assert resp.status_code == 201, f"Register failed: {resp.text}"
    return resp.json()


# ── Test Application Factory ────────────────────────────────────────────────


def _build_test_app(*, db_override=None):
    """Create a FastAPI app with all routers and optional DB override."""
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
    """Yield a per-test database session."""
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

    The ``get_db`` dependency is overridden to use the per-test
    in-memory database session.
    """
    async def override_get_db():
        yield db_session

    app = _build_test_app(db_override=override_get_db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── GET /settings/llm ───────────────────────────────────────────────────────


class TestGetLLMConfig:
    """Tests for GET /settings/llm."""

    async def test_get_returns_404_when_no_config(self, client: AsyncClient) -> None:
        """When no LLM config exists, the endpoint returns 404."""
        tokens = await _register_super_admin(client)
        resp = await client.get(
            _BASE,
            headers=_auth_headers(tokens["access_token"]),
        )
        assert resp.status_code == 404
        assert "No active LLM configuration" in resp.json()["detail"]

    async def test_get_returns_config_after_setting(self, client: AsyncClient) -> None:
        """After putting a config, GET returns it with a masked API key."""
        tokens = await _register_super_admin(client)

        # First, set a configuration.
        put_resp = await client.put(
            _BASE,
            json={
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "sk-test-key-1234567890abcdef",
            },
            headers=_auth_headers(tokens["access_token"]),
        )
        assert put_resp.status_code == 200

        # Then read it back.
        get_resp = await client.get(
            _BASE,
            headers=_auth_headers(tokens["access_token"]),
        )
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["provider"] == "openai"
        assert body["model"] == "gpt-4o"
        assert body["is_active"] is True
        assert "created_at" in body

    async def test_api_key_is_masked(self, client: AsyncClient) -> None:
        """The returned API key field is always masked (never plaintext)."""
        tokens = await _register_super_admin(client)

        plain_key = "sk-test-key-1234567890abcdef"

        await client.put(
            _BASE,
            json={"provider": "openai", "model": "gpt-4o", "api_key": plain_key},
            headers=_auth_headers(tokens["access_token"]),
        )

        get_resp = await client.get(
            _BASE,
            headers=_auth_headers(tokens["access_token"]),
        )
        body = get_resp.json()

        # The masked key should NOT equal the plain key.
        assert body["masked_api_key"] != plain_key
        # It should contain "..." as the masking separator.
        assert "..." in body["masked_api_key"]
        # It should NOT contain the full original key.
        assert plain_key not in body["masked_api_key"]

    async def test_get_requires_super_admin(self, client: AsyncClient) -> None:
        """Non-super-admin users receive 403."""
        tokens = await _register_editor(client)
        resp = await client.get(
            _BASE,
            headers=_auth_headers(tokens["access_token"]),
        )
        assert resp.status_code == 403

    async def test_get_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """No auth header returns 401."""
        resp = await client.get(_BASE)
        assert resp.status_code == 401


# ── PUT /settings/llm ───────────────────────────────────────────────────────


class TestPutLLMConfig:
    """Tests for PUT /settings/llm."""

    async def test_put_creates_config_successfully(self, client: AsyncClient) -> None:
        """A valid PUT creates a new active config and returns 200."""
        tokens = await _register_super_admin(client)
        resp = await client.put(
            _BASE,
            json={
                "provider": "anthropic",
                "model": "claude-3-opus-20240229",
                "api_key": "sk-ant-test-key-12345",
            },
            headers=_auth_headers(tokens["access_token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "anthropic"
        assert body["model"] == "claude-3-opus-20240229"
        assert body["is_active"] is True
        assert "..." in body["masked_api_key"]

    async def test_put_overwrites_previous_config(self, client: AsyncClient) -> None:
        """A second PUT replaces the previous active config."""
        tokens = await _register_super_admin(client)

        # First config.
        await client.put(
            _BASE,
            json={"provider": "openai", "model": "gpt-4o", "api_key": "sk-first-key"},
            headers=_auth_headers(tokens["access_token"]),
        )

        # Second config.
        resp = await client.put(
            _BASE,
            json={"provider": "anthropic", "model": "claude-3-sonnet", "api_key": "sk-second-key"},
            headers=_auth_headers(tokens["access_token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "anthropic"
        assert body["model"] == "claude-3-sonnet"

        # GET should reflect the second config.
        get_resp = await client.get(
            _BASE,
            headers=_auth_headers(tokens["access_token"]),
        )
        assert get_resp.json()["provider"] == "anthropic"

    async def test_put_rejects_invalid_provider(self, client: AsyncClient) -> None:
        """An unknown provider name is rejected with 422."""
        tokens = await _register_super_admin(client)
        resp = await client.put(
            _BASE,
            json={
                "provider": "google-gemini",
                "model": "gemini-pro",
                "api_key": "sk-test",
            },
            headers=_auth_headers(tokens["access_token"]),
        )
        assert resp.status_code == 422

    async def test_put_missing_api_key_returns_422(self, client: AsyncClient) -> None:
        """API key is required and missing → 422."""
        tokens = await _register_super_admin(client)
        resp = await client.put(
            _BASE,
            json={"provider": "openai", "model": "gpt-4o"},
            headers=_auth_headers(tokens["access_token"]),
        )
        assert resp.status_code == 422

    async def test_put_missing_provider_returns_422(self, client: AsyncClient) -> None:
        """Provider is required and missing → 422."""
        tokens = await _register_super_admin(client)
        resp = await client.put(
            _BASE,
            json={"model": "gpt-4o", "api_key": "sk-test"},
            headers=_auth_headers(tokens["access_token"]),
        )
        assert resp.status_code == 422

    async def test_put_empty_provider_returns_422(self, client: AsyncClient) -> None:
        """Empty provider name → 422."""
        tokens = await _register_super_admin(client)
        resp = await client.put(
            _BASE,
            json={"provider": "", "model": "gpt-4o", "api_key": "sk-test"},
            headers=_auth_headers(tokens["access_token"]),
        )
        assert resp.status_code == 422

    async def test_put_requires_super_admin(self, client: AsyncClient) -> None:
        """Editor cannot update LLM config → 403."""
        tokens = await _register_editor(client)
        resp = await client.put(
            _BASE,
            json={"provider": "openai", "model": "gpt-4o", "api_key": "sk-test"},
            headers=_auth_headers(tokens["access_token"]),
        )
        assert resp.status_code == 403

    async def test_put_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """No auth header → 401."""
        resp = await client.put(
            _BASE,
            json={"provider": "openai", "model": "gpt-4o", "api_key": "sk-test"},
        )
        assert resp.status_code == 401

    async def test_api_key_encrypted_in_db(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """The stored API key in the database should be encrypted (not plaintext)."""
        from app.llm.config_service import LLMConfigService

        tokens = await _register_super_admin(client)

        plain_key = "sk-test-key-encrypted-check-1234"

        await client.put(
            _BASE,
            json={"provider": "openai", "model": "gpt-4o", "api_key": plain_key},
            headers=_auth_headers(tokens["access_token"]),
        )

        config = await LLMConfigService.get_active_config(db_session)
        assert config is not None
        # The stored value must be encrypted — not the plain key.
        assert config.api_key_encrypted != plain_key
        # Fernet-encrypted values always start with 'gAAAAA' prefix.
        assert config.api_key_encrypted.startswith("gAAAAA")


# ── POST /settings/llm/test ─────────────────────────────────────────────────


class TestLLMConnectionTest:
    """Tests for POST /settings/llm/test."""

    async def test_test_returns_failure_when_no_config(self, client: AsyncClient) -> None:
        """When no config is set, the test endpoint returns success=False."""
        tokens = await _register_super_admin(client)
        resp = await client.post(
            f"{_BASE}/test",
            headers=_auth_headers(tokens["access_token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "No active LLM configuration" in body["message"]

    async def test_test_with_mocked_provider_success(
        self, client: AsyncClient
    ) -> None:
        """A mocked provider returns success with measured latency."""
        tokens = await _register_super_admin(client)

        # First, set a config.
        await client.put(
            _BASE,
            json={"provider": "openai", "model": "gpt-4o", "api_key": "sk-test-123456"},
            headers=_auth_headers(tokens["access_token"]),
        )

        # Mock the provider's generate method.
        from app.llm.provider_base import LLMResponse

        mock_response = LLMResponse(
            content="ok",
            model_used="gpt-4o",
            tokens_used=5,
            finish_reason="stop",
            latency_ms=42.5,
        )

        with patch(
            "app.settings.llm_service.get_provider",
            return_value=AsyncMock(
                generate=AsyncMock(return_value=mock_response),
            ),
        ):
            resp = await client.post(
                f"{_BASE}/test",
                headers=_auth_headers(tokens["access_token"]),
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["latency_ms"] > 0
            assert body["message"] == "Connection successful."
            assert body["model_used"] == "gpt-4o"

    async def test_test_with_auth_error(self, client: AsyncClient) -> None:
        """A provider authentication error returns success=False with details."""
        tokens = await _register_super_admin(client)

        await client.put(
            _BASE,
            json={"provider": "openai", "model": "gpt-4o", "api_key": "sk-test-123456"},
            headers=_auth_headers(tokens["access_token"]),
        )

        from app.llm.provider_base import LLMAuthError

        with patch(
            "app.settings.llm_service.get_provider",
            return_value=AsyncMock(
                generate=AsyncMock(side_effect=LLMAuthError("Invalid API key")),
            ),
        ):
            resp = await client.post(
                f"{_BASE}/test",
                headers=_auth_headers(tokens["access_token"]),
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is False
            assert "Authentication failed" in body["message"]

    async def test_test_requires_super_admin(self, client: AsyncClient) -> None:
        """Editor cannot test LLM connection → 403."""
        tokens = await _register_editor(client)
        resp = await client.post(
            f"{_BASE}/test",
            headers=_auth_headers(tokens["access_token"]),
        )
        assert resp.status_code == 403

    async def test_test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """No auth header → 401."""
        resp = await client.post(f"{_BASE}/test")
        assert resp.status_code == 401


# ── Cache Invalidation ─────────────────────────────────────────────────────


class TestCacheInvalidation:
    """Tests that the in-memory cache is properly invalidated on updates."""

    async def test_cache_reflects_update(self, client: AsyncClient) -> None:
        """After updating config, GET returns the new values (not stale)."""
        tokens = await _register_super_admin(client)

        await client.put(
            _BASE,
            json={"provider": "openai", "model": "gpt-4o", "api_key": "sk-first"},
            headers=_auth_headers(tokens["access_token"]),
        )

        await client.put(
            _BASE,
            json={"provider": "anthropic", "model": "claude-3-sonnet", "api_key": "sk-second"},
            headers=_auth_headers(tokens["access_token"]),
        )

        # GET should return the new model, not the old cached one.
        resp = await client.get(
            _BASE,
            headers=_auth_headers(tokens["access_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["model"] == "claude-3-sonnet"


# ── End-to-End Settings Flow ────────────────────────────────────────────────


class TestFullSettingsFlow:
    """End-to-end integration test spanning multiple settings endpoints."""

    async def test_full_lifecycle(self, client: AsyncClient) -> None:
        """Full flow: get 404 → set config → get config → overwrite → test connection."""
        tokens = await _register_super_admin(client)
        headers = _auth_headers(tokens["access_token"])

        # 1. No config yet — GET returns 404.
        resp = await client.get(_BASE, headers=headers)
        assert resp.status_code == 404

        # 2. Set OpenAI config.
        put_resp = await client.put(
            _BASE,
            json={"provider": "openai", "model": "gpt-4o", "api_key": "sk-key-abc"},
            headers=headers,
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["provider"] == "openai"

        # 3. Read it back — key should be masked.
        get_resp = await client.get(_BASE, headers=headers)
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["provider"] == "openai"
        assert "sk-key-abc" not in body["masked_api_key"]
        assert "..." in body["masked_api_key"]

        # 4. Overwrite with Anthropic config.
        put2 = await client.put(
            _BASE,
            json={"provider": "anthropic", "model": "claude-3-opus-20240229", "api_key": "sk-ant-xyz"},
            headers=headers,
        )
        assert put2.status_code == 200
        assert put2.json()["provider"] == "anthropic"

        # 5. Verify overwrite — GET should show Anthropic.
        get2 = await client.get(_BASE, headers=headers)
        assert get2.json()["provider"] == "anthropic"

        # 6. Test connection with mocked provider.
        from app.llm.provider_base import LLMResponse

        mock_response = LLMResponse(
            content="ok",
            model_used="claude-3-opus-20240229",
            tokens_used=3,
            finish_reason="stop",
            latency_ms=33.3,
        )

        with patch(
            "app.settings.llm_service.get_provider",
            return_value=AsyncMock(
                generate=AsyncMock(return_value=mock_response),
            ),
        ):
            test_resp = await client.post(f"{_BASE}/test", headers=headers)
            assert test_resp.status_code == 200
            assert test_resp.json()["success"] is True
            assert test_resp.json()["model_used"] == "claude-3-opus-20240229"
