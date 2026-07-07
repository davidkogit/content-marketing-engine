"""
Category service layer — async CRUD operations with uniqueness validation.

Provides a ``CategoryService`` class whose methods accept a database session
via dependency injection, keeping callers in control of transaction boundaries.
"""


import logging
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.product import Product

logger = logging.getLogger(__name__)


# ── CategoryService ────────────────────────────────────────────────────────


class CategoryService:
    """Async service for category CRUD operations.

    All methods accept ``db`` as the first positional argument (dependency
    injection) so that callers control session lifecycle and transaction
    boundaries.

    Usage:
        service = CategoryService()

        category = await service.create_category(db, name="Electronics")
        found = await service.get_by_id(db, category.id)
    """

    # ── Create ──────────────────────────────────────────────────────────

    async def create_category(
        self,
        db: AsyncSession,
        name: str,
        description: str | None = None,
    ) -> Category:
        """Create a new product category with uniqueness validation.

        Checks that no other category shares the same ``name`` (case-
        sensitive comparison) before inserting.

        Args:
            db: Active database session.
            name: Unique category name (1–255 characters).
            description: Optional free-text description.

        Returns:
            The newly created ``Category`` ORM instance with ``id`` populated.

        Raises:
            ValueError: If a category with the same ``name`` already exists.
        """
        # Guard: name uniqueness
        existing = await db.execute(
            select(Category).where(Category.name == name)
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(
                f"A category with name {name!r} already exists."
            )

        category = Category(name=name, description=description)
        db.add(category)
        await db.flush()
        await db.refresh(category)

        logger.info("Created category %r (id=%d)", name, category.id)
        return category

    # ── Read ────────────────────────────────────────────────────────────

    async def get_by_id(
        self, db: AsyncSession, category_id: int
    ) -> Category | None:
        """Fetch a single category by primary key.

        Args:
            db: Active database session.
            category_id: The category's primary key (integer ID).

        Returns:
            The matching ``Category`` instance, or ``None`` if not found.
        """
        result = await db.execute(
            select(Category).where(Category.id == category_id)
        )
        return result.scalar_one_or_none()

    async def get_product_count(
        self, db: AsyncSession, category_id: int
    ) -> int:
        """Return the number of products linked to the given category.

        Only counts non-deleted products (``is_deleted=False``).

        Args:
            db: Active database session.
            category_id: The category's primary key.

        Returns:
            An integer count (0 or more).
        """
        result = await db.execute(
            select(func.count(Product.id)).where(
                Product.category_id == category_id,
                Product.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def list_categories(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Category]:
        """Return a paginated list of all categories ordered by name.

        Args:
            db: Active database session.
            skip: Number of records to skip (offset). Default 0.
            limit: Maximum number of records to return. Default 100.

        Returns:
            A (possibly empty) sequence of ``Category`` instances.
        """
        result = await db.execute(
            select(Category)
            .order_by(Category.name)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    # ── Update ──────────────────────────────────────────────────────────

    async def update_category(
        self,
        db: AsyncSession,
        category_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Category:
        """Update one or more fields of an existing category.

        Only the explicitly provided fields are mutated. When ``name`` is
        supplied it is validated for uniqueness — a ``ValueError`` is raised
        if another category already uses the requested name.

        Args:
            db: Active database session.
            category_id: The category's primary key.
            name: New unique name (optional).
            description: New description (optional).

        Returns:
            The refreshed ``Category`` instance after the update.

        Raises:
            ValueError: If the category is not found or the new name
                        conflicts with an existing category.
        """
        category = await self._require_category(db, category_id)

        # Uniqueness guard when renaming
        if name is not None and name != category.name:
            duplicate = await db.execute(
                select(Category).where(Category.name == name)
            )
            if duplicate.scalar_one_or_none() is not None:
                raise ValueError(
                    f"A category with name {name!r} already exists."
                )

        if name is not None:
            category.name = name
        if description is not None:
            category.description = description

        await db.flush()
        await db.refresh(category)

        logger.info("Updated category id=%d", category_id)
        return category

    # ── Delete ──────────────────────────────────────────────────────────

    async def delete_category(
        self, db: AsyncSession, category_id: int
    ) -> None:
        """Permanently delete a category after checking for linked products.

        A category with one or more products (excluding soft-deleted products)
        cannot be deleted — the caller must reassign or remove those products
        first.

        Args:
            db: Active database session.
            category_id: The category's primary key.

        Raises:
            ValueError: If the category is not found or has linked products.
        """
        category = await self._require_category(db, category_id)

        # Block deletion if products exist
        product_count = await self.get_product_count(db, category_id)
        if product_count > 0:
            raise ValueError(
                f"Cannot delete category {category.name!r}: "
                f"{product_count} product(s) are still linked to it."
            )

        await db.delete(category)
        await db.flush()

        logger.info("Deleted category id=%d name=%r", category_id, category.name)

    # ── Helpers ─────────────────────────────────────────────────────────

    async def _require_category(
        self, db: AsyncSession, category_id: int
    ) -> Category:
        """Fetch a category by ID or raise ValueError if not found."""
        category = await self.get_by_id(db, category_id)
        if category is None:
            raise ValueError(f"Category with id={category_id!r} not found.")
        return category
