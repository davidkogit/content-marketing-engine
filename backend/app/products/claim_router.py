"""
Claims API router — create, list, update, and delete product claims.

Mounts under ``/api/v1`` (prefixed by ``main.py``) and exposes:
- ``POST   /api/products/{id}/claims`` — create claim (admin+)
- ``GET    /api/products/{id}/claims`` — list claims, filterable by status
- ``PUT    /api/claims/{id}``           — update claim text/status (editor+)
- ``DELETE /api/claims/{id}``           — remove claim (admin+)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import RoleDTO
from app.database import get_db
from app.models.product_claim import ClaimStatus
from app.models.user import User
from app.products.claim_schemas import ClaimCreate, ClaimResponse, ClaimUpdate
from app.products.claim_service import ClaimService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["claims"])

# ── Singleton ───────────────────────────────────────────────────────────────

_claim_service = ClaimService()


# ── GET /api/products/{product_id}/claims ────────────────────────────────────


@router.get(
    "/products/{product_id}/claims",
    response_model=list[ClaimResponse],
    summary="List claims for a product",
)
async def list_product_claims(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    status: ClaimStatus | None = Query(
        None,
        description="Filter claims by verification status",
    ),
) -> list[ClaimResponse]:
    """Return all claims for the specified product, optionally filtered by status.

    Any authenticated user may list claims.
    """
    claims = await _claim_service.list_claims(
        db, product_id, status=status
    )
    return [ClaimResponse.model_validate(c) for c in claims]


# ── POST /api/products/{product_id}/claims ───────────────────────────────────


@router.post(
    "/products/{product_id}/claims",
    response_model=ClaimResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new claim",
)
async def create_claim(
    product_id: int,
    body: ClaimCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> ClaimResponse:
    """Create a new claim for a product.  Requires admin or higher.

    If ``source_doc_id`` is provided, the referenced document must belong
    to the same product — otherwise a 400 Bad Request is returned.
    """
    try:
        claim = await _claim_service.create_claim(
            db,
            product_id=product_id,
            claim_text=body.claim_text,
            source_doc_id=body.source_doc_id,
            status=body.status,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    logger.info(
        "Claim id=%d created for product_id=%d by user_id=%d",
        claim.id,
        product_id,
        current_user.id,
    )
    return ClaimResponse.model_validate(claim)


# ── PUT /api/claims/{claim_id} ───────────────────────────────────────────────


@router.put(
    "/claims/{claim_id}",
    response_model=ClaimResponse,
    summary="Update a claim",
)
async def update_claim(
    claim_id: int,
    body: ClaimUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.EDITOR))],
) -> ClaimResponse:
    """Update a claim's text and/or status.  Requires editor or higher.

    Only non-null fields in the request body are applied.
    """
    try:
        claim = await _claim_service.update_claim(
            db,
            claim_id,
            claim_text=body.claim_text,
            status=body.status,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    logger.info(
        "Claim id=%d updated by user_id=%d", claim_id, current_user.id
    )
    return ClaimResponse.model_validate(claim)


# ── DELETE /api/claims/{claim_id} ────────────────────────────────────────────


@router.delete(
    "/claims/{claim_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a claim",
)
async def delete_claim(
    claim_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> None:
    """Permanently delete a claim.  Requires admin or higher.

    Returns ``204 No Content`` on success.
    """
    try:
        await _claim_service.delete_claim(db, claim_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    logger.info(
        "Claim id=%d deleted by user_id=%d", claim_id, current_user.id
    )
