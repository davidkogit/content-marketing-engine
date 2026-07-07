"""
Export API router — CSV download, preview, mapping config, and history.

Mounts under ``/export`` (prefixed by ``/api/v1`` in main.py) and exposes:
- ``GET    /api/export/products/{id}``       — download CSV for a single product
- ``GET    /api/export/products/{id}/preview`` — preview export data as JSON
- ``POST   /api/export/config``               — save mapping config (super_admin)
- ``GET    /api/export/config``               — retrieve current mapping config
- ``GET    /api/export/history``              — paginated export log
"""


import json
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import RoleDTO
from app.config import settings
from app.database import get_db
from app.export.csv_exporter import CSVExporter
from app.export.export_schemas import (
    ClaimMode,
    ExportFieldMapping,
    ExportHistoryItem,
    ExportHistoryResponse,
    ExportMappingConfig,
    ExportPreviewResponse,
)
from app.models.export_log import ExportLog
from app.models.product import Product
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["export"])

# ── Singletons ───────────────────────────────────────────────────────────────

_csv_exporter = CSVExporter()

# ── Default mapping ──────────────────────────────────────────────────────────

_DEFAULT_FIELDS: list[ExportFieldMapping] = [
    ExportFieldMapping(source="sku", label="SKU", enabled=True),
    ExportFieldMapping(source="name", label="Product Name", enabled=True),
    ExportFieldMapping(source="description", label="Description", enabled=True),
    ExportFieldMapping(source="category", label="Category", enabled=False),
    ExportFieldMapping(source="segment", label="Segment", enabled=False),
    ExportFieldMapping(source="claims", label="Claims", enabled=True),
    ExportFieldMapping(source="workflow_stage", label="Stage", enabled=False),
]

_DEFAULT_CONFIG = ExportMappingConfig(
    fields=_DEFAULT_FIELDS,
    claim_mode=ClaimMode.INLINE,
)


# ── Config file persistence ──────────────────────────────────────────────────


def _config_file_path() -> Path:
    """Return the filesystem path where the export mapping config is stored."""
    return settings.database_path.parent / "export_config.json"


def _load_config() -> ExportMappingConfig:
    """Load the saved mapping config, falling back to defaults."""
    path = _config_file_path()
    if not path.exists():
        return _DEFAULT_CONFIG
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ExportMappingConfig.model_validate(data)
    except Exception:
        logger.warning(
            "Failed to parse export config at %s; using defaults.", path
        )
        return _DEFAULT_CONFIG


def _save_config(config: ExportMappingConfig) -> None:
    """Persist the mapping config to disk."""
    path = _config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")


# ── Product loader ───────────────────────────────────────────────────────────


async def _load_product(db: AsyncSession, product_id: int) -> Product:
    """Fetch a non-deleted product with claims eager-loaded, or raise 404."""
    stmt = (
        select(Product)
        .where(Product.id == product_id, Product.is_deleted == False)  # noqa: E712
        .options(
            selectinload(Product.category),
            selectinload(Product.segment),
            selectinload(Product.claims),
        )
    )
    result = await db.execute(stmt)
    product = result.unique().scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id={product_id} not found.",
        )
    return product


# ── GET /api/export/products/{id} ────────────────────────────────────────────


@router.get(
    "/products/{product_id}",
    response_class=PlainTextResponse,
    summary="Export a product as CSV",
)
async def export_product_csv(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PlainTextResponse:
    """Generate and download a CSV file for a single product using the
    current mapping configuration.

    An ``ExportLog`` record is created to track this export event.
    """
    product = await _load_product(db, product_id)
    mapping = _load_config()

    csv_content = _csv_exporter.generate_csv(product, mapping)

    # Record the export event
    log_entry = ExportLog(
        product_id=product.id,
        exported_by=current_user.id,
        mapping_config_json=mapping.model_dump_json(),
    )
    db.add(log_entry)
    await db.flush()

    logger.info(
        "Product id=%d exported as CSV by user_id=%d",
        product_id,
        current_user.id,
    )

    filename = f"{product.sku or product.name}.csv"
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── GET /api/export/products/{id}/preview ────────────────────────────────────


@router.get(
    "/products/{product_id}/preview",
    response_model=ExportPreviewResponse,
    summary="Preview export data as JSON",
)
async def preview_export(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ExportPreviewResponse:
    """Return a structured preview of the data that would be included
    in a CSV export for the given product, without generating the file.

    Useful for frontend UIs that need to show a preview grid before
    the user confirms the download.
    """
    product = await _load_product(db, product_id)
    mapping = _load_config()

    preview_rows = _csv_exporter.preview_data(product, mapping)

    return ExportPreviewResponse(
        product_id=product.id,
        product_name=product.name,
        claim_mode=mapping.claim_mode.value,
        total_rows=len(preview_rows),
        rows=preview_rows,
    )


# ── POST /api/export/config ──────────────────────────────────────────────────


@router.post(
    "/config",
    status_code=status.HTTP_200_OK,
    summary="Save export mapping configuration (Super Admin only)",
)
async def save_export_config(
    body: ExportMappingConfig,
    current_user: Annotated[User, Depends(require_role(RoleDTO.SUPER_ADMIN))],
) -> dict:
    """Persist a new field mapping configuration.

    The config is stored as a JSON file on disk and used by subsequent
    export and preview requests. **super_admin only**.
    """
    _save_config(body)
    logger.info(
        "Export config updated by super_admin user_id=%d", current_user.id
    )
    return {"status": "ok", "message": "Export configuration saved."}


# ── GET /api/export/config ───────────────────────────────────────────────────


@router.get(
    "/config",
    response_model=ExportMappingConfig,
    summary="Get current export mapping configuration",
)
async def get_export_config(
    current_user: Annotated[User, Depends(get_current_user)],
) -> ExportMappingConfig:
    """Return the currently active field mapping configuration.

    All authenticated users may read the config; only super_admins
    may modify it via the POST endpoint.
    """
    return _load_config()


# ── GET /api/export/history ──────────────────────────────────────────────────


@router.get(
    "/history",
    response_model=ExportHistoryResponse,
    summary="List export history",
)
async def list_export_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        20, ge=1, le=100, description="Items per page (max 100)"
    ),
) -> ExportHistoryResponse:
    """Return a paginated list of export log entries, ordered by most
    recent first. Includes the exporting user's email and, when available,
    the mapping configuration used.
    """
    offset = (page - 1) * page_size

    # Count total
    count_stmt = select(func.count()).select_from(ExportLog)
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    # Fetch page with exporter user eager-loaded
    stmt = (
        select(ExportLog)
        .options(selectinload(ExportLog.exporter), selectinload(ExportLog.product))
        .order_by(ExportLog.exported_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    logs: list[ExportLog] = list(result.unique().scalars().all())

    items: list[ExportHistoryItem] = []
    for log in logs:
        mapping_config = None
        if log.mapping_config_json:
            try:
                mapping_config = ExportMappingConfig.model_validate(
                    json.loads(log.mapping_config_json)
                )
            except Exception:
                pass

        items.append(
            ExportHistoryItem(
                id=log.id,
                product_id=log.product_id,
                product_name=log.product.name if log.product else None,
                exported_by=log.exported_by,
                exported_by_email=log.exporter.email if log.exporter else None,
                mapping_config=mapping_config,
                exported_at=log.exported_at,
            )
        )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return ExportHistoryResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
