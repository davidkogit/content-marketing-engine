"""
Integration tests for the product documents API endpoints.

Uses an in-memory SQLite database and httpx AsyncClient to exercise
document creation (with auto-fetched titles), listing, deletion, and
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
os.environ.setdefault("LLM_API_KEY", "test-llm-api-key")

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.jwt_service import JWTService
from app.database import Base, get_db
from app.documents.url_fetcher import FetchedContent
from app.main import create_app
from app.models.product import Product
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


# ── Product Helper ──────────────────────────────────────────────────────────


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


# ── Mock URLFetcher Helper ──────────────────────────────────────────────────


def _mock_fetched_content(title: str = "Test Page Title") -> FetchedContent:
    """Return a FetchedContent with a known title for testing."""
    return FetchedContent(
        url="https://example.com/doc.pdf",
        status_code=200,
        content_type="application/pdf",
        title=title,
        raw_text="Sample extracted text for testing.",
    )


# ── GET /api/products/{product_id}/documents ─────────────────────────────────


class TestListDocuments:
    async def test_list_returns_empty_when_no_documents(self, client):
        await _create_product(client, sku="DOC-EMPTY")
        resp = await client.get(
            "/api/v1/products/1/documents",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_requires_auth(self, client):
        await _create_product(client, sku="DOC-AUTH")
        resp = await client.get("/api/v1/products/1/documents")
        assert resp.status_code == 401

    async def test_list_returns_documents(self, client):
        await _create_product(client, sku="DOC-LIST")
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content("Alpha Doc"),
        ):
            await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/alpha", "doc_type": "url"},
                headers=await _auth_headers("admin"),
            )
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content("Beta Doc"),
        ):
            await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/beta.pdf", "doc_type": "pdf"},
                headers=await _auth_headers("admin"),
            )

        resp = await client.get(
            "/api/v1/products/1/documents",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["title"] == "Alpha Doc"
        assert body[0]["doc_type"] == "url"
        assert body[1]["title"] == "Beta Doc"
        assert body[1]["doc_type"] == "pdf"


# ── POST /api/products/{product_id}/documents ────────────────────────────────


class TestCreateDocument:
    async def test_create_document_returns_201(self, client):
        await _create_product(client, sku="DOC-CREATE")
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content("My Document"),
        ):
            resp = await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/doc", "doc_type": "url"},
                headers=await _auth_headers("admin"),
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "My Document"
        assert body["url"] == "https://example.com/doc"
        assert body["doc_type"] == "url"
        assert body["product_id"] == 1
        assert body["extracted_text"] is None

    async def test_create_requires_admin(self, client):
        await _create_product(client, sku="DOC-ROLE")
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content(),
        ):
            resp = await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/doc", "doc_type": "url"},
                headers=await _auth_headers("editor"),
            )
        assert resp.status_code == 403

        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content(),
        ):
            resp = await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/doc", "doc_type": "url"},
                headers=await _auth_headers("viewer"),
            )
        assert resp.status_code == 403

    async def test_create_requires_auth(self, client):
        await _create_product(client, sku="DOC-UNAUTH")
        resp = await client.post(
            "/api/v1/products/1/documents",
            json={"url": "https://example.com/doc", "doc_type": "url"},
        )
        assert resp.status_code == 401

    async def test_create_with_nonexistent_product_returns_404(self, client):
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content(),
        ):
            resp = await client.post(
                "/api/v1/products/99999/documents",
                json={"url": "https://example.com/doc", "doc_type": "url"},
                headers=await _auth_headers("admin"),
            )
        assert resp.status_code == 404

    async def test_create_falls_back_to_url_path_when_fetch_fails(self, client):
        await _create_product(client, sku="DOC-FALLBACK")
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            resp = await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/some/path/document.pdf", "doc_type": "pdf"},
                headers=await _auth_headers("admin"),
            )
        assert resp.status_code == 201
        body = resp.json()
        # Fallback title derived from URL path
        assert "document.pdf" in body["title"]

    async def test_create_document_for_soft_deleted_product_returns_404(self, client):
        await _create_product(client, sku="DOC-DELETED")
        await client.delete(
            "/api/v1/products/1",
            headers=await _auth_headers("super_admin"),
        )
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content(),
        ):
            resp = await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/doc", "doc_type": "url"},
                headers=await _auth_headers("admin"),
            )
        assert resp.status_code == 404


# ── DELETE /api/documents/{document_id} ──────────────────────────────────────


class TestDeleteDocument:
    async def test_delete_document_returns_204(self, client):
        await _create_product(client, sku="DOC-DEL")
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content("To Delete"),
        ):
            create_resp = await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/doc", "doc_type": "url"},
                headers=await _auth_headers("admin"),
            )
        doc_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/documents/{doc_id}",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 204

        # Verify it's gone
        list_resp = await client.get(
            "/api/v1/products/1/documents",
            headers=await _auth_headers("viewer"),
        )
        assert list_resp.json() == []

    async def test_delete_requires_admin(self, client):
        await _create_product(client, sku="DOC-ROLE-DEL")
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content(),
        ):
            create_resp = await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/doc", "doc_type": "url"},
                headers=await _auth_headers("admin"),
            )
        doc_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/documents/{doc_id}",
            headers=await _auth_headers("editor"),
        )
        assert resp.status_code == 403

        resp = await client.delete(
            f"/api/v1/documents/{doc_id}",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 403

    async def test_delete_not_found(self, client):
        resp = await client.delete(
            "/api/v1/documents/99999",
            headers=await _auth_headers("admin"),
        )
        assert resp.status_code == 404

    async def test_delete_requires_auth(self, client):
        resp = await client.delete("/api/v1/documents/1")
        assert resp.status_code == 401


# ── Auth Enforcement ────────────────────────────────────────────────────────


class TestAuthEnforcement:
    """Verifies that all document endpoints enforce role-based access."""

    async def test_viewer_can_list_but_not_mutate(self, client):
        await _create_product(client, sku="DOC-VIEWER")
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content(),
        ):
            create_resp = await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/doc", "doc_type": "url"},
                headers=await _auth_headers("admin"),
            )
        doc_id = create_resp.json()["id"]

        # Viewer can list
        list_r = await client.get(
            "/api/v1/products/1/documents",
            headers=await _auth_headers("viewer"),
        )
        assert list_r.status_code == 200

        # Viewer cannot create
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content(),
        ):
            create_r = await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/another", "doc_type": "url"},
                headers=await _auth_headers("viewer"),
            )
        assert create_r.status_code == 403

        # Viewer cannot delete
        delete_r = await client.delete(
            f"/api/v1/documents/{doc_id}",
            headers=await _auth_headers("viewer"),
        )
        assert delete_r.status_code == 403

    async def test_editor_can_list_but_not_mutate(self, client):
        await _create_product(client, sku="DOC-EDITOR")
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content(),
        ):
            create_resp = await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/doc", "doc_type": "url"},
                headers=await _auth_headers("admin"),
            )
        doc_id = create_resp.json()["id"]

        # Editor can list
        list_r = await client.get(
            "/api/v1/products/1/documents",
            headers=await _auth_headers("editor"),
        )
        assert list_r.status_code == 200

        # Editor cannot create
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content(),
        ):
            create_r = await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/another", "doc_type": "url"},
                headers=await _auth_headers("editor"),
            )
        assert create_r.status_code == 403

        # Editor cannot delete
        delete_r = await client.delete(
            f"/api/v1/documents/{doc_id}",
            headers=await _auth_headers("editor"),
        )
        assert delete_r.status_code == 403

    async def test_super_admin_full_access(self, client):
        await _create_product(client, sku="DOC-SA")

        # Create
        with patch(
            "app.products.document_service.URLFetcher.fetch",
            new_callable=AsyncMock,
            return_value=_mock_fetched_content("SA Doc"),
        ):
            create_r = await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/doc", "doc_type": "url"},
                headers=await _auth_headers("super_admin"),
            )
        assert create_r.status_code == 201
        doc_id = create_r.json()["id"]

        # List
        list_r = await client.get(
            "/api/v1/products/1/documents",
            headers=await _auth_headers("super_admin"),
        )
        assert list_r.status_code == 200

        # Delete
        delete_r = await client.delete(
            f"/api/v1/documents/{doc_id}",
            headers=await _auth_headers("super_admin"),
        )
        assert delete_r.status_code == 204

    async def test_unauthenticated_rejected(self, client):
        await _create_product(client, sku="DOC-UNAUTH2")

        assert (await client.get("/api/v1/products/1/documents")).status_code == 401
        assert (
            await client.post(
                "/api/v1/products/1/documents",
                json={"url": "https://example.com/doc", "doc_type": "url"},
            )
        ).status_code == 401
        assert (await client.delete("/api/v1/documents/1")).status_code == 401
