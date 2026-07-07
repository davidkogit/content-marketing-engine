"""
Integration tests for the Segments CRUD API.

Uses an in-memory SQLite database and httpx AsyncClient to exercise the
full segments router: create, list, get, update, delete, and role-based
access enforcement.
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
from app.models.segment import Segment
from app.models.product import Product, WorkflowStage

# ── Constants ───────────────────────────────────────────────────────────────

_SEGMENTS_PREFIX = "/api/v1/segments"


# ── Test Application Factory ────────────────────────────────────────────────


def _build_test_app(*, db_override=None):
    """Create a FastAPI app with auth and segments routers and an overridable DB."""
    app = create_app()

    if db_override is not None:
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


# ── Auth Helpers ────────────────────────────────────────────────────────────


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


async def _register_and_get_token(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "securepass123",
    role: str = "admin",
) -> str:
    """Register a user and return the access token."""
    tokens = await _register(client, email=email, password=password, role=role)
    return tokens["access_token"]


def _auth_header(token: str) -> dict:
    """Build an Authorization header dict for a Bearer token."""
    return {"Authorization": f"Bearer {token}"}


# ── Segment CRUD Helpers ────────────────────────────────────────────────────


async def _create_segment(
    client: AsyncClient,
    token: str,
    *,
    name: str = "Enterprise",
    description: str | None = None,
    target_audience: str | None = None,
    tone: str | None = None,
) -> dict:
    """Create a segment via the API and return the parsed JSON response."""
    payload: dict = {"name": name}
    if description is not None:
        payload["description"] = description
    if target_audience is not None:
        payload["target_audience"] = target_audience
    if tone is not None:
        payload["tone"] = tone

    resp = await client.post(
        _SEGMENTS_PREFIX,
        json=payload,
        headers=_auth_header(token),
    )
    return resp.json()


async def _create_product(
    db_session: AsyncSession,
    *,
    sku: str = "SKU-001",
    name: str = "Test Product",
    segment_id: int | None = None,
) -> Product:
    """Insert a product directly into the database (bypasses API)."""
    product = Product(
        sku=sku,
        name=name,
        segment_id=segment_id,
        workflow_stage=WorkflowStage.INGEST,
    )
    db_session.add(product)
    await db_session.flush()
    return product


# ═══════════════════════════════════════════════════════════════════════════
#  GET /segments — List all segments
# ═══════════════════════════════════════════════════════════════════════════


class TestListSegments:
    """Tests for GET /segments."""

    async def test_list_returns_empty_when_no_segments(
        self, client: AsyncClient
    ) -> None:
        """Listing segments with no data returns an empty list."""
        token = await _register_and_get_token(client)
        resp = await client.get(
            _SEGMENTS_PREFIX,
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_returns_all_segments(
        self, client: AsyncClient
    ) -> None:
        """Listing returns all created segments with product counts."""
        token = await _register_and_get_token(client)

        await _create_segment(client, token, name="Enterprise")
        await _create_segment(client, token, name="SMB")

        resp = await client.get(
            _SEGMENTS_PREFIX,
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        names = {s["name"] for s in body}
        assert names == {"Enterprise", "SMB"}
        for seg in body:
            assert seg["product_count"] == 0

    async def test_list_requires_authentication(
        self, client: AsyncClient
    ) -> None:
        """Listing segments without a token returns 401."""
        resp = await client.get(_SEGMENTS_PREFIX)
        assert resp.status_code == 401

    async def test_list_viewer_can_access(
        self, client: AsyncClient
    ) -> None:
        """A viewer can list segments."""
        token = await _register_and_get_token(client, role="viewer")
        await _create_segment(client, token, name="Enterprise")

        # Use a more privileged token to create, viewer to list
        admin_token = await _register_and_get_token(
            client, email="admin2@ex.com", role="admin"
        )
        await _create_segment(client, admin_token, name="Enterprise")

        resp = await client.get(
            _SEGMENTS_PREFIX,
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ═══════════════════════════════════════════════════════════════════════════
#  POST /segments — Create a segment
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateSegment:
    """Tests for POST /segments."""

    async def test_create_returns_201(
        self, client: AsyncClient
    ) -> None:
        """Successful creation returns 201 with full segment data."""
        token = await _register_and_get_token(client)
        resp = await client.post(
            _SEGMENTS_PREFIX,
            json={
                "name": "Enterprise",
                "description": "Fortune 500 companies",
                "target_audience": "CTOs and VPs",
                "tone": "Professional",
            },
            headers=_auth_header(token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Enterprise"
        assert body["description"] == "Fortune 500 companies"
        assert body["target_audience"] == "CTOs and VPs"
        assert body["tone"] == "Professional"
        assert body["product_count"] == 0
        assert "id" in body
        assert "created_at" in body

    async def test_create_with_minimal_fields(
        self, client: AsyncClient
    ) -> None:
        """Creating with only a name sets other fields to None."""
        token = await _register_and_get_token(client)
        resp = await client.post(
            _SEGMENTS_PREFIX,
            json={"name": "Minimal"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Minimal"
        assert body["description"] is None
        assert body["target_audience"] is None
        assert body["tone"] is None

    async def test_create_duplicate_name_returns_409(
        self, client: AsyncClient
    ) -> None:
        """Creating two segments with the same name returns 409."""
        token = await _register_and_get_token(client)
        await _create_segment(client, token, name="Duplicate")

        resp = await client.post(
            _SEGMENTS_PREFIX,
            json={"name": "Duplicate"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"].lower()

    async def test_create_empty_name_returns_422(
        self, client: AsyncClient
    ) -> None:
        """An empty name is rejected by Pydantic validation (min_length=1)."""
        token = await _register_and_get_token(client)
        resp = await client.post(
            _SEGMENTS_PREFIX,
            json={"name": ""},
            headers=_auth_header(token),
        )
        assert resp.status_code == 422

    async def test_create_missing_name_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Missing required 'name' field returns 422."""
        token = await _register_and_get_token(client)
        resp = await client.post(
            _SEGMENTS_PREFIX,
            json={},
            headers=_auth_header(token),
        )
        assert resp.status_code == 422

    async def test_create_requires_admin_role(
        self, client: AsyncClient
    ) -> None:
        """An editor cannot create a segment."""
        token = await _register_and_get_token(client, role="editor")
        resp = await client.post(
            _SEGMENTS_PREFIX,
            json={"name": "Forbidden"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 403

    async def test_create_viewer_cannot_create(
        self, client: AsyncClient
    ) -> None:
        """A viewer cannot create a segment."""
        token = await _register_and_get_token(client, role="viewer")
        resp = await client.post(
            _SEGMENTS_PREFIX,
            json={"name": "Forbidden"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 403

    async def test_create_super_admin_can_create(
        self, client: AsyncClient
    ) -> None:
        """A super_admin can create a segment."""
        token = await _register_and_get_token(client, role="super_admin")
        resp = await client.post(
            _SEGMENTS_PREFIX,
            json={"name": "SuperSegment"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 201


# ═══════════════════════════════════════════════════════════════════════════
#  GET /segments/{id} — Get a single segment
# ═══════════════════════════════════════════════════════════════════════════


class TestGetSegment:
    """Tests for GET /segments/{id}."""

    async def test_get_returns_segment_with_product_count(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Getting a segment returns its data and product count."""
        token = await _register_and_get_token(client)
        created = await _create_segment(client, token, name="Enterprise")
        seg_id = created["id"]

        # Assign products to the segment
        await _create_product(db_session, sku="SKU-1", name="Prod A", segment_id=seg_id)
        await _create_product(db_session, sku="SKU-2", name="Prod B", segment_id=seg_id)

        resp = await client.get(
            f"{_SEGMENTS_PREFIX}/{seg_id}",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Enterprise"
        assert body["product_count"] == 2

    async def test_get_nonexistent_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Requesting a non-existent segment ID returns 404."""
        token = await _register_and_get_token(client)
        resp = await client.get(
            f"{_SEGMENTS_PREFIX}/9999",
            headers=_auth_header(token),
        )
        assert resp.status_code == 404

    async def test_get_requires_authentication(
        self, client: AsyncClient
    ) -> None:
        """Getting a segment without a token returns 401."""
        resp = await client.get(f"{_SEGMENTS_PREFIX}/1")
        assert resp.status_code == 401

    async def test_get_viewer_can_access(
        self, client: AsyncClient
    ) -> None:
        """A viewer can retrieve a single segment."""
        admin_token = await _register_and_get_token(
            client, email="admin@ex.com", role="admin"
        )
        created = await _create_segment(client, admin_token, name="Public")
        seg_id = created["id"]

        viewer_token = await _register_and_get_token(
            client, email="viewer@ex.com", role="viewer"
        )
        resp = await client.get(
            f"{_SEGMENTS_PREFIX}/{seg_id}",
            headers=_auth_header(viewer_token),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Public"


# ═══════════════════════════════════════════════════════════════════════════
#  PUT /segments/{id} — Update a segment
# ═══════════════════════════════════════════════════════════════════════════


class TestUpdateSegment:
    """Tests for PUT /segments/{id}."""

    async def test_update_name_succeeds(
        self, client: AsyncClient
    ) -> None:
        """Updating a segment's name returns the refreshed segment."""
        token = await _register_and_get_token(client)
        created = await _create_segment(client, token, name="Old Name")
        seg_id = created["id"]

        resp = await client.put(
            f"{_SEGMENTS_PREFIX}/{seg_id}",
            json={"name": "New Name"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "New Name"

    async def test_update_partial_fields(
        self, client: AsyncClient
    ) -> None:
        """Only the provided fields are updated; others remain unchanged."""
        token = await _register_and_get_token(client)
        created = await _create_segment(
            client, token, name="Full", description="Desc", target_audience="TA", tone="T"
        )
        seg_id = created["id"]

        resp = await client.put(
            f"{_SEGMENTS_PREFIX}/{seg_id}",
            json={"description": "Updated Desc"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["description"] == "Updated Desc"
        assert body["name"] == "Full"  # Unchanged
        assert body["target_audience"] == "TA"  # Unchanged
        assert body["tone"] == "T"  # Unchanged

    async def test_update_duplicate_name_returns_409(
        self, client: AsyncClient
    ) -> None:
        """Updating to a name that already exists returns 409."""
        token = await _register_and_get_token(client)
        await _create_segment(client, token, name="First")
        created = await _create_segment(client, token, name="Second")
        seg_id = created["id"]

        resp = await client.put(
            f"{_SEGMENTS_PREFIX}/{seg_id}",
            json={"name": "First"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 409

    async def test_update_nonexistent_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Updating a non-existent segment returns 404."""
        token = await _register_and_get_token(client)
        resp = await client.put(
            f"{_SEGMENTS_PREFIX}/9999",
            json={"name": "Ghost"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 404

    async def test_update_requires_admin_role(
        self, client: AsyncClient
    ) -> None:
        """An editor cannot update a segment."""
        admin_token = await _register_and_get_token(
            client, email="admin@ex.com", role="admin"
        )
        created = await _create_segment(client, admin_token, name="Target")
        seg_id = created["id"]

        editor_token = await _register_and_get_token(
            client, email="editor@ex.com", role="editor"
        )
        resp = await client.put(
            f"{_SEGMENTS_PREFIX}/{seg_id}",
            json={"name": "Hacked"},
            headers=_auth_header(editor_token),
        )
        assert resp.status_code == 403

    async def test_update_viewer_cannot_update(
        self, client: AsyncClient
    ) -> None:
        """A viewer cannot update a segment."""
        admin_token = await _register_and_get_token(
            client, email="admin@ex.com", role="admin"
        )
        created = await _create_segment(client, admin_token, name="Target")
        seg_id = created["id"]

        viewer_token = await _register_and_get_token(
            client, email="viewer@ex.com", role="viewer"
        )
        resp = await client.put(
            f"{_SEGMENTS_PREFIX}/{seg_id}",
            json={"name": "Hacked"},
            headers=_auth_header(viewer_token),
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
#  DELETE /segments/{id} — Delete a segment
# ═══════════════════════════════════════════════════════════════════════════


class TestDeleteSegment:
    """Tests for DELETE /segments/{id}."""

    async def test_delete_empty_segment_succeeds(
        self, client: AsyncClient
    ) -> None:
        """Deleting a segment with no assigned products returns 204."""
        token = await _register_and_get_token(client)
        created = await _create_segment(client, token, name="Deletable")
        seg_id = created["id"]

        resp = await client.delete(
            f"{_SEGMENTS_PREFIX}/{seg_id}",
            headers=_auth_header(token),
        )
        assert resp.status_code == 204

        # Verify the segment is gone
        get_resp = await client.get(
            f"{_SEGMENTS_PREFIX}/{seg_id}",
            headers=_auth_header(token),
        )
        assert get_resp.status_code == 404

    async def test_delete_with_products_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Deleting a segment with assigned products is blocked with 409."""
        token = await _register_and_get_token(client)
        created = await _create_segment(client, token, name="Occupied")
        seg_id = created["id"]

        await _create_product(db_session, sku="SKU-1", name="Prod", segment_id=seg_id)

        resp = await client.delete(
            f"{_SEGMENTS_PREFIX}/{seg_id}",
            headers=_auth_header(token),
        )
        assert resp.status_code == 409
        assert "product" in resp.json()["detail"].lower()

    async def test_delete_nonexistent_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Deleting a non-existent segment returns 404."""
        token = await _register_and_get_token(client)
        resp = await client.delete(
            f"{_SEGMENTS_PREFIX}/9999",
            headers=_auth_header(token),
        )
        assert resp.status_code == 404

    async def test_delete_requires_admin_role(
        self, client: AsyncClient
    ) -> None:
        """An editor cannot delete a segment."""
        admin_token = await _register_and_get_token(
            client, email="admin@ex.com", role="admin"
        )
        created = await _create_segment(client, admin_token, name="Target")
        seg_id = created["id"]

        editor_token = await _register_and_get_token(
            client, email="editor@ex.com", role="editor"
        )
        resp = await client.delete(
            f"{_SEGMENTS_PREFIX}/{seg_id}",
            headers=_auth_header(editor_token),
        )
        assert resp.status_code == 403

    async def test_delete_viewer_cannot_delete(
        self, client: AsyncClient
    ) -> None:
        """A viewer cannot delete a segment."""
        admin_token = await _register_and_get_token(
            client, email="admin@ex.com", role="admin"
        )
        created = await _create_segment(client, admin_token, name="Target")
        seg_id = created["id"]

        viewer_token = await _register_and_get_token(
            client, email="viewer@ex.com", role="viewer"
        )
        resp = await client.delete(
            f"{_SEGMENTS_PREFIX}/{seg_id}",
            headers=_auth_header(viewer_token),
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
#  Unauthenticated access — blanket 401 coverage
# ═══════════════════════════════════════════════════════════════════════════


class TestUnauthenticated:
    """Tests that all mutating endpoints return 401 without a token."""

    async def test_create_without_token_returns_401(
        self, client: AsyncClient
    ) -> None:
        """POST without token returns 401."""
        resp = await client.post(
            _SEGMENTS_PREFIX,
            json={"name": "NoAuth"},
        )
        assert resp.status_code == 401

    async def test_update_without_token_returns_401(
        self, client: AsyncClient
    ) -> None:
        """PUT without token returns 401."""
        resp = await client.put(
            f"{_SEGMENTS_PREFIX}/1",
            json={"name": "NoAuth"},
        )
        assert resp.status_code == 401

    async def test_delete_without_token_returns_401(
        self, client: AsyncClient
    ) -> None:
        """DELETE without token returns 401."""
        resp = await client.delete(f"{_SEGMENTS_PREFIX}/1")
        assert resp.status_code == 401
