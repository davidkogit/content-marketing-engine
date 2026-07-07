"""
Segment service layer — async CRUD operations for market segments.

Provides a ``SegmentService`` class whose methods accept a database session
via dependency injection, keeping callers in control of transaction boundaries.
"""


import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.segment import Segment

logger = logging.getLogger(__name__)


class SegmentService:
    """Async service for segment CRUD operations.

    All methods accept ``db`` as the first positional argument (dependency
    injection) so that callers control session lifecycle and transaction
    boundaries.

    Usage:
        service = SegmentService()

        segment = await service.create_segment(db, name="Enterprise", ...)
        segments = await service.list_segments(db)
    """

    # ── Create ──────────────────────────────────────────────────────────────

    async def create_segment(
        self,
        db: AsyncSession,
        name: str,
        description: str | None = None,
        target_audience: str | None = None,
        tone: str | None = None,
    ) -> Segment:
        """Create a new market segment with a unique name.

        Args:
            db: Active database session.
            name: Unique segment name (max 255 chars).
            description: Optional long-form description.
            target_audience: Optional target audience description.
            tone: Optional tone/voice definition.

        Returns:
            The newly created Segment ORM instance with ``id`` populated.

        Raises:
            ValueError: If a segment with the same name already exists.
        """
        existing = await db.execute(select(Segment).where(Segment.name == name))
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"A segment named {name!r} already exists.")

        segment = Segment(
            name=name,
            description=description,
            target_audience=target_audience,
            tone=tone,
        )
        db.add(segment)
        await db.flush()
        await db.refresh(segment)

        logger.info("Created segment id=%d name=%r", segment.id, segment.name)
        return segment

    # ── Read ────────────────────────────────────────────────────────────────

    async def get_by_id(self, db: AsyncSession, segment_id: int) -> Segment | None:
        """Fetch a segment by primary key.

        Args:
            db: Active database session.
            segment_id: The segment's primary key.

        Returns:
            The matching Segment instance, or ``None`` if not found.
        """
        result = await db.execute(select(Segment).where(Segment.id == segment_id))
        return result.scalar_one_or_none()

    async def list_segments(self, db: AsyncSession) -> list[Segment]:
        """Return all segments ordered by name.

        Args:
            db: Active database session.

        Returns:
            A (possibly empty) list of Segment instances.
        """
        result = await db.execute(select(Segment).order_by(Segment.name))
        return list(result.scalars().all())

    async def get_product_count(self, db: AsyncSession, segment_id: int) -> int:
        """Return the number of products assigned to a segment.

        Args:
            db: Active database session.
            segment_id: The segment's primary key.

        Returns:
            The count of products with ``segment_id`` FK pointing to this segment.
        """
        result = await db.execute(
            select(func.count()).where(Product.segment_id == segment_id)
        )
        # func.count() with a WHERE always returns a single scalar
        return result.scalar() or 0

    # ── Update ──────────────────────────────────────────────────────────────

    async def update_segment(
        self,
        db: AsyncSession,
        segment_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        target_audience: str | None = None,
        tone: str | None = None,
    ) -> Segment:
        """Update one or more segment fields.

        Only non-None keyword arguments are applied. If ``name`` is
        supplied, uniqueness is validated before the update.

        Args:
            db: Active database session.
            segment_id: The segment's primary key.
            name: Optional new name (must be unique).
            description: Optional new description.
            target_audience: Optional new target audience.
            tone: Optional new tone.

        Returns:
            The refreshed Segment instance after the update.

        Raises:
            ValueError: If segment not found or new name conflicts with
                        an existing segment.
        """
        segment = await self._require_segment(db, segment_id)

        if name is not None and name != segment.name:
            # Check uniqueness of the new name
            existing = await db.execute(
                select(Segment).where(Segment.name == name, Segment.id != segment_id)
            )
            if existing.scalar_one_or_none() is not None:
                raise ValueError(f"A segment named {name!r} already exists.")

            segment.name = name

        if description is not None:
            segment.description = description
        if target_audience is not None:
            segment.target_audience = target_audience
        if tone is not None:
            segment.tone = tone

        await db.flush()
        await db.refresh(segment)

        logger.info("Updated segment id=%d", segment_id)
        return segment

    # ── Delete ──────────────────────────────────────────────────────────────

    async def delete_segment(self, db: AsyncSession, segment_id: int) -> None:
        """Delete a segment if it has no associated products.

        Args:
            db: Active database session.
            segment_id: The segment's primary key.

        Raises:
            ValueError: If segment not found or products are still assigned
                        to this segment.
        """
        segment = await self._require_segment(db, segment_id)

        # Guard: block deletion if products reference this segment
        product_count = await self.get_product_count(db, segment_id)
        if product_count > 0:
            raise ValueError(
                f"Cannot delete segment id={segment_id}: "
                f"{product_count} product(s) are still assigned to it. "
                f"Reassign or remove those products first."
            )

        await db.delete(segment)
        await db.flush()

        logger.info("Deleted segment id=%d name=%r", segment_id, segment.name)

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _require_segment(self, db: AsyncSession, segment_id: int) -> Segment:
        """Fetch a segment by ID or raise ValueError if not found."""
        segment = await self.get_by_id(db, segment_id)
        if segment is None:
            raise ValueError(f"Segment with id={segment_id!r} not found.")
        return segment
