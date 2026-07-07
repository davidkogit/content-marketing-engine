"""
Integration tests for the workflow API endpoints.

Uses an in-memory SQLite database and httpx AsyncClient to exercise
the full Kanban board view, stage transitions, approve/reject shortcuts,
history endpoint, and role-based auth enforcement.
"""

from __future__ import annotations

import asyncio
import os

# ── Ensure required env vars are set BEFORE any app imports ──────────────
os.environ.setdefault(
    "SECRET_KEY",
    "test-secret-key-that-is-at-least-32-characters-long!!",
)
os.environ.setdefault("LLM_API_KEY", "test-llm-api-key")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.jwt_service import JWTService
from app.database import Base, get_db
from app.main import create_app
from app.models.user import User, UserRole

# ── Constants ───────────────────────────────────────────────────────────────

_TEST_SECRET: str = os.environ["SECRET_KEY"]

# ── Test Application Factory ─────────────────────────────────────────────────


def _build_test_app(*, db_override=None):
    app = create_app()
    if db_override is not None:
        app.dependency_overrides[get_db] = db_override
    return app


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def engine():
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
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncClient:
    async def override_get_db():
        yield db_session

    app = _build_test_app(db_override=override_get_db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── User Seeding ─────────────────────────────────────────────────────────────

_ROLE_USER_IDS: dict[str, int] = {
    "admin": 1,
    "viewer": 2,
    "editor": 3,
    "super_admin": 4,
}

_ROLE_TO_USER_ROLE: dict[str, UserRole] = {
    "admin": UserRole.ADMIN,
    "viewer": UserRole.VIEWER,
    "editor": UserRole.EDITOR,
    "super_admin": UserRole.SUPER_ADMIN,
}


@pytest.fixture(scope="function", autouse=True)
async def _seed_users(db_session: AsyncSession) -> None:
    """Ensure one user per role exists in the database before each test."""
    for role_str, role_enum in _ROLE_TO_USER_ROLE.items():
        user = User(
            id=_ROLE_USER_IDS[role_str],
            email=f"{role_str}@test.com",
            hashed_password="hashed-placeholder",
            role=role_enum,
            is_active=True,
        )
        db_session.add(user)
    await db_session.flush()


# ── Token Helpers ────────────────────────────────────────────────────────────

_jwt_svc = JWTService(secret_key=_TEST_SECRET)


async def _token(role: str, user_id: int | None = None) -> str:
    uid = user_id if user_id is not None else _ROLE_USER_IDS.get(role, 1)
    return await _jwt_svc.create_access_token(
        user_id=uid, email=f"{role}@test.com", role=role
    )


async def _auth_headers(role: str, user_id: int | None = None) -> dict:
    t = await _token(role, user_id)
    return {"Authorization": f"Bearer {t}"}


# ── Product Helpers ──────────────────────────────────────────────────────────


async def _create_product(
    client: AsyncClient,
    sku: str = "SKU-001",
    name: str = "Test Product",
    role: str = "admin",
) -> int:
    """Create a product via the API and return its ID."""
    resp = await client.post(
        "/api/v1/products",
        json={"sku": sku, "name": name},
        headers=await _auth_headers(role),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _advance_product(
    client: AsyncClient,
    product_id: int,
    to_stage: str,
    role: str = "admin",
    comment: str | None = None,
) -> dict:
    """Transition a product to *to_stage* via the generic transition endpoint."""
    body: dict = {"to_stage": to_stage}
    if comment:
        body["comment"] = comment
    resp = await client.post(
        f"/api/v1/workflow/products/{product_id}/transition",
        json=body,
        headers=await _auth_headers(role),
    )
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# Board endpoint
# ══════════════════════════════════════════════════════════════════════════════


class TestBoard:
    """Tests for GET /api/v1/workflow/board."""

    async def test_board_returns_all_columns_even_empty(self, client):
        """An empty database still returns all 5 workflow columns."""
        resp = await client.get(
            "/api/v1/workflow/board",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["columns"]) == 5
        stages = [c["stage"] for c in body["columns"]]
        assert stages == ["ingest", "draft", "review", "approved", "exported"]
        for col in body["columns"]:
            assert col["count"] == 0
            assert col["products"] == []

    async def test_board_groups_products_by_stage(self, client):
        """Products appear in the correct Kanban columns."""
        await _create_product(client, sku="ING-A", name="Ingest A", role="admin")

        # Create a second product and advance it to draft.
        pid2 = await _create_product(client, sku="DRF-B", name="Draft B", role="admin")
        adv = await _advance_product(client, pid2, "draft", role="editor")
        assert adv.status_code == 200

        # Create a third product and advance to review.
        pid3 = await _create_product(client, sku="REV-C", name="Review C", role="admin")
        await _advance_product(client, pid3, "draft", role="editor")
        await _advance_product(client, pid3, "review", role="editor")

        resp = await client.get(
            "/api/v1/workflow/board",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()

        cols = {c["stage"]: c for c in body["columns"]}
        assert cols["ingest"]["count"] == 1
        assert cols["draft"]["count"] == 1
        assert cols["review"]["count"] == 1
        assert cols["approved"]["count"] == 0
        assert cols["exported"]["count"] == 0

        assert cols["ingest"]["products"][0]["sku"] == "ING-A"
        assert cols["draft"]["products"][0]["sku"] == "DRF-B"
        assert cols["review"]["products"][0]["sku"] == "REV-C"

    async def test_board_requires_auth(self, client):
        """Board endpoint rejects unauthenticated requests."""
        resp = await client.get("/api/v1/workflow/board")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Transition endpoint
# ══════════════════════════════════════════════════════════════════════════════


class TestTransition:
    """Tests for POST /api/v1/workflow/products/{id}/transition."""

    async def test_valid_transition_returns_response(self, client):
        """Transitioning ingest → draft with editor role succeeds."""
        pid = await _create_product(client, sku="T-01", name="Transition Test")
        resp = await _advance_product(client, pid, "draft", role="editor")
        assert resp.status_code == 200
        body = resp.json()
        assert body["product_id"] == pid
        assert body["from_stage"] == "ingest"
        assert body["to_stage"] == "draft"
        assert body["version_number"] == 1
        assert body["comment"] is None

    async def test_transition_with_comment(self, client):
        """Optional comment is returned in the response."""
        pid = await _create_product(client, sku="T-02", name="With Comment")
        resp = await _advance_product(
            client, pid, "draft", role="editor", comment="Ready for drafting"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["comment"] == "Ready for drafting"

    async def test_transition_persists_stage_change(self, client):
        """After a successful transition, the product's stage is updated."""
        pid = await _create_product(client, sku="T-03", name="Persist Test")
        await _advance_product(client, pid, "draft", role="editor")

        # Verify via the product detail endpoint.
        get_r = await client.get(
            f"/api/v1/products/{pid}",
            headers=await _auth_headers("viewer"),
        )
        assert get_r.status_code == 200
        assert get_r.json()["workflow_stage"] == "draft"

    async def test_invalid_transition_returns_422(self, client):
        """Skipping a stage (ingest → review) returns 422."""
        pid = await _create_product(client, sku="T-04", name="Skip Test")
        resp = await _advance_product(client, pid, "review", role="admin")
        assert resp.status_code == 422

    async def test_insufficient_role_returns_422(self, client):
        """Viewer cannot transition ingest → draft (requires editor+)."""
        pid = await _create_product(client, sku="T-05", name="Role Test")
        resp = await _advance_product(client, pid, "draft", role="viewer")
        assert resp.status_code == 422

    async def test_transition_nonexistent_product_404(self, client):
        """Transitioning a non-existent product returns 404."""
        resp = await client.post(
            "/api/v1/workflow/products/9999/transition",
            json={"to_stage": "draft"},
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 404

    async def test_transition_requires_auth(self, client):
        """Transition endpoint rejects unauthenticated requests."""
        resp = await client.post(
            "/api/v1/workflow/products/1/transition",
            json={"to_stage": "draft"},
        )
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Approve shortcut
# ══════════════════════════════════════════════════════════════════════════════


class TestApprove:
    """Tests for POST /api/v1/workflow/products/{id}/approve."""

    async def test_admin_can_approve_from_review(self, client):
        """Admin can use the approve shortcut to move review → approved."""
        pid = await _create_product(client, sku="APR-01", name="Approve Test")
        await _advance_product(client, pid, "draft", role="editor")
        await _advance_product(client, pid, "review", role="editor")

        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/approve",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["from_stage"] == "review"
        assert body["to_stage"] == "approved"

    async def test_super_admin_can_approve(self, client):
        """Super admin can also use the approve shortcut."""
        pid = await _create_product(client, sku="APR-02", name="SA Approve")
        await _advance_product(client, pid, "draft", role="editor")
        await _advance_product(client, pid, "review", role="editor")

        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/approve",
            headers=await _auth_headers("super_admin"),
        )
        assert resp.status_code == 200

    async def test_editor_cannot_approve(self, client):
        """Editor role is rejected by the approve shortcut (requires admin+)."""
        pid = await _create_product(client, sku="APR-03", name="Editor Approve")
        await _advance_product(client, pid, "draft", role="editor")
        await _advance_product(client, pid, "review", role="editor")

        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/approve",
            headers=await _auth_headers("editor"),
        )
        # Role gate enforced by require_role — returns 403.
        assert resp.status_code == 403

    async def test_viewer_cannot_approve(self, client):
        """Viewer role is rejected by the approve shortcut."""
        pid = await _create_product(client, sku="APR-04", name="Viewer Approve")
        await _advance_product(client, pid, "draft", role="admin")

        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/approve",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 403

    async def test_approve_from_wrong_stage_fails(self, client):
        """Approving a product that is not in review returns 422."""
        pid = await _create_product(client, sku="APR-05", name="Wrong Stage")

        # Product is in ingest — approve should fail.
        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/approve",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 422

    async def test_approve_requires_auth(self, client):
        """Approve endpoint rejects unauthenticated requests."""
        resp = await client.post("/api/v1/workflow/products/1/approve")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Request-changes shortcut
# ══════════════════════════════════════════════════════════════════════════════


class TestRequestChanges:
    """Tests for POST /api/v1/workflow/products/{id}/request-changes."""

    async def test_editor_can_request_changes(self, client):
        """Editor can use the request-changes shortcut to move review → draft."""
        pid = await _create_product(client, sku="RC-01", name="Request Changes")
        await _advance_product(client, pid, "draft", role="editor")
        await _advance_product(client, pid, "review", role="editor")

        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/request-changes",
            json={"comment": "Please add more detail to the product description."},
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["from_stage"] == "review"
        assert body["to_stage"] == "draft"
        assert "Please add more detail" in body["comment"]

    async def test_admin_can_request_changes(self, client):
        """Admin can also request changes."""
        pid = await _create_product(client, sku="RC-02", name="Admin RC")
        await _advance_product(client, pid, "draft", role="editor")
        await _advance_product(client, pid, "review", role="editor")

        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/request-changes",
            json={"comment": "Needs revision on specs."},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200

    async def test_request_changes_requires_comment(self, client):
        """Requesting changes without a comment returns 422 validation error."""
        pid = await _create_product(client, sku="RC-03", name="No Comment")
        await _advance_product(client, pid, "draft", role="editor")
        await _advance_product(client, pid, "review", role="editor")

        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/request-changes",
            json={"comment": ""},  # empty — fails min_length=1
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 422

    async def test_viewer_cannot_request_changes(self, client):
        """Viewer role is rejected by the request-changes shortcut."""
        pid = await _create_product(client, sku="RC-04", name="Viewer RC")
        await _advance_product(client, pid, "draft", role="admin")
        await _advance_product(client, pid, "review", role="admin")

        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/request-changes",
            json={"comment": "Needs changes."},
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 403

    async def test_request_changes_from_wrong_stage_fails(self, client):
        """Requesting changes on a product not in review returns 422."""
        pid = await _create_product(client, sku="RC-05", name="Wrong Stage RC")

        # Product is still in ingest.
        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/request-changes",
            json={"comment": "Start over."},
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 422

    async def test_request_changes_requires_auth(self, client):
        """Request-changes endpoint rejects unauthenticated requests."""
        resp = await client.post(
            "/api/v1/workflow/products/1/request-changes",
            json={"comment": "Needs changes."},
        )
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# History endpoint
# ══════════════════════════════════════════════════════════════════════════════


class TestHistory:
    """Tests for GET /api/v1/workflow/products/{id}/history."""

    async def test_history_returns_transition_timeline(self, client):
        """After multiple transitions, the history returns them in order."""
        pid = await _create_product(client, sku="HST-01", name="History Test")
        await _advance_product(client, pid, "draft", role="editor")
        await _advance_product(client, pid, "review", role="editor")
        await _advance_product(client, pid, "draft", role="editor",
                               comment="Needs more content")

        resp = await client.get(
            f"/api/v1/workflow/products/{pid}/history",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3

        # Check chronological order.
        assert body[0]["from_stage"] == "ingest"
        assert body[0]["to_stage"] == "draft"
        assert body[1]["from_stage"] == "draft"
        assert body[1]["to_stage"] == "review"
        assert body[2]["from_stage"] == "review"
        assert body[2]["to_stage"] == "draft"
        assert "Needs more content" in body[2]["comment"]

    async def test_history_empty_for_no_transitions(self, client):
        """A product with no transitions returns an empty list."""
        pid = await _create_product(client, sku="HST-02", name="No History")
        resp = await client.get(
            f"/api/v1/workflow/products/{pid}/history",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_history_nonexistent_product_404(self, client):
        """Requesting history for a non-existent product returns 404."""
        resp = await client.get(
            "/api/v1/workflow/products/9999/history",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 404

    async def test_history_requires_auth(self, client):
        """History endpoint rejects unauthenticated requests."""
        resp = await client.get("/api/v1/workflow/products/1/history")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Full workflow lifecycle
# ══════════════════════════════════════════════════════════════════════════════


class TestFullWorkflowLifecycle:
    """End-to-end tests through the complete Kanban pipeline."""

    async def test_full_ingest_to_exported(self, client):
        """Happy path: ingest → draft → review → approved → exported."""
        pid = await _create_product(client, sku="FULL-01", name="Full Lifecycle")

        # ingest → draft (editor)
        r1 = await _advance_product(client, pid, "draft", role="editor")
        assert r1.status_code == 200
        assert r1.json()["to_stage"] == "draft"

        # draft → review (editor)
        r2 = await _advance_product(client, pid, "review", role="editor")
        assert r2.status_code == 200
        assert r2.json()["to_stage"] == "review"

        # review → approved (admin)
        r3 = await client.post(
            f"/api/v1/workflow/products/{pid}/approve",
            headers=await _auth_headers("admin"),
        )
        assert r3.status_code == 200
        assert r3.json()["to_stage"] == "approved"

        # approved → exported (admin)
        r4 = await _advance_product(client, pid, "exported", role="admin")
        assert r4.status_code == 200
        assert r4.json()["to_stage"] == "exported"

        # Verify history has 4 entries.
        hist_r = await client.get(
            f"/api/v1/workflow/products/{pid}/history",
            headers=await _auth_headers("viewer"),
        )
        assert len(hist_r.json()) == 4

    async def test_reject_path_review_back_to_draft(self, client):
        """Rejection path: ingest → draft → review → draft (request changes)."""
        pid = await _create_product(client, sku="REJ-01", name="Reject Path")
        await _advance_product(client, pid, "draft", role="editor")
        await _advance_product(client, pid, "review", role="editor")

        # Request changes sends it back to draft.
        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/request-changes",
            json={"comment": "Rework section 3."},
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 200
        assert resp.json()["to_stage"] == "draft"

        # Verify product is back in draft.
        get_r = await client.get(
            f"/api/v1/products/{pid}",
            headers=await _auth_headers("viewer"),
        )
        assert get_r.json()["workflow_stage"] == "draft"

    async def test_super_admin_can_reset_to_ingest(self, client):
        """Super admin can reset any product back to ingest via the transition
        endpoint."""
        pid = await _create_product(client, sku="RST-01", name="Reset Test")
        await _advance_product(client, pid, "draft", role="editor")
        await _advance_product(client, pid, "review", role="editor")

        # Super admin resets to ingest.
        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/transition",
            json={"to_stage": "ingest"},
            headers=await _auth_headers("super_admin"),
        )
        assert resp.status_code == 200
        assert resp.json()["to_stage"] == "ingest"

        # Verify product is back at ingest.
        get_r = await client.get(
            f"/api/v1/products/{pid}",
            headers=await _auth_headers("viewer"),
        )
        assert get_r.json()["workflow_stage"] == "ingest"

    async def test_admin_cannot_reset_to_ingest(self, client):
        """Non-super_admin cannot reset to ingest (returns 422)."""
        pid = await _create_product(client, sku="RST-02", name="Admin Reset")
        await _advance_product(client, pid, "draft", role="editor")

        resp = await client.post(
            f"/api/v1/workflow/products/{pid}/transition",
            json={"to_stage": "ingest"},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 422

    async def test_multiple_reject_then_approve(self, client):
        """Reject multiple times, then finally approve."""
        pid = await _create_product(client, sku="MULTI", name="Multi Reject")
        await _advance_product(client, pid, "draft", role="editor")
        await _advance_product(client, pid, "review", role="editor")

        # Reject
        r1 = await client.post(
            f"/api/v1/workflow/products/{pid}/request-changes",
            json={"comment": "First revision."},
            headers=await _auth_headers("editor"),
        )
        assert r1.status_code == 200
        assert r1.json()["to_stage"] == "draft"

        # Move back to review
        await _advance_product(client, pid, "review", role="editor")

        # Reject again
        r2 = await client.post(
            f"/api/v1/workflow/products/{pid}/request-changes",
            json={"comment": "Second revision."},
            headers=await _auth_headers("admin"),
        )
        assert r2.status_code == 200

        # Move to review again and approve
        await _advance_product(client, pid, "review", role="editor")
        r3 = await client.post(
            f"/api/v1/workflow/products/{pid}/approve",
            headers=await _auth_headers("admin"),
        )
        assert r3.status_code == 200
        assert r3.json()["to_stage"] == "approved"

        # History should show 6 transitions.
        hist_r = await client.get(
            f"/api/v1/workflow/products/{pid}/history",
            headers=await _auth_headers("viewer"),
        )
        assert len(hist_r.json()) == 6
