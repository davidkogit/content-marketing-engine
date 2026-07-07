"""
Integration tests for brand rules API endpoints.

Tests reading, updating, and previewing brand rules (tone, compliance,
style) stored as markdown files.  Verifies cache invalidation on update,
role enforcement (only super_admin can write), and the preview endpoint.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import create_app

# ── Constants ───────────────────────────────────────────────────────────────

_TEST_SECRET: str = os.environ["SECRET_KEY"]

_VALID_RULES = {"tone", "compliance", "style"}


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


def _auth_header(tokens: dict) -> dict:
    """Return an Authorization header dict for the given tokens."""
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ── GET /settings/rules/{rule_name} ─────────────────────────────────────────


class TestGetRule:
    """Tests for GET /api/v1/settings/rules/{rule_name}."""

    async def test_get_tone_rule_returns_default_content(
        self, client: AsyncClient
    ) -> None:
        """Reading the tone rule returns default markdown content."""
        tokens = await _register_and_login(client)

        resp = await client.get(
            "/api/v1/settings/rules/tone",
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rule_name"] == "tone"
        assert "Brand Tone" in body["content"]
        assert len(body["content"]) > 50

    async def test_get_compliance_rule_returns_default_content(
        self, client: AsyncClient
    ) -> None:
        """Reading the compliance rule returns default markdown content."""
        tokens = await _register_and_login(client)

        resp = await client.get(
            "/api/v1/settings/rules/compliance",
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rule_name"] == "compliance"
        assert "Compliance Rules" in body["content"]

    async def test_get_style_rule_returns_default_content(
        self, client: AsyncClient
    ) -> None:
        """Reading the style rule returns default markdown content."""
        tokens = await _register_and_login(client)

        resp = await client.get(
            "/api/v1/settings/rules/style",
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rule_name"] == "style"
        assert "Brand Style" in body["content"]

    async def test_get_invalid_rule_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Requesting an invalid rule name returns 404."""
        tokens = await _register_and_login(client)

        resp = await client.get(
            "/api/v1/settings/rules/nonexistent",
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 404

    async def test_get_rule_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        """Unauthenticated requests return 401."""
        resp = await client.get("/api/v1/settings/rules/tone")
        assert resp.status_code == 401

    async def test_get_rule_any_authenticated_role_can_read(
        self, client: AsyncClient
    ) -> None:
        """Any authenticated user (not just super_admin) can read rules."""
        tokens = await _register_and_login(
            client, email="viewer@example.com", role="viewer"
        )

        resp = await client.get(
            "/api/v1/settings/rules/tone",
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200


# ── PUT /settings/rules/{rule_name} ─────────────────────────────────────────


class TestUpdateRule:
    """Tests for PUT /api/v1/settings/rules/{rule_name}."""

    async def test_update_tone_rule_succeeds(
        self, client: AsyncClient
    ) -> None:
        """A super_admin can update a brand rule's content."""
        tokens = await _register_and_login(client)

        new_content = "# Updated Tone\n\nBe more casual and friendly."
        resp = await client.put(
            "/api/v1/settings/rules/tone",
            json={"content": new_content},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rule_name"] == "tone"
        assert "updated" in body["message"].lower()

    async def test_update_rule_cache_invalidation(
        self, client: AsyncClient
    ) -> None:
        """After updating a rule, subsequent reads return the new content."""
        tokens = await _register_and_login(client)

        # Read original
        original = await client.get(
            "/api/v1/settings/rules/compliance",
            headers=_auth_header(tokens),
        )
        assert "Compliance Rules" in original.json()["content"]

        # Update
        new_content = "# New Compliance\n\nAll claims need two sources."
        await client.put(
            "/api/v1/settings/rules/compliance",
            json={"content": new_content},
            headers=_auth_header(tokens),
        )

        # Read again — should get new content
        updated = await client.get(
            "/api/v1/settings/rules/compliance",
            headers=_auth_header(tokens),
        )
        assert updated.json()["content"] == new_content

    async def test_update_rule_multiple_times(
        self, client: AsyncClient
    ) -> None:
        """Multiple updates to the same rule all persist correctly."""
        tokens = await _register_and_login(client)

        for i in range(3):
            content = f"# Version {i}\n\nContent iteration {i}."
            resp = await client.put(
                "/api/v1/settings/rules/style",
                json={"content": content},
                headers=_auth_header(tokens),
            )
            assert resp.status_code == 200

        # Read final version
        final = await client.get(
            "/api/v1/settings/rules/style",
            headers=_auth_header(tokens),
        )
        assert "Version 2" in final.json()["content"]

    async def test_update_all_three_rules(
        self, client: AsyncClient
    ) -> None:
        """All three brand rules can be updated independently."""
        tokens = await _register_and_login(client)

        for rule in ["tone", "compliance", "style"]:
            content = f"# Updated {rule}\n\nNew content for {rule}."
            resp = await client.put(
                f"/api/v1/settings/rules/{rule}",
                json={"content": content},
                headers=_auth_header(tokens),
            )
            assert resp.status_code == 200

        # Verify all three changed
        for rule in ["tone", "compliance", "style"]:
            get_resp = await client.get(
                f"/api/v1/settings/rules/{rule}",
                headers=_auth_header(tokens),
            )
            assert f"Updated {rule}" in get_resp.json()["content"]

    async def test_update_invalid_rule_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Updating an invalid rule name returns 404."""
        tokens = await _register_and_login(client)

        resp = await client.put(
            "/api/v1/settings/rules/nonexistent",
            json={"content": "Some content."},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 404

    async def test_update_missing_content_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Missing the 'content' field returns 422."""
        tokens = await _register_and_login(client)

        resp = await client.put(
            "/api/v1/settings/rules/tone",
            json={},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 422

    async def test_update_empty_content_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Empty content returns 422."""
        tokens = await _register_and_login(client)

        resp = await client.put(
            "/api/v1/settings/rules/tone",
            json={"content": ""},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 422

    async def test_update_non_admin_returns_403(
        self, client: AsyncClient
    ) -> None:
        """A non-super_admin cannot update brand rules."""
        tokens = await _register_and_login(
            client, email="editor@example.com", role="editor"
        )

        resp = await client.put(
            "/api/v1/settings/rules/tone",
            json={"content": "Malicious content!"},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 403

    async def test_update_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        """Unauthenticated update requests return 401."""
        resp = await client.put(
            "/api/v1/settings/rules/tone",
            json={"content": "Some content."},
        )
        assert resp.status_code == 401


# ── POST /settings/rules/{rule_name}/preview ────────────────────────────────


class TestPreviewRule:
    """Tests for POST /api/v1/settings/rules/{rule_name}/preview."""

    async def test_preview_returns_prompt_with_proposed_content(
        self, client: AsyncClient
    ) -> None:
        """Preview endpoint returns a sample prompt with the proposed content."""
        tokens = await _register_and_login(client)

        proposed = "# Preview Tone\n\nTest preview content."
        resp = await client.post(
            "/api/v1/settings/rules/tone/preview",
            json={"content": proposed},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rule_name"] == "tone"
        assert body["proposed_content"] == proposed
        assert "sample_prompt" in body
        assert proposed in body["sample_prompt"]
        assert "diff_summary" in body

    async def test_preview_includes_current_content(
        self, client: AsyncClient
    ) -> None:
        """Preview response includes the current (existing) rule content."""
        tokens = await _register_and_login(client)

        # First update the rule so we have a known current state
        await client.put(
            "/api/v1/settings/rules/compliance",
            json={"content": "# Current\n\nKnown state."},
            headers=_auth_header(tokens),
        )

        # Now preview a change
        proposed = "# Proposed\n\nProposed state."
        resp = await client.post(
            "/api/v1/settings/rules/compliance/preview",
            json={"content": proposed},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_content"] == "# Current\n\nKnown state."
        assert body["proposed_content"] == proposed

    async def test_preview_with_sample_input(
        self, client: AsyncClient
    ) -> None:
        """Preview accepts optional sample product input for context."""
        tokens = await _register_and_login(client)

        sample = "SuperWidget 5000 — a premium widget for enterprise."
        resp = await client.post(
            "/api/v1/settings/rules/style/preview",
            json={
                "content": "# Style v2\n\nUse emoji.",
                "sample_input": sample,
            },
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert sample in body["sample_prompt"]

    async def test_preview_diff_summary_detects_added_lines(
        self, client: AsyncClient
    ) -> None:
        """The diff summary detects added lines in the proposed content."""
        tokens = await _register_and_login(client)

        # Current content is the default. Propose a much longer version.
        proposed = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7\nLine 8"
        resp = await client.post(
            "/api/v1/settings/rules/tone/preview",
            json={"content": proposed},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "line(s) added" in body["diff_summary"].lower()

    async def test_preview_invalid_rule_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Previewing an invalid rule returns 404."""
        tokens = await _register_and_login(client)

        resp = await client.post(
            "/api/v1/settings/rules/nonexistent/preview",
            json={"content": "Some content."},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 404

    async def test_preview_missing_content_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Missing 'content' field returns 422."""
        tokens = await _register_and_login(client)

        resp = await client.post(
            "/api/v1/settings/rules/tone/preview",
            json={},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 422

    async def test_preview_non_admin_returns_403(
        self, client: AsyncClient
    ) -> None:
        """A non-super_admin cannot preview rule changes."""
        tokens = await _register_and_login(
            client, email="editor@example.com", role="editor"
        )

        resp = await client.post(
            "/api/v1/settings/rules/tone/preview",
            json={"content": "Preview content."},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 403

    async def test_preview_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        """Unauthenticated preview requests return 401."""
        resp = await client.post(
            "/api/v1/settings/rules/tone/preview",
            json={"content": "Some content."},
        )
        assert resp.status_code == 401


# ── Edge Cases ──────────────────────────────────────────────────────────────


class TestBrandRulesEdgeCases:
    """Edge case and integration tests for brand rules."""

    async def test_rules_are_independent(
        self, client: AsyncClient
    ) -> None:
        """Updating one rule does not affect the others."""
        tokens = await _register_and_login(client)

        # Read all defaults
        tone_before = await client.get(
            "/api/v1/settings/rules/tone",
            headers=_auth_header(tokens),
        )
        compliance_before = await client.get(
            "/api/v1/settings/rules/compliance",
            headers=_auth_header(tokens),
        )
        style_before = await client.get(
            "/api/v1/settings/rules/style",
            headers=_auth_header(tokens),
        )

        # Update only tone
        new_tone = "# Custom Tone\n\nBe witty."
        await client.put(
            "/api/v1/settings/rules/tone",
            json={"content": new_tone},
            headers=_auth_header(tokens),
        )

        # Verify tone changed, others unchanged
        tone_after = await client.get(
            "/api/v1/settings/rules/tone",
            headers=_auth_header(tokens),
        )
        compliance_after = await client.get(
            "/api/v1/settings/rules/compliance",
            headers=_auth_header(tokens),
        )
        style_after = await client.get(
            "/api/v1/settings/rules/style",
            headers=_auth_header(tokens),
        )

        assert tone_after.json()["content"] == new_tone
        assert compliance_after.json()["content"] == compliance_before.json()["content"]
        assert style_after.json()["content"] == style_before.json()["content"]

    async def test_large_rule_content_handled(
        self, client: AsyncClient
    ) -> None:
        """Large rule content (10k+ chars) is handled correctly."""
        tokens = await _register_and_login(client)

        large_content = "# Big Rule\n\n" + ("Line of content. " * 1000)
        resp = await client.put(
            "/api/v1/settings/rules/compliance",
            json={"content": large_content},
            headers=_auth_header(tokens),
        )
        assert resp.status_code == 200

        # Read back
        get_resp = await client.get(
            "/api/v1/settings/rules/compliance",
            headers=_auth_header(tokens),
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["content"] == large_content
