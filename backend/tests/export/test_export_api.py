"""
Integration tests for the export API endpoints.

Uses an in-memory SQLite database and httpx AsyncClient to exercise
CSV export, preview, mapping config CRUD, export history, and
role-based auth enforcement on export endpoints.
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.jwt_service import JWTService
from app.config import settings
from app.database import Base, get_db
from app.main import create_app
from app.models.product_claim import ProductClaim


# ── Constants ───────────────────────────────────────────────────────────────

_TEST_SECRET: str = os.environ["SECRET_KEY"]
_CONFIG_PATH = settings.database_path.parent / "export_config.json"


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


@pytest.fixture(scope="function", autouse=True)
async def _cleanup_export_config():
    """Remove the export config file before each test to ensure isolation."""
    if _CONFIG_PATH.exists():
        _CONFIG_PATH.unlink()
    yield
    if _CONFIG_PATH.exists():
        _CONFIG_PATH.unlink()


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
    db_session: AsyncSession,
    sku: str = "SKU-001",
    name: str = "Test Product",
    description: str | None = "A test widget.",
    role: str = "admin",
) -> int:
    """Create a product via API and return its ID."""
    resp = await client.post(
        "/api/v1/products",
        json={
            "sku": sku,
            "name": name,
            "description": description,
        },
        headers=await _auth_headers(role),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _add_claims(
    db_session: AsyncSession, product_id: int, texts: list[str]
) -> None:
    """Directly insert claim records for a product."""
    for text in texts:
        claim = ProductClaim(
            product_id=product_id,
            claim_text=text,
        )
        db_session.add(claim)
    await db_session.flush()


# ── GET /api/export/config ──────────────────────────────────────────────────


class TestGetExportConfig:
    async def test_get_config_returns_defaults(self, client):
        """Unauthenticated or fresh state returns default config."""
        resp = await client.get(
            "/api/v1/export/config",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "fields" in body
        assert "claim_mode" in body
        assert body["claim_mode"] == "inline"
        assert len(body["fields"]) == 7

    async def test_get_config_requires_auth(self, client):
        resp = await client.get("/api/v1/export/config")
        assert resp.status_code == 401


# ── POST /api/export/config ─────────────────────────────────────────────────


class TestSaveExportConfig:
    async def test_save_config_super_admin(self, client):
        """Super admin can save a new mapping config."""
        new_config = {
            "fields": [
                {"source": "sku", "label": "SKU", "enabled": True},
                {"source": "name", "label": "Name", "enabled": True},
            ],
            "claim_mode": "expanded",
        }
        resp = await client.post(
            "/api/v1/export/config",
            json=new_config,
            headers=await _auth_headers("super_admin"),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Verify it was saved
        get_resp = await client.get(
            "/api/v1/export/config",
            headers=await _auth_headers("super_admin"),
        )
        saved = get_resp.json()
        assert saved["claim_mode"] == "expanded"
        assert len(saved["fields"]) == 2

    async def test_save_config_requires_super_admin(self, client):
        """Only super_admin can save config. Admin and below get 403."""
        config = {
            "fields": [{"source": "sku", "label": "S", "enabled": True}],
            "claim_mode": "inline",
        }

        for role in ("viewer", "editor", "admin"):
            resp = await client.post(
                "/api/v1/export/config",
                json=config,
                headers=await _auth_headers(role),
            )
            assert resp.status_code == 403, f"{role} should be forbidden"

    async def test_save_config_invalid_schema(self, client):
        """Invalid payload returns 422."""
        resp = await client.post(
            "/api/v1/export/config",
            json={"fields": "not-a-list"},
            headers=await _auth_headers("super_admin"),
        )
        assert resp.status_code == 422


# ── GET /api/export/products/{id}/preview ───────────────────────────────────


class TestPreviewExport:
    async def test_preview_returns_structured_data(self, client, db_session):
        """Preview returns rows with labelled cells."""
        pid = await _create_product(client, db_session, sku="PREV-01")
        await _add_claims(db_session, pid, ["Claim A", "Claim B"])

        resp = await client.get(
            f"/api/v1/export/products/{pid}/preview",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["product_id"] == pid
        assert body["product_name"] == "Test Product"
        assert body["claim_mode"] == "inline"
        assert body["total_rows"] == 1
        assert len(body["rows"]) == 1
        assert len(body["rows"][0]["cells"]) > 0

    async def test_preview_expanded_mode(self, client, db_session):
        """Preview in expanded mode shows one row per claim."""
        # First save expanded config
        config = {
            "fields": [
                {"source": "sku", "label": "SKU", "enabled": True},
                {"source": "claims", "label": "Claims", "enabled": True},
            ],
            "claim_mode": "expanded",
        }
        await client.post(
            "/api/v1/export/config",
            json=config,
            headers=await _auth_headers("super_admin"),
        )

        pid = await _create_product(client, db_session, sku="EXP-01")
        await _add_claims(db_session, pid, ["First claim", "Second claim"])

        resp = await client.get(
            f"/api/v1/export/products/{pid}/preview",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_rows"] == 2
        assert len(body["rows"]) == 2

    async def test_preview_product_not_found(self, client):
        resp = await client.get(
            "/api/v1/export/products/99999/preview",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 404

    async def test_preview_requires_auth(self, client):
        resp = await client.get("/api/v1/export/products/1/preview")
        assert resp.status_code == 401


# ── GET /api/export/products/{id} ───────────────────────────────────────────


class TestExportCSV:
    async def test_export_csv_download(self, client, db_session):
        """Export produces a CSV file download."""
        pid = await _create_product(client, db_session, sku="CSV-01", name="CSV Product")
        await _add_claims(db_session, pid, ["Top quality"])

        resp = await client.get(
            f"/api/v1/export/products/{pid}",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in resp.headers["content-disposition"]

        csv_text = resp.text
        lines = csv_text.strip().split("\r\n")
        assert len(lines) >= 2  # header + data
        assert "SKU" in lines[0]
        assert "CSV-01" in lines[1]

    async def test_export_creates_log(self, client, db_session):
        """Each export creates an ExportLog record."""
        pid = await _create_product(client, db_session, sku="LOG-01")

        resp = await client.get(
            f"/api/v1/export/products/{pid}",
            headers=await _auth_headers("viewer", user_id=99),
        )
        assert resp.status_code == 200

        # Check ExportLog exists
        from app.models.export_log import ExportLog

        logs = (await db_session.execute(select(ExportLog))).scalars().all()
        assert len(logs) == 1
        log = logs[0]
        assert log.product_id == pid
        assert log.exported_by == 99
        assert log.mapping_config_json is not None

    async def test_export_product_not_found(self, client):
        resp = await client.get(
            "/api/v1/export/products/99999",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 404

    async def test_export_requires_auth(self, client):
        resp = await client.get("/api/v1/export/products/1")
        assert resp.status_code == 401


# ── GET /api/export/history ─────────────────────────────────────────────────


class TestExportHistory:
    async def test_history_returns_empty(self, client):
        """History is empty when no exports have occurred."""
        resp = await client.get(
            "/api/v1/export/history",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    async def test_history_lists_exports(self, client, db_session):
        """History returns export records after exports are performed."""
        pid = await _create_product(client, db_session, sku="HIST-01", name="History Product")

        # Perform two exports
        await client.get(
            f"/api/v1/export/products/{pid}",
            headers=await _auth_headers("viewer", user_id=1),
        )
        await client.get(
            f"/api/v1/export/products/{pid}",
            headers=await _auth_headers("viewer", user_id=2),
        )

        resp = await client.get(
            "/api/v1/export/history",
            headers=await _auth_headers("viewer"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        # Most recent first
        items = body["items"]
        assert items[0]["product_id"] == pid
        assert items[0]["exported_by"] == 2
        assert items[1]["exported_by"] == 1
        assert items[0]["product_name"] == "History Product"

    async def test_history_pagination(self, client, db_session):
        """History respects pagination parameters."""
        pid = await _create_product(client, db_session, sku="PAGE-H")

        for i in range(5):
            await client.get(
                f"/api/v1/export/products/{pid}",
                headers=await _auth_headers("viewer"),
            )

        resp = await client.get(
            "/api/v1/export/history?page=1&page_size=2",
            headers=await _auth_headers("viewer"),
        )
        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2
        assert body["total_pages"] == 3

    async def test_history_requires_auth(self, client):
        resp = await client.get("/api/v1/export/history")
        assert resp.status_code == 401


# ── Auth Enforcement ────────────────────────────────────────────────────────


class TestAuthEnforcement:
    async def test_viewer_can_export_and_preview(self, client, db_session):
        """Viewers can read config, preview, and export."""
        pid = await _create_product(client, db_session, sku="AUTH-V")

        # Config
        assert (
            await client.get(
                "/api/v1/export/config",
                headers=await _auth_headers("viewer"),
            )
        ).status_code == 200

        # Preview
        assert (
            await client.get(
                f"/api/v1/export/products/{pid}/preview",
                headers=await _auth_headers("viewer"),
            )
        ).status_code == 200

        # Export
        assert (
            await client.get(
                f"/api/v1/export/products/{pid}",
                headers=await _auth_headers("viewer"),
            )
        ).status_code == 200

        # History
        assert (
            await client.get(
                "/api/v1/export/history",
                headers=await _auth_headers("viewer"),
            )
        ).status_code == 200

    async def test_viewer_cannot_save_config(self, client):
        """Only super_admin can save config."""
        config = {
            "fields": [{"source": "sku", "label": "S", "enabled": True}],
            "claim_mode": "inline",
        }
        for role in ("viewer", "editor", "admin"):
            resp = await client.post(
                "/api/v1/export/config",
                json=config,
                headers=await _auth_headers(role),
            )
            assert resp.status_code == 403

    async def test_unauthenticated_rejected(self, client):
        """All export endpoints reject unauthenticated requests."""
        assert (await client.get("/api/v1/export/config")).status_code == 401
        assert (
            await client.get("/api/v1/export/products/1/preview")
        ).status_code == 401
        assert (
            await client.get("/api/v1/export/products/1")
        ).status_code == 401
        assert (
            await client.get("/api/v1/export/history")
        ).status_code == 401
        assert (
            await client.post(
                "/api/v1/export/config",
                json={"fields": [], "claim_mode": "inline"},
            )
        ).status_code == 401
