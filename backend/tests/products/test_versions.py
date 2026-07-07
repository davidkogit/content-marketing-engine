"""
Integration tests for the product version history API endpoints.

Uses an in-memory SQLite database and httpx AsyncClient to exercise
version listing, detail retrieval, restore, and auto-versioning on
product updates.
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
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.auth.jwt_service import JWTService
from app.database import Base, get_db
from app.main import create_app
from app.models.product_version import ProductVersion

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


async def _update_product(
    client: AsyncClient,
    product_id: int,
    updates: dict,
    role: str = "admin",
) -> dict:
    resp = await client.put(
        f"/api/v1/products/{product_id}",
        json=updates,
        headers=await _auth_headers(role),
    )
    return resp


# ── GET /api/products/{id}/versions (List) ───────────────────────────────────


class TestListVersions:
    async def test_list_empty_for_new_product(self, client):
        """A brand new product has no version records."""
        await _create_product(client, sku="V-LIST-1")

        resp = await client.get(
            "/api/v1/products/1/versions",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["versions"] == []
        assert body["total"] == 0

    async def test_list_requires_auth(self, client):
        """Unauthenticated requests are rejected."""
        resp = await client.get("/api/v1/products/1/versions")
        assert resp.status_code == 401

    async def test_list_returns_versions_ordered_newest_first(self, client):
        """Versions are returned in descending version_number order."""
        await _create_product(client, sku="ORDERED")
        # Create multiple versions via updates
        await _update_product(client, 1, {"name": "v2"})
        await _update_product(client, 1, {"name": "v3"})
        await _update_product(client, 1, {"description": "desc v4"})

        resp = await client.get(
            "/api/v1/products/1/versions",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        versions = body["versions"]
        # Newest first
        assert versions[0]["version_number"] == 3
        assert versions[1]["version_number"] == 2
        assert versions[2]["version_number"] == 1

    async def test_list_includes_snapshot_json(self, client):
        """Each version in the list response includes snapshot_json."""
        await _create_product(client, sku="SNAP", name="Original")
        await _update_product(client, 1, {"name": "Changed"})

        resp = await client.get(
            "/api/v1/products/1/versions",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert body["total"] == 1
        v = body["versions"][0]
        assert "snapshot_json" in v
        assert "name" in v["snapshot_json"]
        assert v["change_summary"] is not None

    async def test_list_for_nonexistent_product_returns_empty(self, client):
        """Listing versions for a non-existent product returns empty list."""
        resp = await client.get(
            "/api/v1/products/99999/versions",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["versions"] == []
        assert body["total"] == 0

    async def test_list_after_soft_delete_still_works(self, client):
        """Soft-deleted products still have their version history."""
        await _create_product(client, sku="DEL-VER")
        await _update_product(client, 1, {"name": "Updated"})
        await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("super_admin"),
        )

        resp = await client.get(
            "/api/v1/products/1/versions",
            headers=await _auth_headers("viewer"),
        )
        # Product is soft-deleted but versions still exist in DB
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1


# ── GET /api/products/{id}/versions/{n} (Detail) ─────────────────────────────


class TestGetVersion:
    async def test_get_specific_version(self, client):
        """Fetch a specific version by its number."""
        await _create_product(client, sku="DETAIL", name="v1")
        await _update_product(client, 1, {"name": "v2"})
        await _update_product(client, 1, {"name": "v3"})

        resp = await client.get(
            "/api/v1/products/1/versions/2",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["version_number"] == 2
        assert body["id"] is not None
        assert "snapshot_json" in body
        assert body["change_summary"] is not None

    async def test_get_version_requires_auth(self, client):
        resp = await client.get("/api/v1/products/1/versions/1")
        assert resp.status_code == 401

    async def test_get_version_not_found(self, client):
        """Requesting a non-existent version returns 404."""
        await _create_product(client, sku="NO-VER")
        resp = await client.get(
            "/api/v1/products/1/versions/99",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    async def test_get_version_wrong_product(self, client):
        """Version number exists on a different product — 404."""
        await _create_product(client, sku="PROD-A", name="A")
        await _create_product(client, sku="PROD-B", name="B")
        await _update_product(client, 1, {"name": "A2"})  # creates version 1 on prod 1

        resp = await client.get(
            "/api/v1/products/2/versions/1",  # product 2 has no versions
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 404

    async def test_get_version_includes_snapshot(self, client):
        """The snapshot_json contains the pre-edit state."""
        await _create_product(
            client, sku="SNAP-DETAIL", name="Before", description="Initial"
        )
        await _update_product(client, 1, {"name": "After"})

        resp = await client.get(
            "/api/v1/products/1/versions/1",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        snapshot = body["snapshot_json"]
        # The snapshot should contain the pre-edit state: name="Before"
        assert "name" in snapshot

    async def test_get_version_has_all_required_fields(self, client):
        """Response includes id, version_number, snapshot_json, change_summary,
        created_by, created_at."""
        await _create_product(client, sku="FIELDS", name="Original")
        await _update_product(client, 1, {"name": "New"})

        resp = await client.get(
            "/api/v1/products/1/versions/1",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        for field in (
            "id",
            "version_number",
            "snapshot_json",
            "change_summary",
            "created_by",
            "created_at",
        ):
            assert field in body, f"Missing field: {field}"


# ── POST /api/products/{id}/versions/{n}/restore ─────────────────────────────


class TestRestoreVersion:
    async def test_restore_creates_new_version(self, client, db_session):
        """Restoring to a previous version creates a new version record."""
        await _create_product(client, sku="RESTORE", name="Original")
        await _update_product(client, 1, {"name": "Changed"})

        # Now we have version 1 (Original → Changed)
        # Restore to version 1 (should go back to "Original")
        resp = await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Should now have 2 versions: the original update + the restore
        assert body["total"] == 2

        # Verify the product was actually restored
        get_resp = await client.get(
            "/api/v1/products/1",
            headers=await _auth_headers("viewer"),
        )
        assert get_resp.status_code == 200
        # The original snapshot (version 1) stored "name"="Original"
        # After restore, the product name should be back to "Original"
        assert get_resp.json()["name"] == "Original"

    async def test_restore_requires_admin(self, client):
        """Only admin+ can restore versions."""
        await _create_product(client, sku="NO-REST", name="v1")
        await _update_product(client, 1, {"name": "v2"})

        resp = await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 403

        resp = await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 403

    async def test_restore_requires_auth(self, client):
        resp = await client.post("/api/v1/products/1/versions/1/restore")
        assert resp.status_code == 401

    async def test_restore_nonexistent_product(self, client):
        """Restoring on a product that doesn't exist returns 404."""
        resp = await client.post(
            "/api/v1/products/99999/versions/1/restore",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 404

    async def test_restore_nonexistent_version(self, client):
        """Restoring to a version that doesn't exist returns 404."""
        await _create_product(client, sku="NO-VER-REST")
        resp = await client.post(
            "/api/v1/products/1/versions/99/restore",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 404

    async def test_restore_soft_deleted_product(self, client):
        """Cannot restore a soft-deleted product."""
        await _create_product(client, sku="DEL-REST", name="v1")
        await _update_product(client, 1, {"name": "v2"})
        await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("super_admin"),
        )

        resp = await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 404

    async def test_restore_change_summary_indicates_restore(self, client):
        """The new version created by a restore has a descriptive change_summary."""
        await _create_product(client, sku="SUM-TEST", name="Original")
        await _update_product(client, 1, {"name": "Changed"})

        resp = await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200
        versions = resp.json()["versions"]
        # Newest version (index 0) should be the restore
        newest = versions[0]
        assert "restore" in newest["change_summary"].lower()

    async def test_restore_with_multiple_fields(self, client):
        """Restoring a snapshot with multiple field changes works correctly."""
        await _create_product(
            client,
            sku="MULTI-REST",
            name="Original Name",
            description="Original Desc",
        )
        # Update name and description
        await _update_product(client, 1, {"name": "New Name", "description": "New Desc"})
        # Update workflow_stage
        await _update_product(client, 1, {"workflow_stage": "draft"})

        # Now versions: 1 (name+desc change), 2 (stage change)
        # Restore to version 1
        resp = await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200

        # Verify product state matches version 1 snapshot
        get_resp = await client.get(
            "/api/v1/products/1",
            headers=await _auth_headers("viewer"),
        )
        product = get_resp.json()
        assert product["name"] == "Original Name"
        assert product["description"] == "Original Desc"

    async def test_restore_appends_versions_not_truncates(self, client):
        """Restoring does not delete existing version history — it appends."""
        await _create_product(client, sku="APPEND", name="v1")
        await _update_product(client, 1, {"name": "v2"})
        await _update_product(client, 1, {"name": "v3"})

        # We have 2 versions before restore
        resp_before = await client.get(
            "/api/v1/products/1/versions",
            headers=await _auth_headers("viewer"),
        )
        assert resp_before.json()["total"] == 2

        # Restore to version 1
        await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=await _auth_headers("admin"),
        )

        # Now we should have 3 versions (2 originals + 1 restore)
        resp_after = await client.get(
            "/api/v1/products/1/versions",
            headers=await _auth_headers("viewer"),
        )
        assert resp_after.json()["total"] == 3

    async def test_restore_to_current_state(self, client):
        """Restoring to a version that matches current state still creates a version."""
        await _create_product(client, sku="SAME-REST", name="Same")

        # Update creates version 1 with snapshot of "Same"
        await _update_product(client, 1, {"name": "Different"})

        # Restore to version 1 (which has name="Same" — current state is "Different")
        resp = await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200
        # Should now have 2 versions: original update + restore
        assert resp.json()["total"] == 2


# ── Auto-Versioning (Smoke Tests) ────────────────────────────────────────────


class TestAutoVersioning:
    """Verify that product updates automatically create version records."""

    async def test_update_name_creates_version(self, client, db_session):
        await _create_product(client, sku="AUTO-1", name="v1")
        await _update_product(client, 1, {"name": "v2"})

        from sqlalchemy import select

        versions = (
            (await db_session.execute(select(ProductVersion)))
            .scalars()
            .all()
        )
        assert len(versions) == 1
        assert versions[0].version_number == 1
        assert versions[0].product_id == 1

    async def test_multiple_updates_increment_version(self, client, db_session):
        await _create_product(client, sku="AUTO-2", name="v1")
        await _update_product(client, 1, {"name": "v2"})
        await _update_product(client, 1, {"name": "v3"})
        await _update_product(client, 1, {"description": "added"})

        from sqlalchemy import select

        versions = (
            (await db_session.execute(
                select(ProductVersion).order_by(ProductVersion.version_number)
            ))
            .scalars()
            .all()
        )
        assert len(versions) == 3
        assert [v.version_number for v in versions] == [1, 2, 3]

    async def test_no_change_creates_no_version(self, client, db_session):
        await _create_product(client, sku="AUTO-3", name="Same")
        await _update_product(client, 1, {"name": "Same"})

        from sqlalchemy import select

        versions = (
            (await db_session.execute(select(ProductVersion)))
            .scalars()
            .all()
        )
        assert len(versions) == 0

    async def test_version_includes_created_by(self, client, db_session):
        await _create_product(client, sku="AUTO-4", name="v1")
        # User ID in token helper is 1 for admin
        await _update_product(client, 1, {"name": "v2"}, role="admin")

        from sqlalchemy import select

        versions = (
            (await db_session.execute(select(ProductVersion)))
            .scalars()
            .all()
        )
        assert len(versions) == 1
        assert versions[0].created_by == 1


# ── Auth Enforcement ────────────────────────────────────────────────────────


class TestVersionAuthEnforcement:
    """Verify that version endpoints enforce role-based access."""

    async def test_viewer_can_list_and_get(self, client):
        """Viewers can list versions and get individual version detail."""
        await _create_product(client, sku="VIEW-VER", name="v1")
        await _update_product(client, 1, {"name": "v2"})

        list_resp = await client.get(
            "/api/v1/products/1/versions",
            headers=await _auth_headers("viewer"),
        )
        assert list_resp.status_code == 200

        get_resp = await client.get(
            "/api/v1/products/1/versions/1",
            headers=await _auth_headers("viewer"),
        )
        assert get_resp.status_code == 200

    async def test_viewer_cannot_restore(self, client):
        """Viewers cannot restore versions."""
        await _create_product(client, sku="VIEW-NO-REST", name="v1")
        await _update_product(client, 1, {"name": "v2"})

        resp = await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 403

    async def test_editor_cannot_restore(self, client):
        """Editors cannot restore versions."""
        await _create_product(client, sku="EDIT-NO-REST", name="v1")
        await _update_product(client, 1, {"name": "v2"})

        resp = await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 403

    async def test_admin_can_restore(self, client):
        """Admin role can restore versions."""
        await _create_product(client, sku="ADMIN-REST", name="v1")
        await _update_product(client, 1, {"name": "v2"})

        resp = await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200

    async def test_super_admin_can_restore(self, client):
        """Super admin role can restore versions."""
        await _create_product(client, sku="SA-REST", name="v1")
        await _update_product(client, 1, {"name": "v2"})

        resp = await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=await _auth_headers("super_admin"),
        )
        assert resp.status_code == 200

    async def test_unauthenticated_rejected_all(self, client):
        """All version endpoints reject unauthenticated requests."""
        await _create_product(client, sku="NO-AUTH-VER", name="v1")

        assert (
            await client.get("/api/v1/products/1/versions")
        ).status_code == 401
        assert (
            await client.get("/api/v1/products/1/versions/1")
        ).status_code == 401
        assert (
            await client.post("/api/v1/products/1/versions/1/restore")
        ).status_code == 401


# ── Full Restore Flow ────────────────────────────────────────────────────────


class TestFullRestoreFlow:
    """End-to-end test of the version lifecycle: create → update → restore."""

    async def test_full_restore_lifecycle(self, client, db_session):
        """Exercise create, multiple updates, restore, and verify history."""
        h = await _auth_headers("admin")

        # 1. Create product
        resp = await client.post(
            "/api/v1/products",
            json={
                "sku": "LIFECYCLE-V",
                "name": "Stage 1",
                "description": "Initial description",
            },
            headers=h,
        )
        assert resp.status_code == 201

        # 2. Update to Stage 2
        await client.put(
            "/api/v1/products/1",
            json={"name": "Stage 2", "description": "Updated description"},
            headers=h,
        )

        # 3. Update to Stage 3
        await client.put(
            "/api/v1/products/1",
            json={"name": "Stage 3", "workflow_stage": "draft"},
            headers=h,
        )

        # 4. Verify 2 versions exist
        list_resp = await client.get(
            "/api/v1/products/1/versions",
            headers=await _auth_headers("viewer"),
        )
        assert list_resp.json()["total"] == 2

        # 5. Restore to version 1
        restore_resp = await client.post(
            "/api/v1/products/1/versions/1/restore",
            headers=h,
        )
        assert restore_resp.status_code == 200
        assert restore_resp.json()["total"] == 3

        # 6. Verify product has version 1's state
        get_resp = await client.get(
            "/api/v1/products/1",
            headers=await _auth_headers("viewer"),
        )
        product = get_resp.json()
        assert product["name"] == "Stage 1"
        assert product["description"] == "Initial description"

        # 7. Verify DB has 3 version records
        from sqlalchemy import select

        versions = (
            (await db_session.execute(
                select(ProductVersion).order_by(ProductVersion.version_number)
            ))
            .scalars()
            .all()
        )
        assert len(versions) == 3
        assert versions[0].version_number == 1
        assert versions[1].version_number == 2
        assert versions[2].version_number == 3
        # Version 3 should be the restore
        assert "restore" in (versions[2].change_summary or "").lower()
