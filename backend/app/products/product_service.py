"""
Product service layer — async CRUD with filtering, pagination, and version tracking.

Provides a ProductService class whose methods accept a database session
via dependency injection.  The service is responsible for SKU uniqueness
enforcement, workflow-stage initialisation, and automatic version
snapshot creation when product content changes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product, WorkflowStage
from app.models.product_version import ProductVersion

logger = logging.getLogger(__name__)

# ── Version‑tracking: which fields to snapshot on update ────────────────────

_VERSIONED_FIELDS: tuple[str, ...] = (
    "name",
    "description",
    "category_id",
    "segment_id",
    "workflow_stage",
)


def _build_change_summary(old: dict[str, Any], new: dict[str, Any]) -> str:
    """Produce a human-readable summary of what changed between *old* and *new*."""
    changed: list[str] = []
    for field in _VERSIONED_FIELDS:
        if old.get(field) != new.get(field):
            changed.append(field)
    return ", ".join(changed) if changed else "no detectable changes"


def _serialise_product(product: Product) -> dict[str, Any]:
    """Extract versioned fields from a Product instance as a plain dict."""
    serialised: dict[str, Any] = {}
    for field in _VERSIONED_FIELDS:
        val = getattr(product, field, None)
        if hasattr(val, "value"):
            # Enum → store its string value so JSON is clean
            serialised[field] = val.value
        else:
            serialised[field] = val
    return serialised


# ── ProductService ──────────────────────────────────────────────────────────


class ProductService:
    """Async service for product CRUD, filtering, pagination, and version history.

    All methods accept ``db`` as the first positional argument so that
    callers control session boundaries.  Updates automatically create a
    ``ProductVersion`` snapshot when versioned fields change.
    """

    # ── Create ──────────────────────────────────────────────────────────────

    async def create_product(
        self,
        db: AsyncSession,
        *,
        sku: str,
        name: str,
        description: str | None = None,
        category_id: int | None = None,
        segment_id: int | None = None,
    ) -> Product:
        """Create a new product with initial ``workflow_stage='ingest'``.

        Enforces SKU uniqueness — if a non-deleted product already holds
        the requested SKU a ``ValueError`` is raised.

        Args:
            db: Active database session.
            sku: Unique product identifier.
            name: Display name.
            description: Optional long-form description.
            category_id: Optional category FK.
            segment_id: Optional segment FK.

        Returns:
            The refreshed Product ORM instance.

        Raises:
            ValueError: If the SKU is already taken by an active product.
        """
        existing = await db.execute(
            select(Product).where(
                Product.sku == sku,
                Product.is_deleted == False,  # noqa: E712
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"A product with SKU {sku!r} already exists.")

        product = Product(
            sku=sku,
            name=name,
            description=description,
            category_id=category_id,
            segment_id=segment_id,
            workflow_stage=WorkflowStage.INGEST,
        )
        db.add(product)
        await db.flush()

        result = await db.execute(
            select(Product)
            .where(Product.id == product.id)
            .options(
                selectinload(Product.category),
                selectinload(Product.segment),
                selectinload(Product.documents),
                selectinload(Product.claims),
                selectinload(Product.versions),
            )
        )
        product = result.unique().scalar_one()

        logger.info("Created product id=%d sku=%r", product.id, sku)
        return product

    # ── Read ────────────────────────────────────────────────────────────────

    async def get_product(
        self,
        db: AsyncSession,
        product_id: int,
        *,
        include_deleted: bool = False,
    ) -> Product | None:
        """Fetch a single product with all related data eager-loaded.

        Loads category, segment, documents, claims, and version history
        in a single query using ``selectinload``.

        Args:
            db: Active database session.
            product_id: The product's primary key.
            include_deleted: If True, also return soft-deleted products.

        Returns:
            The eagerly-loaded Product, or None if not found.
        """
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.category),
                selectinload(Product.segment),
                selectinload(Product.documents),
                selectinload(Product.claims),
                selectinload(Product.versions),
            )
        )
        if not include_deleted:
            stmt = stmt.where(Product.is_deleted == False)  # noqa: E712

        result = await db.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_product_by_sku(
        self,
        db: AsyncSession,
        sku: str,
    ) -> Product | None:
        """Look up an active (non-deleted) product by its SKU."""
        result = await db.execute(
            select(Product).where(
                Product.sku == sku,
                Product.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def list_products(
        self,
        db: AsyncSession,
        *,
        category_id: int | None = None,
        segment_id: int | None = None,
        workflow_stage: WorkflowStage | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Product], int]:
        """List products with optional filters and pagination.

        Args:
            db: Active database session.
            category_id: Filter by assigned category.
            segment_id: Filter by assigned segment.
            workflow_stage: Filter by Kanban stage.
            search: Free-text search across name and SKU (case-insensitive).
            page: 1-based page number.
            page_size: Items per page (clamped to 1–100).

        Returns:
            A ``(items, total_count)`` tuple.
        """
        page_size = max(1, min(page_size, 100))
        offset = (page - 1) * page_size

        # Base — only non-deleted products
        base = select(Product).where(Product.is_deleted == False)  # noqa: E712

        # Apply optional filters
        if category_id is not None:
            base = base.where(Product.category_id == category_id)
        if segment_id is not None:
            base = base.where(Product.segment_id == segment_id)
        if workflow_stage is not None:
            base = base.where(Product.workflow_stage == workflow_stage)
        if search:
            pattern = f"%{search}%"
            base = base.where(
                or_(
                    Product.name.ilike(pattern),
                    Product.sku.ilike(pattern),
                )
            )

        # Count total matching rows
        count_stmt = select(func.count()).select_from(base.subquery())
        total_result = await db.execute(count_stmt)
        total: int = total_result.scalar_one()

        # Fetch paginated results
        items_stmt = base.order_by(Product.id).offset(offset).limit(page_size)
        items_result = await db.execute(items_stmt)
        items: list[Product] = list(items_result.scalars().all())

        return items, total

    # ── Update ──────────────────────────────────────────────────────────────

    async def update_product(
        self,
        db: AsyncSession,
        product_id: int,
        *,
        updated_by: int,
        name: str | None = None,
        description: str | None = None,
        category_id: int | None = None,
        segment_id: int | None = None,
        workflow_stage: WorkflowStage | None = None,
    ) -> Product:
        """Partially update a product and create a version snapshot if changed.

        Only non-None fields are applied.  If any versioned field actually
        changes value, a ``ProductVersion`` record is created to preserve
        the pre-edit state.

        Args:
            db: Active database session.
            product_id: The product's primary key.
            updated_by: User ID of the editor (for the version record).
            name: New name (optional).
            description: New description (optional).
            category_id: New category (optional).
            segment_id: New segment (optional).
            workflow_stage: New Kanban stage (optional).

        Returns:
            The refreshed Product ORM instance.

        Raises:
            ValueError: If the product is not found or is soft-deleted.
        """
        product = await self._require_active(db, product_id)

        old_state = _serialise_product(product)

        # Apply changes
        if name is not None:
            product.name = name
        if description is not None:
            product.description = description
        if category_id is not None:
            product.category_id = category_id
        if segment_id is not None:
            product.segment_id = segment_id
        if workflow_stage is not None:
            product.workflow_stage = workflow_stage

        await db.flush()
        new_state = _serialise_product(product)

        # Create version record only if something actually changed
        if old_state != new_state:
            latest = await db.execute(
                select(func.max(ProductVersion.version_number)).where(
                    ProductVersion.product_id == product_id
                )
            )
            next_version = (latest.scalar_one() or 0) + 1

            version = ProductVersion(
                product_id=product.id,
                version_number=next_version,
                snapshot_json=json.dumps(old_state),
                change_summary=_build_change_summary(old_state, new_state),
                created_by=updated_by,
            )
            db.add(version)

        await db.refresh(product)

        logger.info(
            "Updated product id=%d (version %d, changed: %s)",
            product.id,
            next_version if old_state != new_state else 0,
            _build_change_summary(old_state, new_state),
        )
        return product

    # ── Delete ──────────────────────────────────────────────────────────────

    async def soft_delete_product(
        self, db: AsyncSession, product_id: int
    ) -> Product:
        """Mark a product as deleted without removing it from the database.

        Args:
            db: Active database session.
            product_id: The product's primary key.

        Returns:
            The refreshed Product instance with ``is_deleted=True``.

        Raises:
            ValueError: If the product is not found.
        """
        product = await self._require_active(db, product_id)
        product.is_deleted = True
        await db.flush()
        await db.refresh(product)

        logger.info("Soft-deleted product id=%d", product_id)
        return product

    async def hard_delete_product(
        self, db: AsyncSession, product_id: int
    ) -> None:
        """Permanently remove a product and its version history.

        Cascading is handled by SQLAlchemy relationships — child records
        (documents, claims, versions, exports) are also deleted.

        Args:
            db: Active database session.
            product_id: The product's primary key.

        Raises:
            ValueError: If the product is not found.
        """
        product = await self._require_active(db, product_id)
        await db.delete(product)
        await db.flush()

        logger.info("Hard-deleted product id=%d", product_id)

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
