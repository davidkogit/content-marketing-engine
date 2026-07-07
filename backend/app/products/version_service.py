"""
Product version service layer — listing, detail retrieval, and restore.

Provides a ``VersionService`` class that works alongside the existing
``ProductService`` version-tracking infrastructure.  The restore
operation creates a new version recording the rollback so the audit
trail is never truncated.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, WorkflowStage
from app.models.product_version import ProductVersion

logger = logging.getLogger(__name__)

# ── Versioned fields (mirrors product_service._VERSIONED_FIELDS) ────────────

_VERSIONED_FIELDS: tuple[str, ...] = (
    "name",
    "description",
    "category_id",
    "segment_id",
    "workflow_stage",
)

_WORKFLOW_STAGE_MAP: dict[str, WorkflowStage] = {
    stage.value: stage for stage in WorkflowStage
}


def _parse_snapshot(snapshot_json: str) -> dict[str, Any]:
    """Parse a version snapshot JSON string into a field→value dict.

    Returns an empty dict on malformed JSON (edge-case guard).
    """
    try:
        return json.loads(snapshot_json)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse snapshot_json; returning empty dict.")
        return {}


def _build_restore_summary(version_number: int) -> str:
    """Produce a change summary indicating a restore action."""
    return f"Restored to version {version_number}"


# ── VersionService ───────────────────────────────────────────────────────────


class VersionService:
    """Async service for querying and restoring product version history.

    All methods accept ``db`` as the first positional argument so that
    callers control session boundaries.
    """

    # ── List ───────────────────────────────────────────────────────────────

    async def list_versions(
        self,
        db: AsyncSession,
        product_id: int,
    ) -> list[ProductVersion]:
        """Return all versions for a product, newest first.

        Args:
            db: Active database session.
            product_id: The product whose versions to list.

        Returns:
            A list of ``ProductVersion`` ORM instances ordered by
            ``version_number`` descending.
        """
        stmt = (
            select(ProductVersion)
            .where(ProductVersion.product_id == product_id)
            .order_by(ProductVersion.version_number.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── Get ────────────────────────────────────────────────────────────────

    async def get_version(
        self,
        db: AsyncSession,
        product_id: int,
        version_number: int,
    ) -> ProductVersion | None:
        """Fetch a specific version by product and version number.

        Args:
            db: Active database session.
            product_id: The owning product's ID.
            version_number: The sequential version number to fetch.

        Returns:
            The ``ProductVersion`` ORM instance, or ``None`` if not found.
        """
        stmt = select(ProductVersion).where(
            ProductVersion.product_id == product_id,
            ProductVersion.version_number == version_number,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # ── Restore ────────────────────────────────────────────────────────────

    async def restore_version(
        self,
        db: AsyncSession,
        product_id: int,
        version_number: int,
        *,
        restored_by: int,
    ) -> Product:
        """Restore a product to the state captured in a previous version.

        Applies the snapshot fields to the product, then creates a **new**
        version record documenting the restore (so the audit trail is
        always append-only).

        Args:
            db: Active database session.
            product_id: The product to restore.
            version_number: The version whose state should be restored.
            restored_by: User ID performing the restore.

        Returns:
            The refreshed ``Product`` ORM instance after restoration.

        Raises:
            ValueError: If the product is not found, is soft-deleted,
                        or the target version does not exist.
        """
        # ── Validate product exists and is active ──────────────────────
        product = await self._require_active(db, product_id)

        # ── Validate target version exists ─────────────────────────────
        version = await self.get_version(db, product_id, version_number)
        if version is None:
            raise ValueError(
                f"Version {version_number} not found for product id={product_id}."
            )

        # ── Parse snapshot ─────────────────────────────────────────────
        snapshot = _parse_snapshot(version.snapshot_json)
        if not snapshot:
            raise ValueError(
                f"Version {version_number} snapshot is empty or corrupt."
            )

        # ── Calculate next version number ──────────────────────────────
        latest = await db.execute(
            select(func.max(ProductVersion.version_number)).where(
                ProductVersion.product_id == product_id
            )
        )
        next_version = (latest.scalar_one() or 0) + 1

        # ── Build current-state snapshot BEFORE applying restore ───────
        old_state: dict[str, Any] = {}
        for field in _VERSIONED_FIELDS:
            val = getattr(product, field, None)
            if hasattr(val, "value"):
                old_state[field] = val.value
            else:
                old_state[field] = val

        # ── Apply snapshot fields to product ───────────────────────────
        for field in _VERSIONED_FIELDS:
            if field not in snapshot:
                continue
            value = snapshot[field]
            # Handle workflow_stage enum
            if field == "workflow_stage" and isinstance(value, str):
                try:
                    value = _WORKFLOW_STAGE_MAP[value]
                except KeyError:
                    logger.warning(
                        "Unknown workflow_stage value %r in snapshot; skipping.",
                        value,
                    )
                    continue
            setattr(product, field, value)

        await db.flush()

        # ── Create new version recording the restore ───────────────────
        restore_version = ProductVersion(
            product_id=product.id,
            version_number=next_version,
            snapshot_json=json.dumps(old_state),
            change_summary=_build_restore_summary(version_number),
            created_by=restored_by,
        )
        db.add(restore_version)
        await db.flush()
        await db.refresh(product)

        logger.info(
            "Product id=%d restored to version %d (new version %d) by user_id=%d",
            product.id,
            version_number,
            next_version,
            restored_by,
        )
        return product

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _require_active(
        self, db: AsyncSession, product_id: int
    ) -> Product:
        """Fetch an active (non-deleted) product or raise ValueError."""
        result = await db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.is_deleted == False,  # noqa: E712
            )
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise ValueError(f"Product with id={product_id!r} not found.")
        return product
