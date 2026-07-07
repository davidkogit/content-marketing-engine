"""
RAG context collector — assembles everything the LLM needs to generate
marketing copy for a product: product specs, source documents, brand rules,
and the target segment's tone & audience profile.

All database access is async and accepts a session via dependency injection.
Missing / incomplete data is handled gracefully so the pipeline never throws.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.llm.brand_rules import BrandRules, BrandRulesLoader
from app.models.product import Product
from app.models.product_document import ProductDocument
from app.models.segment import Segment

logger = logging.getLogger(__name__)

# ── GenerationContext ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GenerationContext:
    """All information the prompt builder needs to construct LLM prompts.

    Every field is populated with sensible empty defaults so downstream
    code never has to guard against ``None``.
    """

    product_specs: dict[str, str | None] = field(default_factory=dict)
    source_documents: list[dict[str, str | None]] = field(default_factory=list)
    brand_rules: BrandRules = field(default_factory=BrandRulesLoader.load_rules)
    segment_profile: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        """Return a JSON-safe dict representation (useful for logging)."""
        return {
            "product_specs": self.product_specs,
            "source_documents": self.source_documents,
            "brand_rules": self.brand_rules.as_dict(),
            "segment_profile": self.segment_profile,
        }


# ── Helper builders ─────────────────────────────────────────────────────────


def _build_product_specs(product: Product) -> dict[str, str | None]:
    """Extract product metadata into a flat dict."""
    return {
        "name": product.name,
        "sku": product.sku,
        "description": product.description or "",
        "category": product.category.name if product.category else None,
        "segment": product.segment.name if product.segment else None,
    }


def _build_source_documents(
    documents: list[ProductDocument],
) -> list[dict[str, str | None]]:
    """Convert a list of ORM document rows to a list of plain dicts."""
    return [
        {
            "title": doc.title,
            "extracted_text": doc.extracted_text or "",
        }
        for doc in documents
    ]


def _build_segment_profile(segment: Segment | None) -> dict[str, str]:
    """Extract tone and audience from a Segment ORM row.

    Returns empty strings for both fields when *segment* is ``None``.
    """
    if segment is None:
        return {"tone": "", "audience": ""}
    return {
        "tone": segment.tone or "",
        "audience": segment.target_audience or "",
    }


# ── ContextCollector ────────────────────────────────────────────────────────


class ContextCollector:
    """Collects all RAG context for a product — specs, documents, segment,
    and brand rules — into a single ``GenerationContext``.

    Usage::

        collector = ContextCollector(rules_dir="/app/data/rules")
        ctx = await collector.collect(db_session, product_id=42)
    """

    def __init__(self, rules_dir: str | None = None) -> None:
        """Initialise the collector with an optional rules directory.

        Args:
            rules_dir: Path to the brand rules directory.  Passed
                       through to ``BrandRulesLoader``.  When *None*
                       the loader uses its own default.
        """
        self._rules_dir = rules_dir

    async def collect(
        self,
        db: AsyncSession,
        product_id: int,
    ) -> GenerationContext:
        """Assemble the full generation context for *product_id*.

        Args:
            db: An active async database session.
            product_id: The product's primary key.

        Returns:
            A fully-populated ``GenerationContext`` (missing data is
            represented as empty strings / lists, never ``None``).
        """
        # 1. Fetch product with eager-loaded relationships
        product = await self._fetch_product(db, product_id)

        if product is None:
            logger.warning(
                "Product id=%d not found — returning empty context", product_id
            )
            return GenerationContext()

        # 2. Build each context component
        product_specs = _build_product_specs(product)
        source_docs = _build_source_documents(product.documents or [])
        segment_profile = _build_segment_profile(product.segment)
        brand_rules = BrandRulesLoader.load_rules(self._rules_dir)

        ctx = GenerationContext(
            product_specs=product_specs,
            source_documents=source_docs,
            brand_rules=brand_rules,
            segment_profile=segment_profile,
        )

        logger.info(
            "Assembled context for product id=%d: %d docs, segment=%s",
            product_id,
            len(source_docs),
            segment_profile.get("tone") or "(none)",
        )
        return ctx

    # ── Internal helpers ─────────────────────────────────────────────────

    @staticmethod
    async def _fetch_product(
        db: AsyncSession, product_id: int
    ) -> Product | None:
        """Fetch a product eagerly loading category, segment, and documents."""
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.category),
                selectinload(Product.segment),
                selectinload(Product.documents),
            )
        )
        result = await db.execute(stmt)
        return result.unique().scalar_one_or_none()
