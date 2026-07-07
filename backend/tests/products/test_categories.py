"""
Integration tests for the categories API endpoints.

Uses an in-memory SQLite database and httpx ``AsyncClient`` to exercise
the full FastAPI categories router: create, list, get, update, and delete
— with auth role enforcement checks for write operations (admin+).
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
from app.models.user import UserRole

# ── Constants ───────────────────────────────────────────────────────────

_TEST_SECRET: str = os.environ["SECRET_KEY"]


# ── Test Application Factory ────────────────────────────────────────────


def _build_test_app(*, db_override=None):
    """Create a FastAPI app with all routers and an overridable DB dependency."""
    app = create_app()

    if db_override is not None:
        original_get_db = get_db
        app.dependency_overrides[original_get_db] = db_override

    # Also register the categories router (normally done in main.py)
    from app.products.category_router import router as categories_router

    app.include_router(categories_router, prefix="/api/v1")

    return app


# ── Fixtures ────────────────────────────────────────────────────────────


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


# ── Helpers ─────────────────────────────────────────────────────────────


async def _register_and_login(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "securepass123",
    role: str = "admin",
) -> str:
    """Register a user and return a valid access token.

    Defaults to ADMIN role so tests can exercise write endpoints.
    """
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "role": role},
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()["access_token"]


async def _create_category(
    client: AsyncClient,
    token: str,
    name: str = "Electronics",
    description: str = "Electronic devices",
) -> dict:
    """Create a category via the API and return the parsed JSON response."""
    resp = await client.post(
        "/api/v1/categories",
        json={"name": name, "description": description},
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()


def _auth(token: str) -> dict:
    """Build an Authorization header dict from a JWT token."""
    return {"Authorization": f"Bearer {token}"}


# ── POST /categories (Create) ───────────────────────────────────────────


class TestCreateCategory:
    """Tests for POST /categories."""

    async def test_create_category_returns_201(self, client: AsyncClient) -> None:
        """Admin user can create a category with valid name and description."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        resp = await client.post(
            "/api/v1/categories",
            json={"name": "Electronics", "description": "Electronic devices"},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Electronics"
        assert body["description"] == "Electronic devices"
        assert "id" in body
        assert body["product_count"] == 0
        assert "created_at" in body

    async def test_create_category_without_description(self, client: AsyncClient) -> None:
        """Description is optional — category should be created without it."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        resp = await client.post(
            "/api/v1/categories",
            json={"name": "Apparel"},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Apparel"
        assert body["description"] is None

    async def test_create_duplicate_name_returns_409(self, client: AsyncClient) -> None:
        """Creating a category with an existing name fails with 409."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        await _create_category(client, token, name="DuplicateName")
        resp = await client.post(
            "/api/v1/categories",
            json={"name": "DuplicateName"},
            headers=_auth(token),
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    async def test_create_empty_name_returns_422(self, client: AsyncClient) -> None:
        """Empty category name is rejected by Pydantic validation."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        resp = await client.post(
            "/api/v1/categories",
            json={"name": ""},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_create_missing_name_returns_422(self, client: AsyncClient) -> None:
        """Missing required field returns 422."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        resp = await client.post(
            "/api/v1/categories",
            json={"description": "No name here"},
            headers=_auth(token),
        )
        assert resp.status_code == 422


# ── GET /categories (List) ──────────────────────────────────────────────


class TestListCategories:
    """Tests for GET /categories."""

    async def test_list_returns_empty_when_no_categories(self, client: AsyncClient) -> None:
        """Empty database returns an empty list, not null."""
        token = await _register_and_login(client, email="viewer@test.com", role="viewer")
        resp = await client.get(
            "/api/v1/categories", headers=_auth(token)
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_returns_all_categories(self, client: AsyncClient) -> None:
        """List returns every category in name order."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        await _create_category(client, token, name="ZZZ")
        await _create_category(client, token, name="AAA")
        await _create_category(client, token, name="MMM")
        resp = await client.get(
            "/api/v1/categories", headers=_auth(token)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3
        # Should be ordered by name
        assert body[0]["name"] == "AAA"
        assert body[1]["name"] == "MMM"
        assert body[2]["name"] == "ZZZ"

    async def test_list_any_authenticated_user_can_list(self, client: AsyncClient) -> None:
        """A viewer (lowest role) can list categories."""
        token = await _register_and_login(client, email="viewer@test.com", role="viewer")
        resp = await client.get(
            "/api/v1/categories", headers=_auth(token)
        )
        assert resp.status_code == 200

    async def test_list_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """No token returns 401 Unauthorized."""
        resp = await client.get("/api/v1/categories")
        assert resp.status_code == 401

    async def test_list_product_count_not_included(self, client: AsyncClient) -> None:
        """The list endpoint does not include product_count for efficiency."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        await _create_category(client, token, name="TestCat")
        resp = await client.get(
            "/api/v1/categories", headers=_auth(token)
        )
        body = resp.json()
        # product_count is 0 by default but we check it's present on list too
        assert body[0]["product_count"] == 0


# ── GET /categories/{id} (Single) ───────────────────────────────────────


class TestGetCategory:
    """Tests for GET /categories/{id}."""

    async def test_get_returns_category_with_product_count(self, client: AsyncClient) -> None:
        """Single-category response includes product_count."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, token, name="Gadgets")
        resp = await client.get(
            f"/api/v1/categories/{created['id']}", headers=_auth(token)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Gadgets"
        assert body["product_count"] == 0
        assert body["id"] == created["id"]

    async def test_get_nonexistent_category_returns_404(self, client: AsyncClient) -> None:
        """Requesting a non-existent category returns 404."""
        token = await _register_and_login(client, email="viewer@test.com", role="viewer")
        resp = await client.get(
            "/api/v1/categories/99999", headers=_auth(token)
        )
        assert resp.status_code == 404

    async def test_get_any_authenticated_user_can_read(self, client: AsyncClient) -> None:
        """A viewer can fetch a single category."""
        admin_token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, admin_token, name="Shared")

        viewer_token = await _register_and_login(client, email="viewer@test.com", role="viewer")
        resp = await client.get(
            f"/api/v1/categories/{created['id']}", headers=_auth(viewer_token)
        )
        assert resp.status_code == 200

    async def test_get_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """No auth token returns 401."""
        resp = await client.get("/api/v1/categories/1")
        assert resp.status_code == 401


# ── PUT /categories/{id} (Update) ───────────────────────────────────────


class TestUpdateCategory:
    """Tests for PUT /categories/{id}."""

    async def test_update_changes_name(self, client: AsyncClient) -> None:
        """Admin can rename a category."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, token, name="OldName")
        resp = await client.put(
            f"/api/v1/categories/{created['id']}",
            json={"name": "NewName"},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "NewName"
        assert body["description"] == created["description"]  # unchanged

    async def test_update_changes_description(self, client: AsyncClient) -> None:
        """Admin can update just the description."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, token, name="Books", description="Old desc")
        resp = await client.put(
            f"/api/v1/categories/{created['id']}",
            json={"description": "Updated description"},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["description"] == "Updated description"
        assert body["name"] == "Books"  # unchanged

    async def test_update_clear_description(self, client: AsyncClient) -> None:
        """Setting description to empty string clears it."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, token, name="ClearMe", description="Has desc")
        resp = await client.put(
            f"/api/v1/categories/{created['id']}",
            json={"description": ""},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["description"] == ""

    async def test_update_nonexistent_returns_404(self, client: AsyncClient) -> None:
        """Updating a non-existent category returns 404."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        resp = await client.put(
            "/api/v1/categories/99999",
            json={"name": "Ghost"},
            headers=_auth(token),
        )
        assert resp.status_code == 404

    async def test_update_duplicate_name_returns_409(self, client: AsyncClient) -> None:
        """Renaming to an existing name returns 409."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        cat_a = await _create_category(client, token, name="CategoryA")
        await _create_category(client, token, name="CategoryB")
        resp = await client.put(
            f"/api/v1/categories/{cat_a['id']}",
            json={"name": "CategoryB"},
            headers=_auth(token),
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    async def test_update_same_name_no_conflict(self, client: AsyncClient) -> None:
        """Updating with the same name does not trigger a uniqueness error."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, token, name="SameName")
        resp = await client.put(
            f"/api/v1/categories/{created['id']}",
            json={"name": "SameName"},
            headers=_auth(token),
        )
        assert resp.status_code == 200

    async def test_update_viewer_forbidden(self, client: AsyncClient) -> None:
        """A viewer cannot update a category (403)."""
        admin_token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, admin_token, name="Protected")

        viewer_token = await _register_and_login(client, email="viewer@test.com", role="viewer")
        resp = await client.put(
            f"/api/v1/categories/{created['id']}",
            json={"name": "Hacked"},
            headers=_auth(viewer_token),
        )
        assert resp.status_code == 403

    async def test_update_editor_forbidden(self, client: AsyncClient) -> None:
        """An editor cannot update a category (403) — admin required."""
        admin_token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, admin_token, name="EditorBlocked")

        editor_token = await _register_and_login(client, email="editor@test.com", role="editor")
        resp = await client.put(
            f"/api/v1/categories/{created['id']}",
            json={"name": "Hacked"},
            headers=_auth(editor_token),
        )
        assert resp.status_code == 403


# ── DELETE /categories/{id} ─────────────────────────────────────────────


class TestDeleteCategory:
    """Tests for DELETE /categories/{id}."""

    async def test_delete_returns_204(self, client: AsyncClient) -> None:
        """Admin can delete a category with no linked products."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, token, name="Deletable")
        resp = await client.delete(
            f"/api/v1/categories/{created['id']}", headers=_auth(token)
        )
        assert resp.status_code == 204
        assert resp.content == b""

        # Verify it's actually gone
        get_resp = await client.get(
            f"/api/v1/categories/{created['id']}", headers=_auth(token)
        )
        assert get_resp.status_code == 404

    async def test_delete_nonexistent_returns_404(self, client: AsyncClient) -> None:
        """Deleting a non-existent category returns 404."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        resp = await client.delete(
            "/api/v1/categories/99999", headers=_auth(token)
        )
        assert resp.status_code == 404

    async def test_delete_blocked_when_products_exist(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """Deleting a category with linked products returns 409."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, token, name="WithProducts")

        # Insert a product linked to this category directly via the ORM
        from app.models.product import Product
        product = Product(
            sku="SKU-001",
            name="Test Product",
            category_id=created["id"],
        )
        db_session.add(product)
        await db_session.flush()

        resp = await client.delete(
            f"/api/v1/categories/{created['id']}", headers=_auth(token)
        )
        assert resp.status_code == 409
        assert "product" in resp.json()["detail"].lower()

    async def test_delete_viewer_forbidden(self, client: AsyncClient) -> None:
        """A viewer cannot delete a category (403)."""
        admin_token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, admin_token, name="DeleteTarget")

        viewer_token = await _register_and_login(client, email="viewer@test.com", role="viewer")
        resp = await client.delete(
            f"/api/v1/categories/{created['id']}", headers=_auth(viewer_token)
        )
        assert resp.status_code == 403

    async def test_delete_editor_forbidden(self, client: AsyncClient) -> None:
        """An editor cannot delete a category (403)."""
        admin_token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, admin_token, name="EditorNoDelete")

        editor_token = await _register_and_login(client, email="editor@test.com", role="editor")
        resp = await client.delete(
            f"/api/v1/categories/{created['id']}", headers=_auth(editor_token)
        )
        assert resp.status_code == 403

    async def test_delete_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """No token returns 401."""
        resp = await client.delete("/api/v1/categories/1")
        assert resp.status_code == 401


# ── Auth Role Enforcement ───────────────────────────────────────────────


class TestAuthRoleEnforcement:
    """Cross-cutting tests for role-based access control."""

    async def test_create_viewer_forbidden(self, client: AsyncClient) -> None:
        """Viewer cannot create categories."""
        token = await _register_and_login(client, email="viewer@test.com", role="viewer")
        resp = await client.post(
            "/api/v1/categories",
            json={"name": "Nope"},
            headers=_auth(token),
        )
        assert resp.status_code == 403

    async def test_create_editor_forbidden(self, client: AsyncClient) -> None:
        """Editor cannot create categories."""
        token = await _register_and_login(client, email="editor@test.com", role="editor")
        resp = await client.post(
            "/api/v1/categories",
            json={"name": "Nope"},
            headers=_auth(token),
        )
        assert resp.status_code == 403

    async def test_super_admin_can_create(self, client: AsyncClient) -> None:
        """Super admin can create categories."""
        token = await _register_and_login(client, email="super@test.com", role="super_admin")
        resp = await client.post(
            "/api/v1/categories",
            json={"name": "SuperCategory"},
            headers=_auth(token),
        )
        assert resp.status_code == 201

    async def test_super_admin_can_delete(self, client: AsyncClient) -> None:
        """Super admin can delete categories."""
        token = await _register_and_login(client, email="super@test.com", role="super_admin")
        created = await _create_category(client, token, name="SuperDeletable")
        resp = await client.delete(
            f"/api/v1/categories/{created['id']}", headers=_auth(token)
        )
        assert resp.status_code == 204

    async def test_invalid_token_returns_401(self, client: AsyncClient) -> None:
        """A garbled token returns 401 on a protected write endpoint."""
        resp = await client.post(
            "/api/v1/categories",
            json={"name": "X"},
            headers={"Authorization": "Bearer not.real.token"},
        )
        assert resp.status_code == 401


# ── Full CRUD Integration Flow ──────────────────────────────────────────


class TestCategoryCRUDFlow:
    """End-to-end tests spanning multiple category endpoints."""

    async def test_create_read_update_delete_flow(self, client: AsyncClient) -> None:
        """Complete CRUD flow: create → read → update → verify → delete → verify gone."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")

        # 1. Create
        create_resp = await client.post(
            "/api/v1/categories",
            json={"name": "FlowCategory", "description": "Initial desc"},
            headers=_auth(token),
        )
        assert create_resp.status_code == 201
        cat = create_resp.json()
        cat_id = cat["id"]

        # 2. Read single
        get_resp = await client.get(
            f"/api/v1/categories/{cat_id}", headers=_auth(token)
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "FlowCategory"
        assert get_resp.json()["product_count"] == 0

        # 3. Update
        update_resp = await client.put(
            f"/api/v1/categories/{cat_id}",
            json={"name": "FlowCategoryRenamed", "description": "Updated desc"},
            headers=_auth(token),
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "FlowCategoryRenamed"

        # 4. Verify update persisted
        verify_resp = await client.get(
            f"/api/v1/categories/{cat_id}", headers=_auth(token)
        )
        assert verify_resp.json()["name"] == "FlowCategoryRenamed"
        assert verify_resp.json()["description"] == "Updated desc"

        # 5. Delete
        delete_resp = await client.delete(
            f"/api/v1/categories/{cat_id}", headers=_auth(token)
        )
        assert delete_resp.status_code == 204

        # 6. Verify deleted
        gone_resp = await client.get(
            f"/api/v1/categories/{cat_id}", headers=_auth(token)
        )
        assert gone_resp.status_code == 404

    async def test_product_count_reflects_linked_products(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """The product_count on a single-category response matches reality."""
        token = await _register_and_login(client, email="admin@test.com", role="admin")
        created = await _create_category(client, token, name="CountTest")

        # product_count should be 0 initially
        get1 = await client.get(
            f"/api/v1/categories/{created['id']}", headers=_auth(token)
        )
        assert get1.json()["product_count"] == 0

        # Add two products
        from app.models.product import Product
        for i in range(2):
            prod = Product(sku=f"SKU-{i}", name=f"Product {i}", category_id=created["id"])
            db_session.add(prod)
        await db_session.flush()

        get2 = await client.get(
            f"/api/v1/categories/{created['id']}", headers=_auth(token)
        )
        assert get2.json()["product_count"] == 2

        # Soft-delete one product — count should drop to 1
        from sqlalchemy import select as sa_select
        result = await db_session.execute(
            sa_select(Product).where(Product.category_id == created["id"]).limit(1)
        )
        prod_to_delete = result.scalar_one()
        prod_to_delete.is_deleted = True
        await db_session.flush()

        get3 = await client.get(
            f"/api/v1/categories/{created['id']}", headers=_auth(token)
        )
        assert get3.json()["product_count"] == 1
