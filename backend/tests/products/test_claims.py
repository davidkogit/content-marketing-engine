"""
Integration tests for the product claims API endpoints.

Uses an in-memory SQLite database and httpx AsyncClient to exercise
claim creation (with cross-entity validation), listing (with status
filtering), updating, deletion, and role-based auth enforcement.
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

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.jwt_service import JWTService
from app.database import Base, get_db
from app.documents.url_fetcher import FetchedContent
from app.main import create_app
from app.models.user import User, UserRole

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


# ── User Seeding ────────────────────────────────────────────────────────────

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


# ── Token Helpers ───────────────────────────────────────────────────────────

_jwt_svc = JWTService(secret_key=_TEST_SECRET)


async def _token(role: str, user_id: int | None = None) -> str:
    uid = user_id if user_id is not None else _ROLE_USER_IDS.get(role, 1)
    return await _jwt_svc.create_access_token(
        user_id=uid, email=f"{role}@test.com", role=role
    )


async def _auth_headers(role: str, user_id: int | None = None) -> dict:
    t = await _token(role, user_id)
    return {"Authorization": f"Bearer {t}"}


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _create_product(
    client: AsyncClient,
    sku: str = "SKU-001",
    name: str = "Test Product",
) -> dict:
    resp = await client.post(
        "/api/v1/products",
        json={"sku": sku, "name": name},
        headers=await _auth_headers("admin"),
    )
    return resp


async def _create_document(
    client: AsyncClient,
    product_id: int = 1,
    url: str = "https://example.com/doc",
    title: str = "Test Doc",
) -> int:
    """Create a linked document and return its ID."""
    content = FetchedContent(
        url=url,
        status_code=200,
        content_type="text/html",
        title=title,
        raw_text="Sample content.",
    )
    with patch(
        "app.products.document_service.URLFetcher.fetch",
        new_callable=AsyncMock,
        return_value=content,
    ):
        resp = await client.post(
            f"/api/v1/products/{product_id}/documents",
            json={"url": url, "doc_type": "url"},
            headers=await _auth_headers("admin"),
        )
    return resp.json()["id"]


async def _create_claim(
    client: AsyncClient,
    product_id: int = 1,
    claim_text: str = "Best product ever",
    source_doc_id: int | None = None,
    status: str = "pending_review",
    role: str = "admin",
) -> dict:
    """Create a claim and return the response dict."""
    body: dict = {"claim_text": claim_text, "status": status}
    if source_doc_id is not None:
        body["source_doc_id"] = source_doc_id
    resp = await client.post(
        f"/api/v1/products/{product_id}/claims",
        json=body,
        headers=await _auth_headers(role),
    )
    return resp


# ── GET /api/products/{product_id}/claims ────────────────────────────────────


class TestListClaims:
    async def test_list_returns_empty_when_no_claims(self, client):
        await _create_product(client, sku="CLAIM-EMPTY")
        resp = await client.get(
            "/api/v1/products/1/claims",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_requires_auth(self, client):
        await _create_product(client, sku="CLAIM-AUTH")
        resp = await client.get("/api/v1/products/1/claims")
        assert resp.status_code == 401

    async def test_list_returns_claims(self, client):
        await _create_product(client, sku="CLAIM-LIST")
        await _create_claim(client, claim_text="First claim")
        await _create_claim(client, claim_text="Second claim")

        resp = await client.get(
            "/api/v1/products/1/claims",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["claim_text"] == "First claim"
        assert body[1]["claim_text"] == "Second claim"

    async def test_list_filter_by_status(self, client):
        await _create_product(client, sku="CLAIM-FILTER")
        await _create_claim(client, claim_text="Pending", status="pending_review")
        await _create_claim(client, claim_text="Verified", status="verified")

        # Filter for pending
        resp = await client.get(
            "/api/v1/products/1/claims?status=pending_review",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert len(body) == 1
        assert body[0]["claim_text"] == "Pending"

        # Filter for verified
        resp = await client.get(
            "/api/v1/products/1/claims?status=verified",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert len(body) == 1
        assert body[0]["claim_text"] == "Verified"

    async def test_list_includes_source_doc_when_present(self, client):
        await _create_product(client, sku="CLAIM-DOC")
        doc_id = await _create_document(client, title="Source Document")
        await _create_claim(
            client,
            claim_text="Anchored claim",
            source_doc_id=doc_id,
        )

        resp = await client.get(
            "/api/v1/products/1/claims",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert len(body) == 1
        assert body[0]["source_doc_id"] == doc_id
        assert body[0]["source_doc"] is not None
        assert body[0]["source_doc"]["title"] == "Source Document"
        assert body[0]["source_doc"]["url"] == "https://example.com/doc"


# ── POST /api/products/{product_id}/claims ───────────────────────────────────


class TestCreateClaim:
    async def test_create_claim_returns_201(self, client):
        await _create_product(client, sku="CLAIM-CREATE")
        resp = await _create_claim(client, claim_text="Amazing product!")
        assert resp.status_code == 201
        body = resp.json()
        assert body["claim_text"] == "Amazing product!"
        assert body["product_id"] == 1
        assert body["status"] == "pending_review"
        assert body["source_doc_id"] is None

    async def test_create_claim_with_source_doc(self, client):
        await _create_product(client, sku="CLAIM-DOC-SRC")
        doc_id = await _create_document(client, title="Spec Sheet")
        resp = await _create_claim(
            client,
            claim_text="5-year warranty",
            source_doc_id=doc_id,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["source_doc_id"] == doc_id

    async def test_create_claim_with_explicit_status(self, client):
        await _create_product(client, sku="CLAIM-STATUS")
        resp = await _create_claim(
            client, claim_text="Fast shipping", status="verified"
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "verified"

    async def test_create_requires_admin(self, client):
        await _create_product(client, sku="CLAIM-ROLE")
        resp = await _create_claim(client, role="editor", claim_text="No permission")
        assert resp.status_code == 403

        resp = await _create_claim(client, role="viewer", claim_text="No permission")
        assert resp.status_code == 403

    async def test_create_requires_auth(self, client):
        await _create_product(client, sku="CLAIM-UNAUTH")
        resp = await client.post(
            "/api/v1/products/1/claims",
            json={"claim_text": "No auth"},
        )
        assert resp.status_code == 401

    async def test_create_with_nonexistent_product_returns_400(self, client):
        resp = await client.post(
            "/api/v1/products/99999/claims",
            json={"claim_text": "Ghost claim"},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    async def test_create_with_source_doc_from_different_product_returns_400(
        self, client
    ):
        # Create two products
        await _create_product(client, sku="PROD-A", name="Product A")
        await _create_product(client, sku="PROD-B", name="Product B")

        # Create document on product A
        doc_id = await _create_document(client, product_id=1, title="Doc for A")

        # Try to create claim on product B with doc from product A
        resp = await _create_claim(
            client,
            product_id=2,
            claim_text="Wrong doc claim",
            source_doc_id=doc_id,
        )
        assert resp.status_code == 400
        assert "does not belong" in resp.json()["detail"]

    async def test_create_with_nonexistent_source_doc_returns_400(self, client):
        await _create_product(client, sku="CLAIM-BAD-DOC")
        resp = await _create_claim(
            client,
            claim_text="Missing doc",
            source_doc_id=99999,
        )
        assert resp.status_code == 400

    async def test_create_default_status_is_pending_review(self, client):
        await _create_product(client, sku="CLAIM-DEFAULT")
        resp = await client.post(
            "/api/v1/products/1/claims",
            json={"claim_text": "No status specified"},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"

    async def test_create_claim_for_soft_deleted_product_returns_400(self, client):
        await _create_product(client, sku="CLAIM-GONE")
        await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("super_admin"),
        )
        resp = await _create_claim(client, claim_text="Late claim")
        assert resp.status_code == 400


# ── PUT /api/claims/{claim_id} ───────────────────────────────────────────────


class TestUpdateClaim:
    async def test_update_claim_text(self, client):
        await _create_product(client, sku="CLAIM-UPD")
        create_resp = await _create_claim(client, claim_text="Original text")
        claim_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/claims/{claim_id}",
            json={"claim_text": "Updated text"},
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 200
        assert resp.json()["claim_text"] == "Updated text"

    async def test_update_claim_status(self, client):
        await _create_product(client, sku="CLAIM-UPD-STATUS")
        create_resp = await _create_claim(client, claim_text="Review me")
        claim_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/claims/{claim_id}",
            json={"status": "verified"},
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "verified"

    async def test_update_both_text_and_status(self, client):
        await _create_product(client, sku="CLAIM-UPD-BOTH")
        create_resp = await _create_claim(client, claim_text="Old")
        claim_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/claims/{claim_id}",
            json={"claim_text": "New and verified", "status": "verified"},
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["claim_text"] == "New and verified"
        assert body["status"] == "verified"

    async def test_update_requires_editor(self, client):
        await _create_product(client, sku="CLAIM-UPD-ROLE")
        create_resp = await _create_claim(client, claim_text="Cant touch this")
        claim_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/claims/{claim_id}",
            json={"claim_text": "Hacked"},
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 403

    async def test_update_requires_auth(self, client):
        resp = await client.put(
            "/api/v1/claims/1",
            json={"claim_text": "No auth"},
        )
        assert resp.status_code == 401

    async def test_update_not_found(self, client):
        resp = await client.put(
            "/api/v1/claims/99999",
            json={"claim_text": "Ghost"},
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 404

    async def test_admin_can_update(self, client):
        """Admin (higher than editor) should also be able to update."""
        await _create_product(client, sku="CLAIM-ADMIN-UPD")
        create_resp = await _create_claim(client, claim_text="Admin update test")
        claim_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/claims/{claim_id}",
            json={"claim_text": "Updated by admin"},
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 200

    async def test_update_response_includes_source_doc(self, client):
        await _create_product(client, sku="CLAIM-UPD-DOC")
        doc_id = await _create_document(client, title="Ref Doc")
        create_resp = await _create_claim(
            client,
            claim_text="Original",
            source_doc_id=doc_id,
        )
        claim_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/claims/{claim_id}",
            json={"claim_text": "Updated"},
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["source_doc"] is not None
        assert body["source_doc"]["title"] == "Ref Doc"


# ── DELETE /api/claims/{claim_id} ────────────────────────────────────────────


class TestDeleteClaim:
    async def test_delete_claim_returns_204(self, client):
        await _create_product(client, sku="CLAIM-DEL")
        create_resp = await _create_claim(client, claim_text="To delete")
        claim_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/claims/{claim_id}",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 204

        # Verify it's gone
        list_resp = await client.get(
            "/api/v1/products/1/claims",
            headers=await _auth_headers("viewer"),
        )
        assert list_resp.json() == []

    async def test_delete_requires_admin(self, client):
        await _create_product(client, sku="CLAIM-DEL-ROLE")
        create_resp = await _create_claim(client, claim_text="No delete")
        claim_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/claims/{claim_id}",
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 403

        resp = await client.delete(
            f"/api/v1/claims/{claim_id}",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 403

    async def test_delete_not_found(self, client):
        resp = await client.delete(
            "/api/v1/claims/99999",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 404

    async def test_delete_requires_auth(self, client):
        resp = await client.delete("/api/v1/claims/1")
        assert resp.status_code == 401


# ── Auth Enforcement ────────────────────────────────────────────────────────


class TestAuthEnforcement:
    """Verifies that all claim endpoints enforce role-based access."""

    async def test_viewer_can_list_but_not_mutate(self, client):
        await _create_product(client, sku="CLAIM-VIEWER")
        create_resp = await _create_claim(client, claim_text="Read only")
        claim_id = create_resp.json()["id"]

        # Viewer can list
        list_r = await client.get(
            "/api/v1/products/1/claims",
            headers=await _auth_headers("viewer"),
        )
        assert list_r.status_code == 200

        # Viewer cannot create
        create_r = await _create_claim(client, role="viewer", claim_text="Nope")
        assert create_r.status_code == 403

        # Viewer cannot update
        update_r = await client.put(
            f"/api/v1/claims/{claim_id}",
            json={"claim_text": "Nope"},
            headers=await _auth_headers("viewer"),
        )
        assert update_r.status_code == 403

        # Viewer cannot delete
        delete_r = await client.delete(
            f"/api/v1/claims/{claim_id}",
            headers=await _auth_headers("viewer"),
        )
        assert delete_r.status_code == 403

    async def test_editor_can_update_but_not_delete(self, client):
        await _create_product(client, sku="CLAIM-EDITOR")
        create_resp = await _create_claim(client, claim_text="Editor test")
        claim_id = create_resp.json()["id"]

        # Editor can list
        list_r = await client.get(
            "/api/v1/products/1/claims",
            headers=await _auth_headers("editor"),
        )
        assert list_r.status_code == 200

        # Editor cannot create
        create_r = await _create_claim(client, role="editor", claim_text="Nope")
        assert create_r.status_code == 403

        # Editor can update
        update_r = await client.put(
            f"/api/v1/claims/{claim_id}",
            json={"claim_text": "Updated by editor"},
            headers=await _auth_headers("editor"),
        )
        assert update_r.status_code == 200

        # Editor cannot delete
        delete_r = await client.delete(
            f"/api/v1/claims/{claim_id}",
            headers=await _auth_headers("editor"),
        )
        assert delete_r.status_code == 403

    async def test_admin_full_access(self, client):
        await _create_product(client, sku="CLAIM-ADMIN")

        # Admin can create
        create_r = await _create_claim(client, role="admin", claim_text="Admin claim")
        assert create_r.status_code == 201
        claim_id = create_r.json()["id"]

        # Admin can update
        update_r = await client.put(
            f"/api/v1/claims/{claim_id}",
            json={"claim_text": "Admin updated"},
            headers=await _auth_headers("admin"),
        )
        assert update_r.status_code == 200

        # Admin can delete
        delete_r = await client.delete(
            f"/api/v1/claims/{claim_id}",
            headers=await _auth_headers("admin"),
        )
        assert delete_r.status_code == 204

    async def test_super_admin_full_access(self, client):
        await _create_product(client, sku="CLAIM-SA")

        # Super admin can create
        create_r = await _create_claim(
            client, role="super_admin", claim_text="SA claim"
        )
        assert create_r.status_code == 201
        claim_id = create_r.json()["id"]

        # Super admin can update
        update_r = await client.put(
            f"/api/v1/claims/{claim_id}",
            json={"claim_text": "SA updated"},
            headers=await _auth_headers("super_admin"),
        )
        assert update_r.status_code == 200

        # Super admin can delete
        delete_r = await client.delete(
            f"/api/v1/claims/{claim_id}",
            headers=await _auth_headers("super_admin"),
        )
        assert delete_r.status_code == 204

    async def test_unauthenticated_rejected(self, client):
        await _create_product(client, sku="CLAIM-UNAUTH2")

        assert (await client.get("/api/v1/products/1/claims")).status_code == 401
        assert (
            await client.post(
                "/api/v1/products/1/claims",
                json={"claim_text": "No auth"},
            )
        ).status_code == 401
        assert (
            await client.put(
                "/api/v1/claims/1",
                json={"claim_text": "No auth"},
            )
        ).status_code == 401
        assert (await client.delete("/api/v1/claims/1")).status_code == 401
