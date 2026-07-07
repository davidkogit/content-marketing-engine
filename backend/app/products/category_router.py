"""
Categories API router — list, create, read, update, and delete categories.

Mounts under ``/api/v1/categories`` and exposes five endpoints.  Write
operations (create, update, delete) require the ADMIN role or higher;
read operations are available to any authenticated user.

Product counts are returned inline on single-category reads so the
frontend can display them without additional requests.
"""


import logging
from typing import Annotated, Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import RoleDTO
from app.database import get_db
from app.models.category import Category
from app.models.user import User
from app.products.category_schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
)
from app.products.category_service import CategoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/categories", tags=["categories"])

# ── Singletons ──────────────────────────────────────────────────────────

_category_service = CategoryService()

# Re-export for app mounting convenience
__all__ = ["router"]


# ── Helpers ─────────────────────────────────────────────────────────────


async def _build_response(
    db: AsyncSession, category: Category
) -> CategoryResponse:
    """Build a ``CategoryResponse`` with the live product count attached.

    ``CategoryResponse.model_validate`` performs the ORM → Pydantic
    conversion, then the ``product_count`` field is injected separately
    because it comes from a subquery rather than the ORM model.
    """
    response = CategoryResponse.model_validate(category)
    response.product_count = await _category_service.get_product_count(
        db, category.id
    )
    return response


# ── GET /categories ─────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[CategoryResponse],
    summary="List all categories",
)
async def list_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    skip: int = 0,
    limit: int = 100,
) -> list[CategoryResponse]:
    """Return all categories ordered by name.

    Any authenticated user may list categories. Product counts are not
    included on the list endpoint to keep the response lean — use the
    single-category endpoint to get the count for a specific category.

    Args:
        db: Per-request database session.
        current_user: Authenticated user (any role).
        skip: Offset for pagination (default 0).
        limit: Max records to return (default 100).

    Returns:
        A list of ``CategoryResponse`` objects.
    """
    categories: Sequence[Category] = await _category_service.list_categories(
        db, skip=skip, limit=limit
    )
    return [CategoryResponse.model_validate(c) for c in categories]


# ── POST /categories ────────────────────────────────────────────────────


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new category",
)
async def create_category(
    body: CategoryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> CategoryResponse:
    """Create a new product category (admin role or higher required).

    The category ``name`` must be unique across the system. Returns the
    newly created category with a 201 CREATED status.

    Args:
        body: Validated category payload with unique name.
        db: Per-request database session.
        admin_user: Authenticated user with ADMIN+ role.

    Returns:
        The newly created ``CategoryResponse``.

    Raises:
        HTTPException 409: If a category with the same name already exists.
        HTTPException 403: If the caller lacks the ADMIN role.
    """
    try:
        category = await _category_service.create_category(
            db,
            name=body.name,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    logger.info(
        "User id=%d created category %r (id=%d)",
        admin_user.id,
        body.name,
        category.id,
    )
    return await _build_response(db, category)


# ── GET /categories/{id} ────────────────────────────────────────────────


@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Get a single category",
)
async def get_category(
    category_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CategoryResponse:
    """Return a single category including its current product count.

    Any authenticated user may access this endpoint.

    Args:
        category_id: The category's primary key.
        db: Per-request database session.
        current_user: Authenticated user (any role).

    Returns:
        A ``CategoryResponse`` with ``product_count`` populated.

    Raises:
        HTTPException 404: If the category does not exist.
    """
    category = await _category_service.get_by_id(db, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with id={category_id!r} not found.",
        )
    return await _build_response(db, category)


# ── PUT /categories/{id} ────────────────────────────────────────────────


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Update an existing category",
)
async def update_category(
    category_id: int,
    body: CategoryUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> CategoryResponse:
    """Update an existing category's name and/or description (admin+ required).

    Only the fields explicitly provided in the request body are changed.
    Renaming to a name already used by another category returns a 409.

    Args:
        category_id: The category's primary key.
        body: Partial update payload — all fields optional.
        db: Per-request database session.
        admin_user: Authenticated user with ADMIN+ role.

    Returns:
        The refreshed ``CategoryResponse``.

    Raises:
        HTTPException 404: If the category does not exist.
        HTTPException 409: If the new name conflicts with another category.
        HTTPException 403: If the caller lacks the ADMIN role.
    """
    try:
        category = await _category_service.update_category(
            db,
            category_id,
            name=body.name,
            description=body.description,
        )
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    logger.info(
        "User id=%d updated category id=%d", admin_user.id, category_id
    )
    return await _build_response(db, category)


# ── DELETE /categories/{id} ─────────────────────────────────────────────


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a category",
)
async def delete_category(
    category_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> None:
    """Delete a category permanently (admin+ required).

    Deletion is **blocked** if any products are still linked to the
    category — those products must be reassigned or removed first.

    Returns ``204 No Content`` on success (no response body).

    Args:
        category_id: The category's primary key.
        db: Per-request database session.
        admin_user: Authenticated user with ADMIN+ role.

    Raises:
        HTTPException 404: If the category does not exist.
        HTTPException 409: If products are still linked to this category.
        HTTPException 403: If the caller lacks the ADMIN role.
    """
    try:
        await _category_service.delete_category(db, category_id)
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    logger.info(
        "User id=%d deleted category id=%d", admin_user.id, category_id
    )
    # FastAPI handles the 204 empty response automatically.
