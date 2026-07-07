"""
Integration tests for the products API endpoints.

Uses an in-memory SQLite database and httpx AsyncClient to exercise
full product CRUD, filtering, pagination, version tracking, and
role-based auth enforcement.
"""

from __future__ import annotations

import asyncio
import os

# ── Ensure required env vars are set BEFORE any app imports ──────────────
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
from app.models.product import WorkflowStage
from app.models.category import Category
from app.models.segment import Segment

# ── Constants ───────────────────────────────────────────────────────────────

_TEST_SECRET: str = os.environ["SECRET_KEY"]


# ── Test Application Factory ────────────────────────────────────────────────


def _build_test_app(*, db_override=None):
    app = create_app()
    if db_override is not None:
        app.dependency_overrides[get_db] = db_override
    return app


# ── Fixtures ────────────────────────────────────────────────────────────────


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


# ── Token Helpers ───────────────────────────────────────────────────────────


_jwt_svc = JWTService(secret_key=_TEST_SECRET)


async def _token(role: str, user_id: int = 1) -> str:
    return await _jwt_svc.create_access_token(
        user_id=user_id, email=f"{role}@test.com", role=role
    )


async def _auth_headers(role: str, user_id: int = 1) -> dict:
    t = await _token(role, user_id)
    return {"Authorization": f"Bearer {t}"}


# ── Product Helpers ─────────────────────────────────────────────────────────


async def _create_product(
    client: AsyncClient,
    sku: str = "SKU-001",
    name: str = "Test Product",
    role: str = "admin",
) -> dict:
    resp = await client.post(
        "/api/v1/products",
        json={"sku": sku, "name": name},
        headers=await _auth_headers(role),
    )
    return resp


async def _create_category(db_session: AsyncSession, name: str = "Electronics") -> int:
    cat = Category(name=name)
    db_session.add(cat)
    await db_session.flush()
    await db_session.refresh(cat)
    return cat.id


async def _create_segment(db_session: AsyncSession, name: str = "Enterprise") -> int:
    seg = Segment(name=name)
    db_session.add(seg)
    await db_session.flush()
    await db_session.refresh(seg)
    return seg.id


# ── GET /api/products ───────────────────────────────────────────────────────


class TestListProducts:
    async def test_list_returns_empty_when_no_products(self, client):
        resp = await client.get(
            "/api/v1/products",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []
        assert body["page"] == 1
        assert body["total_pages"] == 0

    async def test_list_requires_auth(self, client):
        resp = await client.get("/api/v1/products")
        assert resp.status_code == 401

    async def test_list_returns_products(self, client):
        await _create_product(client, sku="A", name="Alpha")
        await _create_product(client, sku="B", name="Beta")

        resp = await client.get(
            "/api/v1/products",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        assert body["items"][0]["sku"] == "A"
        assert body["items"][1]["sku"] == "B"

    async def test_list_pagination(self, client):
        for i in range(5):
            await _create_product(client, sku=f"SKU-{i:03d}", name=f"Product {i}")

        resp = await client.get(
            "/api/v1/products?page=1&page_size=2",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2
        assert body["total_pages"] == 3
        assert body["page"] == 1
        assert body["page_size"] == 2

    async def test_list_filter_by_category(self, client, db_session):
        cat_id = await _create_category(db_session, "Shoes")
        await _create_product(client, sku="SHOE-1", name="Runner", role="admin")
        resp = await client.put(
            "/api/v1/products/1",
            json={"category_id": cat_id},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200

        resp = await client.get(
            f"/api/v1/products?category_id={cat_id}",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["category_id"] == cat_id

    async def test_list_filter_by_segment(self, client, db_session):
        seg_id = await _create_segment(db_session, "SMB")
        await _create_product(client, sku="SEG-1", name="Small Biz", role="admin")
        resp = await client.put(
            "/api/v1/products/1",
            json={"segment_id": seg_id},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200

        resp = await client.get(
            f"/api/v1/products?segment_id={seg_id}",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert body["total"] == 1

    async def test_list_filter_by_workflow_stage(self, client):
        await _create_product(client, sku="INGEST-1", name="Raw")

        resp = await client.get(
            "/api/v1/products?workflow_stage=ingest",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert body["total"] == 1

        resp = await client.get(
            "/api/v1/products?workflow_stage=draft",
            headers=await _auth_headers("viewer"),
        )
        assert resp.json()["total"] == 0

    async def test_list_search_by_name(self, client):
        await _create_product(client, sku="X", name="Widget Pro")
        await _create_product(client, sku="Y", name="Gadget Lite")

        resp = await client.get(
            "/api/v1/products?search=widget",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Widget Pro"

    async def test_list_search_by_sku(self, client):
        await _create_product(client, sku="WIDGET-99", name="Widget")
        await _create_product(client, sku="GADGET-01", name="Gadget")

        resp = await client.get(
            "/api/v1/products?search=WIDGET",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["sku"] == "WIDGET-99"

    async def test_list_combines_filters(self, client):
        await _create_product(client, sku="A1", name="Alpha")
        await _create_product(client, sku="B1", name="Beta")
        # Move B1 to draft
        await client.put(
            "/api/v1/products/2",
            json={"workflow_stage": "draft"},
            headers=await _auth_headers("admin"),
        )

        resp = await client.get(
            "/api/v1/products?workflow_stage=ingest&search=Alpha",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["sku"] == "A1"


# ── POST /api/products ──────────────────────────────────────────────────────


class TestCreateProduct:
    async def test_create_returns_201(self, client):
        resp = await _create_product(client)
        assert resp.status_code == 201
        body = resp.json()
        assert body["sku"] == "SKU-001"
        assert body["name"] == "Test Product"
        assert body["workflow_stage"] == "ingest"
        assert body["is_deleted"] is False

    async def test_create_requires_admin(self, client):
        resp = await _create_product(client, role="editor")
        assert resp.status_code == 403

        resp = await _create_product(client, role="viewer")
        assert resp.status_code == 403

    async def test_create_enforces_sku_uniqueness(self, client):
        await _create_product(client, sku="UNIQUE")
        resp = await _create_product(client, sku="UNIQUE")
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    async def test_create_with_category_and_segment(self, client, db_session):
        cat_id = await _create_category(db_session)
        seg_id = await _create_segment(db_session)

        resp = await client.post(
            "/api/v1/products",
            json={
                "sku": "FULL",
                "name": "Full Product",
                "category_id": cat_id,
                "segment_id": seg_id,
            },
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["category_id"] == cat_id
        assert body["segment_id"] == seg_id

    async def test_create_with_description(self, client):
        resp = await client.post(
            "/api/v1/products",
            json={"sku": "DESC", "name": "Described", "description": "A fine product."},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 201
        assert resp.json()["description"] == "A fine product."

    async def test_create_missing_required_fields(self, client):
        resp = await client.post(
            "/api/v1/products",
            json={},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 422

    async def test_create_empty_sku_rejected(self, client):
        resp = await client.post(
            "/api/v1/products",
            json={"sku": "", "name": "Bad"},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 422

    async def test_create_requires_auth(self, client):
        resp = await client.post(
            "/api/v1/products",
            json={"sku": "NOPE", "name": "Nope"},
        )
        assert resp.status_code == 401

    async def test_create_sku_can_be_reused_after_soft_delete(self, client):
        await _create_product(client, sku="REUSE-ME")
        await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("super_admin"),
        )
        resp = await _create_product(client, sku="REUSE-ME")
        assert resp.status_code == 201


# ── GET /api/products/{id} ──────────────────────────────────────────────────


class TestGetProduct:
    async def test_get_single_product(self, client):
        await _create_product(client, sku="GET-ME")
        resp = await client.get(
            "/api/v1/products/1",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["sku"] == "GET-ME"
        assert body["documents"] == []
        assert body["claims"] == []
        assert body["versions"] == []

    async def test_get_product_includes_category_and_segment(self, client, db_session):
        cat_id = await _create_category(db_session, "Books")
        seg_id = await _create_segment(db_session, "Education")

        await client.post(
            "/api/v1/products",
            json={
                "sku": "BOOK",
                "name": "E-Book",
                "category_id": cat_id,
                "segment_id": seg_id,
            },
            headers=await _auth_headers("admin"),
        )

        resp = await client.get(
            "/api/v1/products/1",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert body["category"]["id"] == cat_id
        assert body["category"]["name"] == "Books"
        assert body["segment"]["id"] == seg_id
        assert body["segment"]["name"] == "Education"

    async def test_get_product_soft_deleted_returns_404(self, client):
        await _create_product(client, sku="GONE")
        await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("super_admin"),
        )
        resp = await client.get(
            "/api/v1/products/1",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 404

    async def test_get_product_not_found(self, client):
        resp = await client.get(
            "/api/v1/products/99999",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 404

    async def test_get_product_requires_auth(self, client):
        resp = await client.get("/api/v1/products/1")
        assert resp.status_code == 401


# ── PUT /api/products/{id} ──────────────────────────────────────────────────


class TestUpdateProduct:
    async def test_update_name(self, client):
        await _create_product(client, sku="CHANGE")
        resp = await client.put(
            "/api/v1/products/1",
            json={"name": "Changed Name"},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Changed Name"

    async def test_update_creates_version(self, client, db_session):
        await _create_product(client, sku="VERSIONED", name="v1")
        # Update creates version
        resp = await client.put(
            "/api/v1/products/1",
            json={"name": "v2"},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200
        # Verify version record exists
        from app.models.product_version import ProductVersion
        from sqlalchemy import select

        versions = (
            (await db_session.execute(select(ProductVersion))).scalars().all()
        )
        assert len(versions) == 1
        v = versions[0]
        assert v.product_id == 1
        assert v.version_number == 1
        assert v.change_summary == "name"

    async def test_update_multiple_fields_single_version(self, client, db_session):
        await _create_product(client, sku="MULTI")
        resp = await client.put(
            "/api/v1/products/1",
            json={"name": "Multi", "description": "New desc"},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200

        from app.models.product_version import ProductVersion
        from sqlalchemy import select

        versions = (
            (await db_session.execute(select(ProductVersion))).scalars().all()
        )
        assert len(versions) == 1
        assert "name" in versions[0].change_summary
        assert "description" in versions[0].change_summary

    async def test_update_no_change_creates_no_version(self, client, db_session):
        await _create_product(client, sku="SAME", name="Same")
        resp = await client.put(
            "/api/v1/products/1",
            json={"name": "Same"},  # same value
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200

        from app.models.product_version import ProductVersion
        from sqlalchemy import select

        versions = (
            (await db_session.execute(select(ProductVersion))).scalars().all()
        )
        assert len(versions) == 0

    async def test_update_workflow_stage(self, client):
        await _create_product(client, sku="STAGE-MOVE")
        resp = await client.put(
            "/api/v1/products/1",
            json={"workflow_stage": "draft"},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200
        assert resp.json()["workflow_stage"] == "draft"

    async def test_update_requires_admin(self, client):
        await _create_product(client, sku="NO-EDIT")
        resp = await client.put(
            "/api/v1/products/1",
            json={"name": "Hacked"},
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 403

    async def test_update_soft_deleted_returns_404(self, client):
        await _create_product(client, sku="GONE-UPD")
        await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("super_admin"),
        )
        resp = await client.put(
            "/api/v1/products/1",
            json={"name": "Resurrect"},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 404

    async def test_update_not_found(self, client):
        resp = await client.put(
            "/api/v1/products/99999",
            json={"name": "Ghost"},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 404


# ── DELETE /api/products/{id} ───────────────────────────────────────────────


class TestDeleteProduct:
    async def test_soft_delete(self, client):
        await _create_product(client, sku="SOFT-DEL")
        resp = await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("super_admin"),
        )
        assert resp.status_code == 204

        # Should be hidden from listing
        list_resp = await client.get(
            "/api/v1/products",
            headers=await _auth_headers("viewer"),
        )
        assert list_resp.json()["total"] == 0

    async def test_hard_delete(self, client):
        await _create_product(client, sku="HARD-DEL")
        resp = await client.delete(
            "/api/v1/products/1?permanent=true",
            headers=await _auth_headers("super_admin"),
        )
        assert resp.status_code == 204

        # Should be physically removed from the database
        get_resp = await client.get(
            "/api/v1/products/1",
            headers=await _auth_headers("viewer"),
        )
        assert get_resp.status_code == 404
        # After hard delete the product is physically gone from the DB

    async def test_delete_requires_super_admin(self, client):
        await _create_product(client, sku="NO-DEL")
        resp = await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 403

    async def test_delete_not_found(self, client):
        resp = await client.delete(
            "/api/v1/products/99999",
            headers=await _auth_headers("super_admin"),
        )
        assert resp.status_code == 404

    async def test_cannot_soft_delete_twice(self, client):
        await _create_product(client, sku="ONCE")
        await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("super_admin"),
        )
        resp = await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("super_admin"),
        )
        assert resp.status_code == 404


# ── Auth Enforcement ────────────────────────────────────────────────────────


class TestAuthEnforcement:
    """Tests verifying that every endpoint enforces role-based access."""

    async def test_viewer_cannot_mutate(self, client):
        """Viewer role cannot create, update, or delete products."""
        await _create_product(client, role="admin", sku="SAFE")

        create = await client.post(
            "/api/v1/products",
            json={"sku": "NOPE", "name": "Nope"},
            headers=await _auth_headers("viewer"),
        )
        assert create.status_code == 403

        update = await client.put(
            "/api/v1/products/1",
            json={"name": "Nope"},
            headers=await _auth_headers("viewer"),
        )
        assert update.status_code == 403

        delete = await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("viewer"),
        )
        assert delete.status_code == 403

    async def test_editor_can_view_but_not_mutate(self, client):
        """Editor can read but cannot write."""
        await _create_product(client, role="admin", sku="EDIT-VIEW")

        list_r = await client.get(
            "/api/v1/products",
            headers=await _auth_headers("editor"),
        )
        assert list_r.status_code == 200

        get_r = await client.get(
            "/api/v1/products/1",
            headers=await _auth_headers("editor"),
        )
        assert get_r.status_code == 200

        create_r = await client.post(
            "/api/v1/products",
            json={"sku": "NOPE", "name": "Nope"},
            headers=await _auth_headers("editor"),
        )
        assert create_r.status_code == 403

    async def test_admin_can_mutate_but_not_delete(self, client):
        """Admin can CRUD except delete."""
        create = await _create_product(client, role="admin", sku="ADMIN-TEST")
        assert create.status_code == 201

        update = await client.put(
            "/api/v1/products/1",
            json={"name": "Updated"},
            headers=await _auth_headers("admin"),
        )
        assert update.status_code == 200

        delete = await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("admin"),
        )
        assert delete.status_code == 403

    async def test_super_admin_full_access(self, client):
        """Super admin can do everything."""
        create = await _create_product(client, role="super_admin", sku="SA-TEST")
        assert create.status_code == 201

        update = await client.put(
            "/api/v1/products/1",
            json={"name": "SA Updated"},
            headers=await _auth_headers("super_admin"),
        )
        assert update.status_code == 200

        delete = await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("super_admin"),
        )
        assert delete.status_code == 204

    async def test_unauthenticated_rejected(self, client):
        """All endpoints reject requests without auth headers."""
        # GET list
        assert (await client.get("/api/v1/products")).status_code == 401
        # GET single
        assert (await client.get("/api/v1/products/1")).status_code == 401
        # POST
        assert (
            await client.post(
                "/api/v1/products",
                json={"sku": "X", "name": "X"},
            )
        ).status_code == 401
        # PUT
        assert (
            await client.put(
                "/api/v1/products/1",
                json={"name": "X"},
            )
        ).status_code == 401
        # DELETE
        assert (await client.delete("/api/v1/products/1")).status_code == 401


# ── Full CRUD Flow ──────────────────────────────────────────────────────────


class TestFullCRUDFlow:
    async def test_full_crud_lifecycle(self, client, db_session):
        """Exercise the complete product lifecycle."""
        headers = await _auth_headers("admin")

        # Create
        resp = await client.post(
            "/api/v1/products",
            json={"sku": "LIFECYCLE", "name": "Lifecycle Product", "description": "Start"},
            headers=headers,
        )
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # Read
        get_r = await client.get(
            f"/api/v1/products/{pid}",
            headers=await _auth_headers("viewer"),
        )
        assert get_r.status_code == 200
        assert get_r.json()["workflow_stage"] == "ingest"

        # Update stage through workflow
        stages = ["draft", "review", "approved"]
        for stage in stages:
            r = await client.put(
                f"/api/v1/products/{pid}",
                json={"workflow_stage": stage},
                headers=headers,
            )
            assert r.status_code == 200
            assert r.json()["workflow_stage"] == stage

        # Verify versions captured
        from app.models.product_version import ProductVersion
        from sqlalchemy import select

        versions = (
            (await db_session.execute(select(ProductVersion))).scalars().all()
        )
        assert len(versions) == 3  # one per stage change

        # List with filter
        list_r = await client.get(
            "/api/v1/products?workflow_stage=approved",
            headers=await _auth_headers("viewer"),
        )
        assert list_r.json()["total"] == 1

        # Soft delete
        del_r = await client.delete(
            f"/api/v1/products/{pid}",
            headers=await _auth_headers("super_admin"),
        )
        assert del_r.status_code == 204

        # Should be hidden
        list_r = await client.get(
            "/api/v1/products",
            headers=await _auth_headers("viewer"),
        )
        assert list_r.json()["total"] == 0

    async def test_pagination_with_many_products(self, client):
        """Create 10 products and verify pagination works correctly."""
        h = await _auth_headers("admin")
        for i in range(10):
            r = await client.post(
                "/api/v1/products",
                json={"sku": f"PAGE-{i:03d}", "name": f"Page Product {i}"},
                headers=h,
            )
            assert r.status_code == 201

        # Page 1
        r1 = await client.get(
            "/api/v1/products?page=1&page_size=3",
            headers=await _auth_headers("viewer"),
        )
        b1 = r1.json()
        assert b1["total"] == 10
        assert b1["total_pages"] == 4
        assert len(b1["items"]) == 3
        assert b1["items"][0]["sku"] == "PAGE-000"

        # Page 4 (last page)
        r4 = await client.get(
            "/api/v1/products?page=4&page_size=3",
            headers=await _auth_headers("viewer"),
        )
        b4 = r4.json()
        assert len(b4["items"]) == 1
        assert b4["items"][0]["sku"] == "PAGE-009"
