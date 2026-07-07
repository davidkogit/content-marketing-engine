"""
Segment API router — CRUD endpoints for market segments.

Mounts under ``/segments`` and exposes:
- ``GET    /segments`` — list all segments (any authenticated user)
- ``POST   /segments`` — create a segment (admin+ only)
- ``GET    /segments/{id}`` — get segment with product count
- ``PUT    /segments/{id}`` — update a segment (admin+ only)
- ``DELETE /segments/{id}`` — delete a segment (admin+ only, blocked if products exist)
"""


import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import RoleDTO
from app.database import get_db
from app.models.segment import Segment
from app.models.user import User
from app.products.segment_schemas import SegmentCreate, SegmentResponse, SegmentUpdate
from app.products.segment_service import SegmentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/segments", tags=["segments"])

# ── Singletons ──────────────────────────────────────────────────────────────

_service = SegmentService()


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _build_response(db: AsyncSession, segment: Segment) -> SegmentResponse:
    """Build a ``SegmentResponse`` with computed ``product_count``."""
    count = await _service.get_product_count(db, segment.id)
    return SegmentResponse(
        id=segment.id,
        name=segment.name,
        description=segment.description,
        target_audience=segment.target_audience,
        tone=segment.tone,
        created_at=segment.created_at,
        product_count=count,
    )


# ── GET /segments ────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[SegmentResponse],
    summary="List all segments",
)
async def list_segments(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[SegmentResponse]:
    """Return all market segments, ordered by name.

    Accessible by any authenticated user.

    Returns:
        A list of ``SegmentResponse`` objects, each with a computed
        ``product_count``.
    """
    segments = await _service.list_segments(db)
    return [await _build_response(db, seg) for seg in segments]


# ── POST /segments ───────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=SegmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new segment",
)
async def create_segment(
    body: SegmentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> SegmentResponse:
    """Create a new market segment with the given details.

    Requires ADMIN or SUPER_ADMIN role. Name must be unique across all
    segments.

    Returns:
        The newly created ``SegmentResponse`` with ``product_count`` = 0.

    Raises:
        HTTPException 409: If a segment with the same name already exists.
    """
    try:
        segment = await _service.create_segment(
            db,
            name=body.name,
            description=body.description,
            target_audience=body.target_audience,
            tone=body.tone,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return await _build_response(db, segment)


# ── GET /segments/{id} ─────────────────────────────────────────────────────


@router.get(
    "/{segment_id}",
    response_model=SegmentResponse,
    summary="Get a single segment",
)
async def get_segment(
    segment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SegmentResponse:
    """Return a single segment with its product count.

    Accessible by any authenticated user.

    Returns:
        A ``SegmentResponse`` including the number of products assigned
        to this segment.

    Raises:
        HTTPException 404: If no segment exists with the given ID.
    """
    segment = await _service.get_by_id(db, segment_id)
    if segment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment with id={segment_id!r} not found.",
        )

    return await _build_response(db, segment)


# ── PUT /segments/{id} ─────────────────────────────────────────────────────


@router.put(
    "/{segment_id}",
    response_model=SegmentResponse,
    summary="Update a segment",
)
async def update_segment(
    segment_id: int,
    body: SegmentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> SegmentResponse:
    """Update one or more fields of an existing segment.

    Requires ADMIN or SUPER_ADMIN role. Only non-null fields in the
    request body are applied. If ``name`` is updated it must remain unique.

    Returns:
        The refreshed ``SegmentResponse`` with current ``product_count``.

    Raises:
        HTTPException 404: If the segment does not exist.
        HTTPException 409: If the new name conflicts with an existing segment.
    """
    try:
        segment = await _service.update_segment(
            db,
            segment_id,
            name=body.name,
            description=body.description,
            target_audience=body.target_audience,
            tone=body.tone,
        )
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail,
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )

    return await _build_response(db, segment)


# ── DELETE /segments/{id} ──────────────────────────────────────────────────


@router.delete(
    "/{segment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a segment",
)
async def delete_segment(
    segment_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> None:
    """Delete a segment permanently.

    Requires ADMIN or SUPER_ADMIN role. Deletion is **blocked** if any
    products are still assigned to the segment — those products must be
    reassigned or removed first.

    Raises:
        HTTPException 404: If the segment does not exist.
        HTTPException 409: If products are still assigned to this segment.
    """
    try:
        await _service.delete_segment(db, segment_id)
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail,
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )
