"""
Product API router — full CRUD with role-based access control.

Mounts under ``/products`` (prefixed by ``/api/v1`` in main.py) and
exposes:
- ``GET    /api/products``        — list with optional filters & pagination
- ``POST   /api/products``        — create new product (admin+)
- ``GET    /api/products/{id}``   — single product with eager-loaded relations
- ``PUT    /api/products/{id}``   — partial update (admin+), tracks version
- ``DELETE /api/products/{id}``   — soft- or hard-delete (super_admin only)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import RoleDTO
from app.database import get_db
from app.models.product import WorkflowStage
from app.models.user import User
from app.products.product_schemas import (
    ProductCreate,
    ProductListItem,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)
from app.products.product_service import ProductService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["products"])

# ── Singleton ───────────────────────────────────────────────────────────────

_product_service = ProductService()

# ── GET /api/products ───────────────────────────────────────────────────────


@router.get(
    "",
    response_model=ProductListResponse,
    summary="List products",
)
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    category_id: int | None = Query(None, description="Filter by category ID"),
    segment_id: int | None = Query(None, description="Filter by segment ID"),
    workflow_stage: WorkflowStage | None = Query(
        None, description="Filter by Kanban workflow stage"
    ),
    search: str | None = Query(
        None, description="Search across product name and SKU (case-insensitive)"
    ),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        20, ge=1, le=100, description="Items per page (max 100)"
    ),
) -> ProductListResponse:
    """Return a paginated, filtered list of products.

    All authenticated users may list products. Soft-deleted products
    are excluded.  Filters are combinable — apply several at once to
    narrow results.
    """
    items, total = await _product_service.list_products(
        db,
        category_id=category_id,
        segment_id=segment_id,
        workflow_stage=workflow_stage,
        search=search,
        page=page,
        page_size=page_size,
    )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return ProductListResponse(
        items=[ProductListItem.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ── POST /api/products ──────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new product",
)
async def create_product(
    body: ProductCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> ProductResponse:
    """Create a new product.  Requires admin or higher role.

    The product is created with ``workflow_stage='ingest'``.  The SKU
    must be unique — a 409 Conflict response is returned if it is already
    in use.
    """
    try:
        product = await _product_service.create_product(
            db,
            sku=body.sku,
            name=body.name,
            description=body.description,
            category_id=body.category_id,
            segment_id=body.segment_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    logger.info(
        "Product created id=%d sku=%r by user_id=%d",
        product.id,
        product.sku,
        current_user.id,
    )
    return ProductResponse.model_validate(product)


# ── GET /api/products/{id} ──────────────────────────────────────────────────


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get a single product",
)
async def get_product(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProductResponse:
    """Return a single product with category, segment, documents, claims,
    and version history eager-loaded.

    Raises 404 if the product does not exist or has been soft-deleted.
    """
    product = await _product_service.get_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id={product_id} not found.",
        )

    return ProductResponse.model_validate(product)


# ── PUT /api/products/{id} ──────────────────────────────────────────────────


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Update a product",
)
async def update_product(
    product_id: int,
    body: ProductUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> ProductResponse:
    """Update a product's metadata.  Requires admin or higher role.

    Only non-null fields in the request body are applied.  If any
    versioned field (name, description, category, segment, stage)
    changes, a version snapshot is automatically created for audit
    purposes.
    """
    try:
        product = await _product_service.update_product(
            db,
            product_id,
            updated_by=current_user.id,
            name=body.name,
            description=body.description,
            category_id=body.category_id,
            segment_id=body.segment_id,
            workflow_stage=body.workflow_stage,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    logger.info(
        "Product id=%d updated by user_id=%d", product_id, current_user.id
    )
    return ProductResponse.model_validate(product)


# ── DELETE /api/products/{id} ───────────────────────────────────────────────


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product (soft or hard)",
)
async def delete_product(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.SUPER_ADMIN))],
    permanent: bool = Query(
        False,
        description="If true, permanently delete. Otherwise soft-delete.",
    ),
) -> None:
    """Delete a product.  **super_admin only**.

    By default performs a soft-delete (marks ``is_deleted=True``).
    Pass ``?permanent=true`` to physically remove the record and all
    associated child data from the database.
    """
    try:
        if permanent:
            await _product_service.hard_delete_product(db, product_id)
            logger.info(
                "Product id=%d permanently deleted by user_id=%d",
                product_id,
                current_user.id,
            )
        else:
            await _product_service.soft_delete_product(db, product_id)
            logger.info(
                "Product id=%d soft-deleted by user_id=%d",
                product_id,
                current_user.id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
