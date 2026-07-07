"""
Product version history API router.

Mounts under ``/products`` (prefixed by ``/api/v1`` in main.py) and
exposes:
- ``GET    /api/products/{id}/versions``              — list versions
- ``GET    /api/products/{id}/versions/{n}``          — single version detail
- ``POST   /api/products/{id}/versions/{n}/restore``  — restore to version (admin+)
"""


import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import RoleDTO
from app.database import get_db
from app.models.user import User
from app.products.version_schemas import VersionListResponse, VersionResponse
from app.products.version_service import VersionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["products", "versions"])

# ── Singleton ───────────────────────────────────────────────────────────────

_version_service = VersionService()

# ── GET /api/products/{product_id}/versions ──────────────────────────────────


@router.get(
    "/{product_id}/versions",
    response_model=VersionListResponse,
    summary="List product versions",
)
async def list_versions(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> VersionListResponse:
    """Return all version records for a product, newest first.

    Includes the full ``snapshot_json`` for each version so consumers
    can inspect historical product state.
    """
    versions = await _version_service.list_versions(db, product_id)
    return VersionListResponse(
        versions=[VersionResponse.model_validate(v) for v in versions],
        total=len(versions),
    )


# ── GET /api/products/{product_id}/versions/{version_number} ─────────────────


@router.get(
    "/{product_id}/versions/{version_number}",
    response_model=VersionResponse,
    summary="Get a specific product version",
)
async def get_version(
    product_id: int,
    version_number: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> VersionResponse:
    """Return a single version record with its full snapshot payload.

    Raises 404 if the version does not exist for this product.
    """
    version = await _version_service.get_version(db, product_id, version_number)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Version {version_number} not found for product "
                f"id={product_id}."
            ),
        )
    return VersionResponse.model_validate(version)


# ── POST /api/products/{product_id}/versions/{version_number}/restore ────────


@router.post(
    "/{product_id}/versions/{version_number}/restore",
    response_model=VersionListResponse,
    summary="Restore product to a previous version",
)
async def restore_version(
    product_id: int,
    version_number: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> VersionListResponse:
    """Restore a product to the state captured in a given version.

    **Requires admin or higher role.**  The operation is append-only:
    a new version is created to record the restore, so no history is
    ever lost.

    Returns the updated version list so the caller can immediately
    see the new restore record.
    """
    try:
        await _version_service.restore_version(
            db,
            product_id,
            version_number,
            restored_by=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    # Return refreshed version list
    versions = await _version_service.list_versions(db, product_id)
    return VersionListResponse(
        versions=[VersionResponse.model_validate(v) for v in versions],
        total=len(versions),
    )
