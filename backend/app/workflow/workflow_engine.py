"""
Kanban workflow state machine with role-based transition gating.

Provides a ``WorkflowEngine`` that validates transitions against a
pre-defined DAG of stages, enforces minimum-role rules, and records
every stage change in the product version history.

Key concepts
------------
* **Valid transitions** — a directed acyclic graph mapping each stage
  to the set of stages it may legally advance (or regress) into.
* **Reset** — only ``super_admin`` may move *any* stage back to
  ``INGEST``, regardless of the normal transition graph.
* **Role floors** — each transition declares the minimum ``UserRole``
  required to execute it.  Higher roles inherit the permission.
* **Version tracking** — every call to ``transition()`` writes a
  ``ProductVersion`` row with a full snapshot of the product at the
  point of change, the user who made it, a timestamp, and an optional
  comment.
"""


import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_version import ProductVersion
from app.models.user import User, UserRole
from app.workflow.stage_enum import WorkflowStage

if TYPE_CHECKING:
    from app.models.product import Product

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Exceptions
# ══════════════════════════════════════════════════════════════════════════════


class WorkflowError(Exception):
    """Raised when a requested workflow transition is not permitted.

    Attributes:
        from_stage: The stage the product was in before the attempt.
        to_stage: The stage the caller tried to move to.
        user_role: The ``UserRole`` of the user who attempted the transition.
        reason: A human-readable explanation of why it was rejected.
    """

    def __init__(
        self,
        from_stage: WorkflowStage,
        to_stage: WorkflowStage,
        user_role: UserRole,
        reason: str,
    ) -> None:
        self.from_stage = from_stage
        self.to_stage = to_stage
        self.user_role = user_role
        self.reason = reason
        super().__init__(
            f"Transition {from_stage.value} → {to_stage.value} "
            f"denied for {user_role.value}: {reason}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Configuration tables
# ══════════════════════════════════════════════════════════════════════════════

# Ordered hierarchy — a higher integer means more privileges.
_ROLE_LEVEL: dict[UserRole, int] = {
    UserRole.VIEWER: 0,
    UserRole.EDITOR: 1,
    UserRole.ADMIN: 2,
    UserRole.SUPER_ADMIN: 3,
}

# Valid transitions in the Kanban flow (reset to INGEST is handled separately).
_VALID_TRANSITIONS: dict[WorkflowStage, set[WorkflowStage]] = {
    WorkflowStage.INGEST: {WorkflowStage.DRAFT},
    WorkflowStage.DRAFT: {WorkflowStage.REVIEW},
    WorkflowStage.REVIEW: {WorkflowStage.APPROVED, WorkflowStage.DRAFT},
    WorkflowStage.APPROVED: {WorkflowStage.EXPORTED},
    WorkflowStage.EXPORTED: set(),
}

# Minimum role required for each *non-reset* transition.
# Transitions not listed here have no additional role restriction beyond
# being structurally valid (i.e. VIEWER could technically move them,
# though in practice VIEWER can do nothing because every structural
# transition has a role floor set here).
_TRANSITION_MIN_ROLE: dict[tuple[WorkflowStage, WorkflowStage], UserRole] = {
    (WorkflowStage.INGEST, WorkflowStage.DRAFT): UserRole.EDITOR,
    (WorkflowStage.DRAFT, WorkflowStage.REVIEW): UserRole.EDITOR,
    (WorkflowStage.REVIEW, WorkflowStage.APPROVED): UserRole.ADMIN,
    (WorkflowStage.REVIEW, WorkflowStage.DRAFT): UserRole.EDITOR,
    (WorkflowStage.APPROVED, WorkflowStage.EXPORTED): UserRole.ADMIN,
}


# ══════════════════════════════════════════════════════════════════════════════
# WorkflowEngine
# ══════════════════════════════════════════════════════════════════════════════


class WorkflowEngine:
    """State machine that gates Kanban stage transitions.

    The engine is **stateless** — it holds no database connections or
    product state internally.  All decisions are derived from the
    arguments passed to its methods and the configuration tables above.

    Usage::

        engine = WorkflowEngine()

        # Check permission *before* attempting a move (pure, no I/O).
        if engine.can_transition(product, product.workflow_stage,
                                 WorkflowStage.REVIEW, user.role):
            ...

        # Actually perform the move (async — writes a ProductVersion row).
        await engine.transition(product, WorkflowStage.REVIEW, user, db,
                                comment="Ready for PM review")
    """

    # ── can_transition ──────────────────────────────────────────────────

    def can_transition(
        self,
        product: Product,
        from_stage: WorkflowStage,
        to_stage: WorkflowStage,
        user_role: UserRole,
    ) -> bool:
        """Return ``True`` if the requested move is allowed.

        Args:
            product: The product being moved (reserved for future
                per-product policy checks; currently unused).
            from_stage: The product's current workflow stage.
            to_stage: The desired destination stage.
            user_role: The ``UserRole`` of the user requesting the move.

        Returns:
            ``True`` if the transition is structurally valid and the
            user's role meets or exceeds the required minimum.
        """
        # No-op transitions are never valid.
        if from_stage == to_stage:
            return False

        # Super admin bypasses all gating — they can perform any move
        # including reset-to-ingest and non-standard transitions.
        if user_role == UserRole.SUPER_ADMIN:
            return True

        # ── Reset-to-ingest gate ──────────────────────────────────────
        # Only super_admin may reset.  Non-super users who reached this
        # point are blocked.
        if to_stage == WorkflowStage.INGEST:
            return False

        # ── Structural validity ───────────────────────────────────────
        allowed = _VALID_TRANSITIONS.get(from_stage, set())
        if to_stage not in allowed:
            return False

        # ── Role floor check ──────────────────────────────────────────
        min_role = _TRANSITION_MIN_ROLE.get((from_stage, to_stage))
        if min_role is None:
            # No role restriction for this transition — anyone can do it.
            return True

        user_level = _ROLE_LEVEL.get(user_role, -1)
        required_level = _ROLE_LEVEL.get(min_role, 999)
        return user_level >= required_level

    # ── transition ─────────────────────────────────────────────────────

    async def transition(
        self,
        db: AsyncSession,
        product: "Product",
        target: WorkflowStage,
        user: User,
        *,
        comment: str | None = None,
    ) -> Product:
        """Validate and execute a workflow stage transition.

        Performs the following steps atomically (within the caller's
        transaction):

        1. Validates the transition via :meth:`can_transition`.
        2. Computes the next version number for the product.
        3. Snapshots the current product state as JSON.
        4. Writes a ``ProductVersion`` row capturing who moved it, when,
           which stages were involved, and the optional comment.
        5. Updates the product's ``workflow_stage`` column.
        6. Flushes the session so changes are visible to subsequent
           queries in the same transaction.

        Args:
            product: The ORM ``Product`` instance to transition.
            to_stage: The target workflow stage.
            user: The ``User`` making the change.
            db: An active async SQLAlchemy session.
            comment: Optional human-readable note (e.g. reason for
                requesting changes on a ``review → draft`` return).

        Returns:
            The updated ``Product`` instance (same object, mutated in-place).

        Raises:
            WorkflowError: If the transition is not permitted.
        """
        from_stage = product.workflow_stage

        if not self.can_transition(product, from_stage, to_stage, user.role):
            raise WorkflowError(
                from_stage=from_stage,
                to_stage=to_stage,
                user_role=user.role,
                reason=(
                    "Reset requires super_admin"
                    if to_stage == WorkflowStage.INGEST
                    else (
                        "Same stage"
                        if from_stage == to_stage
                        else "Transition not allowed or insufficient role"
                    )
                ),
            )

        logger.info(
            "Transitioning product %d (%s): %s → %s by user %d (%s)",
            product.id,
            product.sku,
            from_stage.value,
            to_stage.value,
            user.id,
            user.role.value,
        )

        # ── Determine next version number ─────────────────────────────
        result = await db.execute(
            select(func.coalesce(func.max(ProductVersion.version_number), 0)).where(
                ProductVersion.product_id == product.id
            )
        )
        max_version: int = result.scalar_one()
        next_version = max_version + 1

        # ── Snapshot current product state ────────────────────────────
        snapshot: dict = {
            "id": product.id,
            "sku": product.sku,
            "name": product.name,
            "description": product.description,
            "category_id": product.category_id,
            "segment_id": product.segment_id,
            "workflow_stage": from_stage.value,
        }

        # ── Build the change summary for the audit trail ──────────────
        summary_parts: list[str] = [
            f"Stage: {from_stage.value} → {to_stage.value}"
        ]
        if comment:
            summary_parts.append(f"Comment: {comment}")

        # ── Record the version ────────────────────────────────────────
        version = ProductVersion(
            product_id=product.id,
            version_number=next_version,
            snapshot_json=json.dumps(snapshot, ensure_ascii=False),
            change_summary=" | ".join(summary_parts),
            created_by=user.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(version)

        # ── Advance the product stage ─────────────────────────────────
        product.workflow_stage = to_stage

        await db.flush()

        logger.info(
            "Product %d transitioned to %s (version %d)",
            product.id,
            to_stage.value,
            next_version,
        )
        return product
