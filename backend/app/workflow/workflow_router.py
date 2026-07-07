"""
Workflow API router — Kanban board view, stage transitions, approval gates,
and workflow history timeline.

Mounts under ``/workflow`` (prefixed by ``/api/v1`` in main.py) and exposes:
- GET    /api/v1/workflow/board                          — Kanban board view
- POST   /api/v1/workflow/products/{id}/transition        — transition product
- POST   /api/v1/workflow/products/{id}/approve            — approve shortcut
- POST   /api/v1/workflow/products/{id}/request-changes    — reject shortcut
- GET    /api/v1/workflow/products/{id}/history            — transition timeline
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import RoleDTO
from app.database import get_db
from app.models.product import Product, WorkflowStage
from app.models.product_version import ProductVersion
from app.models.user import User
from app.workflow.workflow_engine import WorkflowEngine, WorkflowError
from app.workflow.workflow_schemas import (
    BoardColumn,
    BoardProductItem,
    BoardResponse,
    RequestChangesRequest,
    TransitionRequest,
    TransitionResponse,
    WorkflowHistoryItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow", tags=["workflow"])

# ── Singleton ─────────────────────────────────────────────────────────────────

_engine = WorkflowEngine()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_transition(change_summary: str | None) -> tuple[str, str] | None:
    """Extract from_stage and to_stage from a ProductVersion change_summary.

    Expected format: ``"Stage: {from_stage} → {to_stage}"`` possibly followed
    by ``" | Comment: ..."``.  Returns a ``(from_stage, to_stage)`` tuple,
    or ``None`` if the summary does not describe a stage transition.
    """
    if not change_summary:
        return None
    first_part = change_summary.split(" | ")[0]
    if not first_part.startswith("Stage:"):
        return None
    stages_part = first_part[len("Stage:"):].strip()
    if " → " not in stages_part:
        return None
    parts = stages_part.split(" → ", 1)
    return (parts[0].strip(), parts[1].strip())


def _extract_comment(change_summary: str | None) -> str | None:
    """Extract the optional comment portion from a change_summary string."""
    if not change_summary:
        return None
    parts = change_summary.split(" | ")
    for part in parts[1:]:
        if part.startswith("Comment: "):
            return part[len("Comment: "):]
    return None


async def _get_active_product(
    db: AsyncSession, product_id: int
) -> Product | None:
    """Fetch an active (non-deleted) product by ID, returning None if not found."""
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


# ── GET /api/v1/workflow/board ───────────────────────────────────────────────


@router.get(
    "/board",
    response_model=BoardResponse,
    summary="Get Kanban board view",
)
async def get_board(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BoardResponse:
    """Return all active products grouped by workflow stage (Kanban columns).

    Each column includes the stage name, product count, and the list of
    products currently in that stage.  Columns are ordered by the natural
    workflow progression: ingest → draft → review → approved → exported.
    Empty columns are still included so the board view is consistent.
    """
    result = await db.execute(
        select(Product).where(Product.is_deleted == False)  # noqa: E712
    )
    products: list[Product] = list(result.scalars().all())

    stage_order = [
        WorkflowStage.INGEST,
        WorkflowStage.DRAFT,
        WorkflowStage.REVIEW,
        WorkflowStage.APPROVED,
        WorkflowStage.EXPORTED,
    ]

    grouped: dict[WorkflowStage, list[Product]] = {s: [] for s in stage_order}
    for p in products:
        grouped[p.workflow_stage].append(p)

    columns: list[BoardColumn] = []
    for stage in stage_order:
        items = grouped[stage]
        columns.append(
            BoardColumn(
                stage=stage.value,
                count=len(items),
                products=[BoardProductItem.model_validate(p) for p in items],
            )
        )

    return BoardResponse(columns=columns)


# ── POST /api/v1/workflow/products/{id}/transition ───────────────────────────


@router.post(
    "/products/{product_id}/transition",
    response_model=TransitionResponse,
    summary="Transition a product to a new stage",
)
async def transition_product(
    product_id: int,
    body: TransitionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TransitionResponse:
    """Transition a product to a new workflow stage.

    Validates the transition against the workflow DAG and role permissions.
    Records the change as a ``ProductVersion`` snapshot.  All authenticated
    users may attempt transitions — the ``WorkflowEngine`` enforces role gates.

    Returns 404 if the product does not exist or has been soft-deleted.
    Returns 422 if the transition is invalid (wrong stage, insufficient role).
    """
    product = await _get_active_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id={product_id} not found.",
        )

    from_stage = product.workflow_stage

    try:
        await _engine.transition(
            product, body.to_stage, current_user, db, comment=body.comment
        )
    except WorkflowError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.reason,
        )

    # Retrieve the version number just created for the response.
    latest_result = await db.execute(
        select(ProductVersion.version_number)
        .where(ProductVersion.product_id == product_id)
        .order_by(ProductVersion.version_number.desc())
        .limit(1)
    )
    version_number = latest_result.scalar_one()

    logger.info(
        "Product id=%d transitioned %s → %s by user_id=%d",
        product_id,
        from_stage.value,
        body.to_stage.value,
        current_user.id,
    )
    return TransitionResponse(
        product_id=product_id,
        from_stage=from_stage.value,
        to_stage=body.to_stage.value,
        version_number=version_number,
        comment=body.comment,
    )


# ── POST /api/v1/workflow/products/{id}/approve ──────────────────────────────


@router.post(
    "/products/{product_id}/approve",
    response_model=TransitionResponse,
    summary="Approve a product (admin+ shortcut)",
)
async def approve_product(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> TransitionResponse:
    """Shortcut to approve a product — transitions it to the APPROVED stage.

    Requires **admin** or higher role.  The product must be in the REVIEW
    stage for this transition to be valid.  Use the full
    ``POST /workflow/products/{id}/transition`` endpoint if you need to
    attach an optional comment.

    Returns 404 if the product does not exist or has been soft-deleted.
    Returns 422 if the transition is invalid.
    """
    product = await _get_active_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id={product_id} not found.",
        )

    from_stage = product.workflow_stage

    try:
        await _engine.transition(
            product, WorkflowStage.APPROVED, current_user, db
        )
    except WorkflowError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.reason,
        )

    latest_result = await db.execute(
        select(ProductVersion.version_number)
        .where(ProductVersion.product_id == product_id)
        .order_by(ProductVersion.version_number.desc())
        .limit(1)
    )
    version_number = latest_result.scalar_one()

    logger.info(
        "Product id=%d approved by user_id=%d", product_id, current_user.id
    )
    return TransitionResponse(
        product_id=product_id,
        from_stage=from_stage.value,
        to_stage=WorkflowStage.APPROVED.value,
        version_number=version_number,
        comment=None,
    )


# ── POST /api/v1/workflow/products/{id}/request-changes ─────────────────────


@router.post(
    "/products/{product_id}/request-changes",
    response_model=TransitionResponse,
    summary="Request changes — send back to draft (editor+ shortcut)",
)
async def request_changes(
    product_id: int,
    body: RequestChangesRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.EDITOR))],
) -> TransitionResponse:
    """Shortcut to request changes — transitions product back to DRAFT stage.

    Requires **editor** or higher role.  The product must be in the REVIEW
    stage.  A comment explaining what changes are needed is **required**
    and will be recorded in the audit trail.

    Returns 404 if the product does not exist or has been soft-deleted.
    Returns 422 if the transition is invalid.
    """
    product = await _get_active_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id={product_id} not found.",
        )

    from_stage = product.workflow_stage

    try:
        await _engine.transition(
            product, WorkflowStage.DRAFT, current_user, db, comment=body.comment
        )
    except WorkflowError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.reason,
        )

    latest_result = await db.execute(
        select(ProductVersion.version_number)
        .where(ProductVersion.product_id == product_id)
        .order_by(ProductVersion.version_number.desc())
        .limit(1)
    )
    version_number = latest_result.scalar_one()

    logger.info(
        "Product id=%d sent back to draft by user_id=%d",
        product_id,
        current_user.id,
    )
    return TransitionResponse(
        product_id=product_id,
        from_stage=from_stage.value,
        to_stage=WorkflowStage.DRAFT.value,
        version_number=version_number,
        comment=body.comment,
    )


# ── GET /api/v1/workflow/products/{id}/history ───────────────────────────────


@router.get(
    "/products/{product_id}/history",
    response_model=list[WorkflowHistoryItem],
    summary="Get workflow transition history",
)
async def get_workflow_history(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[WorkflowHistoryItem]:
    """Return the timeline of all stage transitions for a product.

    Only ``ProductVersion`` records that represent stage transitions are
    included (those whose ``change_summary`` starts with ``"Stage:"``).
    Results are ordered chronologically by creation time.

    Returns 404 if the product does not exist or has been soft-deleted.
    Returns an empty list if the product has no transition history.
    """
    exists = await _get_active_product(db, product_id)
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id={product_id} not found.",
        )

    versions_result = await db.execute(
        select(ProductVersion)
        .where(ProductVersion.product_id == product_id)
        .order_by(ProductVersion.created_at.asc())
    )
    versions = versions_result.scalars().all()

    history: list[WorkflowHistoryItem] = []
    for v in versions:
        parsed = _parse_transition(v.change_summary)
        if parsed is None:
            continue  # skip edit-only versions (no stage change)

        from_stage, to_stage = parsed
        comment = _extract_comment(v.change_summary)

        history.append(
            WorkflowHistoryItem(
                id=v.id,
                version_number=v.version_number,
                from_stage=from_stage,
                to_stage=to_stage,
                change_summary=v.change_summary,
                comment=comment,
                created_by=v.created_by,
                created_at=v.created_at,
            )
        )

    return history
