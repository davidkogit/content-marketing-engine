"""
Claim service layer — async CRUD for product claims with validation rules.

Provides ClaimService with methods for creating, listing (with optional
status filter), updating, and deleting claims.  Cross-entity validation
ensures source documents belong to the same product when referenced.
"""


import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product
from app.models.product_claim import ClaimStatus, ProductClaim
from app.models.product_document import ProductDocument

logger = logging.getLogger(__name__)


# ── ClaimService ────────────────────────────────────────────────────────────


class ClaimService:
    """Async service for product claim CRUD with cross-entity validation.

    All methods accept ``db`` as the first positional argument so that
    callers control session boundaries and transaction semantics.

    Validation rules enforced by this service:
    - The product must exist and be active (non-deleted).
    - When ``source_doc_id`` is provided, the document must exist and
      belong to the same product.

    Usage::

        service = ClaimService()
        claim = await service.create_claim(db, product_id=1, claim_text="...")
        claims = await service.list_claims(db, product_id=1, status=ClaimStatus.PENDING_REVIEW)
    """

    # ── Create ──────────────────────────────────────────────────────────

    async def create_claim(
        self,
        db: AsyncSession,
        *,
        product_id: int,
        claim_text: str,
        source_doc_id: int | None = None,
        status: ClaimStatus = ClaimStatus.PENDING_REVIEW,
    ) -> ProductClaim:
        """Create a new claim for a product.

        Validates that the product exists and is active.  If ``source_doc_id``
        is provided, also validates that the document exists and belongs to
        the same product.

        Args:
            db: Active database session.
            product_id: The parent product's primary key.
            claim_text: The marketing claim text.
            source_doc_id: Optional FK to a source document anchoring the claim.
            status: Claim verification status (defaults to pending_review).

        Returns:
            The newly created ``ProductClaim`` ORM instance.

        Raises:
            ValueError: If the product is not found, or the source document
                        does not belong to the product.
        """
        # Guard: product must exist and be active
        product = await db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.is_deleted == False,  # noqa: E712
            )
        )
        if product.scalar_one_or_none() is None:
            raise ValueError(f"Product with id={product_id!r} not found.")

        # Guard: source document must belong to same product (if provided)
        if source_doc_id is not None:
            doc = await db.execute(
                select(ProductDocument).where(
                    ProductDocument.id == source_doc_id,
                    ProductDocument.product_id == product_id,
                )
            )
            if doc.scalar_one_or_none() is None:
                raise ValueError(
                    f"Source document id={source_doc_id!r} not found "
                    f"or does not belong to product id={product_id!r}."
                )

        claim = ProductClaim(
            product_id=product_id,
            claim_text=claim_text,
            source_doc_id=source_doc_id,
            status=status,
        )
        db.add(claim)
        await db.flush()

        result = await db.execute(
            select(ProductClaim)
            .where(ProductClaim.id == claim.id)
            .options(selectinload(ProductClaim.source_doc))
        )
        claim = result.scalar_one()

        logger.info(
            "Created claim id=%d for product_id=%d status=%s",
            claim.id,
            product_id,
            status.value,
        )
        return claim

    # ── Read ────────────────────────────────────────────────────────────

    async def get_by_id(
        self, db: AsyncSession, claim_id: int
    ) -> ProductClaim | None:
        """Fetch a single claim by its primary key, eager-loading the source doc.

        Args:
            db: Active database session.
            claim_id: The claim's primary key.

        Returns:
            The matching ``ProductClaim`` with ``source_doc`` loaded, or ``None``.
        """
        result = await db.execute(
            select(ProductClaim)
            .where(ProductClaim.id == claim_id)
            .options(selectinload(ProductClaim.source_doc))
        )
        return result.scalar_one_or_none()

    async def list_claims(
        self,
        db: AsyncSession,
        product_id: int,
        *,
        status: ClaimStatus | None = None,
    ) -> list[ProductClaim]:
        """List claims for a product, optionally filtered by status.

        Results are eager-loaded with the source document reference and
        ordered by creation date (oldest first).

        Args:
            db: Active database session.
            product_id: The parent product's primary key.
            status: Optional status filter (e.g. ClaimStatus.PENDING_REVIEW).

        Returns:
            A (possibly empty) list of ``ProductClaim`` instances.
        """
        stmt = (
            select(ProductClaim)
            .where(ProductClaim.product_id == product_id)
            .options(selectinload(ProductClaim.source_doc))
            .order_by(ProductClaim.created_at)
        )
        if status is not None:
            stmt = stmt.where(ProductClaim.status == status)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── Update ──────────────────────────────────────────────────────────

    async def update_claim(
        self,
        db: AsyncSession,
        claim_id: int,
        *,
        claim_text: str | None = None,
        status: ClaimStatus | None = None,
    ) -> ProductClaim:
        """Partially update a claim's text and/or status.

        Only non-None fields are applied.  The claim is refreshed and
        returned with its source document eager-loaded.

        Args:
            db: Active database session.
            claim_id: The claim's primary key.
            claim_text: Updated claim text (optional).
            status: Updated verification status (optional).

        Returns:
            The refreshed ``ProductClaim`` with ``source_doc`` loaded.

        Raises:
            ValueError: If the claim is not found.
        """
        claim = await self._require_claim(db, claim_id)

        if claim_text is not None:
            claim.claim_text = claim_text
        if status is not None:
            claim.status = status

        await db.flush()

        # Re-fetch with eager-loaded source_doc for a clean response
        refreshed = await self.get_by_id(db, claim_id)
        if refreshed is None:
            raise ValueError(f"Claim with id={claim_id!r} not found after update.")

        logger.info("Updated claim id=%d", claim_id)
        return refreshed

    # ── Delete ──────────────────────────────────────────────────────────

    async def delete_claim(
        self, db: AsyncSession, claim_id: int
    ) -> ProductClaim:
        """Permanently delete a claim from the database.

        Args:
            db: Active database session.
            claim_id: The claim's primary key.

        Returns:
            The deleted ``ProductClaim`` instance (detached).

        Raises:
            ValueError: If the claim is not found.
        """
        claim = await self._require_claim(db, claim_id)
        await db.delete(claim)
        await db.flush()

        logger.info("Deleted claim id=%d", claim_id)
        return claim

    # ── Helpers ─────────────────────────────────────────────────────────

    async def _require_claim(
        self, db: AsyncSession, claim_id: int
    ) -> ProductClaim:
        """Fetch a claim by ID or raise ValueError if not found."""
        result = await db.execute(
            select(ProductClaim).where(ProductClaim.id == claim_id)
        )
        claim = result.scalar_one_or_none()
        if claim is None:
            raise ValueError(f"Claim with id={claim_id!r} not found.")
        return claim
