"""
Unit tests for ContextCollector and GenerationContext — verifies correct
assembly of product specs, source documents, brand rules, and segment
profile from ORM data, including graceful handling of missing data.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.brand_rules import BrandRules, BrandRulesLoader
from app.llm.context_collector import (
    ContextCollector,
    GenerationContext,
    _build_product_specs,
    _build_segment_profile,
    _build_source_documents,
)
from app.models.category import Category
from app.models.product import Product, WorkflowStage
from app.models.product_document import DocType, ProductDocument
from app.models.segment import Segment


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db() -> AsyncMock:
    """Return a mock AsyncSession for database operations."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def sample_category() -> Category:
    """A sample Category ORM instance."""
    return Category(id=1, name="Electronics", description="Consumer electronics")


@pytest.fixture
def sample_segment() -> Segment:
    """A sample Segment ORM instance with tone and audience."""
    return Segment(
        id=10,
        name="Tech Enthusiasts",
        description="Early adopters of technology",
        target_audience="Tech-savvy professionals aged 25-45",
        tone="Enthusiastic but credible",
    )


@pytest.fixture
def sample_segment_minimal() -> Segment:
    """A Segment with no tone or audience set (simulates minimal config)."""
    return Segment(
        id=11,
        name="General",
        description="General audience",
        target_audience=None,
        tone=None,
    )


@pytest.fixture
def sample_documents() -> list[ProductDocument]:
    """Two sample ProductDocument ORM instances with extracted text."""
    return [
        ProductDocument(
            id=100,
            product_id=1,
            title="Technical Specification Sheet",
            url="https://example.com/specs.pdf",
            extracted_text="The XYZ-9000 features a 5nm processor and 16GB RAM.",
            doc_type=DocType.PDF,
        ),
        ProductDocument(
            id=101,
            product_id=1,
            title="Marketing Brief",
            url="https://example.com/brief.pdf",
            extracted_text="Target audience values speed and battery life.",
            doc_type=DocType.PDF,
        ),
    ]


@pytest.fixture
def sample_document_empty_text() -> ProductDocument:
    """A ProductDocument with no extracted text yet."""
    return ProductDocument(
        id=102,
        product_id=1,
        title="Unprocessed Document",
        url="https://example.com/unprocessed.pdf",
        extracted_text=None,
        doc_type=DocType.PDF,
    )


@pytest.fixture
def sample_product(
    sample_category: Category,
    sample_segment: Segment,
    sample_documents: list[ProductDocument],
) -> Product:
    """A fully-populated Product with category, segment, and documents."""
    product = Product(
        id=1,
        sku="XYZ-9000",
        name="SuperWidget XYZ-9000",
        description="A high-performance widget for professional use.",
        category_id=1,
        segment_id=10,
        workflow_stage=WorkflowStage.DRAFT,
    )
    # Manually wire relationships (these would normally be set by SQLAlchemy)
    product.category = sample_category
    product.segment = sample_segment
    product.documents = sample_documents
    return product


@pytest.fixture
def sample_product_minimal() -> Product:
    """A Product with no category, segment, or documents (minimal data)."""
    product = Product(
        id=2,
        sku="BASIC-100",
        name="Basic Widget 100",
        description=None,
        category_id=None,
        segment_id=None,
        workflow_stage=WorkflowStage.INGEST,
    )
    product.category = None
    product.segment = None
    product.documents = []
    return product


@pytest.fixture
def context_collector() -> ContextCollector:
    """Return a ContextCollector with default (test) rules path."""
    return ContextCollector()


# ── GenerationContext ──────────────────────────────────────────────────────


class TestGenerationContext:
    """Tests for the GenerationContext dataclass."""

    def test_default_context_is_empty(self) -> None:
        """A default-constructed context should have empty/neutral fields."""
        ctx = GenerationContext()
        assert ctx.product_specs == {}
        assert ctx.source_documents == []
        assert isinstance(ctx.brand_rules, BrandRules)
        assert ctx.segment_profile == {}

    def test_full_context_roundtrip(self) -> None:
        """All fields should be settable via constructor."""
        rules = BrandRules(tone="Be friendly", compliance="Be honest", style="Be concise")
        ctx = GenerationContext(
            product_specs={"name": "Widget", "sku": "W-001"},
            source_documents=[{"title": "Doc 1", "extracted_text": "Some text"}],
            brand_rules=rules,
            segment_profile={"tone": "casual", "audience": "developers"},
        )
        assert ctx.product_specs["name"] == "Widget"
        assert len(ctx.source_documents) == 1
        assert ctx.brand_rules.tone == "Be friendly"
        assert ctx.segment_profile["tone"] == "casual"

    def test_as_dict_returns_serialisable(self) -> None:
        """as_dict() should produce a JSON-safe dict."""
        rules = BrandRules(tone="X", compliance="Y", style="Z")
        ctx = GenerationContext(
            product_specs={"name": "P"},
            source_documents=[{"title": "D", "extracted_text": "T"}],
            brand_rules=rules,
            segment_profile={"tone": "t", "audience": "a"},
        )
        d = ctx.as_dict()
        assert d["product_specs"]["name"] == "P"
        assert d["source_documents"][0]["title"] == "D"
        assert d["brand_rules"]["tone"] == "X"
        assert d["segment_profile"]["tone"] == "t"


# ── _build_product_specs ───────────────────────────────────────────────────


class TestBuildProductSpecs:
    """Tests for the _build_product_specs helper."""

    def test_full_product(self, sample_product: Product) -> None:
        """Should extract all fields from a fully-populated product."""
        specs = _build_product_specs(sample_product)
        assert specs["name"] == "SuperWidget XYZ-9000"
        assert specs["sku"] == "XYZ-9000"
        assert specs["description"] == "A high-performance widget for professional use."
        assert specs["category"] == "Electronics"
        assert specs["segment"] == "Tech Enthusiasts"

    def test_minimal_product(self, sample_product_minimal: Product) -> None:
        """Missing category/segment should produce None values."""
        specs = _build_product_specs(sample_product_minimal)
        assert specs["name"] == "Basic Widget 100"
        assert specs["description"] == ""
        assert specs["category"] is None
        assert specs["segment"] is None


# ── _build_source_documents ────────────────────────────────────────────────


class TestBuildSourceDocuments:
    """Tests for the _build_source_documents helper."""

    def test_extracts_title_and_text(self, sample_documents: list[ProductDocument]) -> None:
        """Each document's title and extracted_text should be included."""
        docs = _build_source_documents(sample_documents)
        assert len(docs) == 2
        assert docs[0]["title"] == "Technical Specification Sheet"
        assert "XYZ-9000" in docs[0]["extracted_text"]  # type: ignore[operator]
        assert docs[1]["title"] == "Marketing Brief"

    def test_empty_text_becomes_empty_string(
        self, sample_document_empty_text: ProductDocument,
    ) -> None:
        """None extracted_text should become empty string."""
        docs = _build_source_documents([sample_document_empty_text])
        assert docs[0]["extracted_text"] == ""

    def test_empty_list(self) -> None:
        """An empty document list should produce an empty list."""
        docs = _build_source_documents([])
        assert docs == []


# ── _build_segment_profile ─────────────────────────────────────────────────


class TestBuildSegmentProfile:
    """Tests for the _build_segment_profile helper."""

    def test_full_segment(self, sample_segment: Segment) -> None:
        """A fully-populated segment should extract tone and audience."""
        profile = _build_segment_profile(sample_segment)
        assert profile["tone"] == "Enthusiastic but credible"
        assert profile["audience"] == "Tech-savvy professionals aged 25-45"

    def test_minimal_segment(self, sample_segment_minimal: Segment) -> None:
        """A segment with no tone/audience should produce empty strings."""
        profile = _build_segment_profile(sample_segment_minimal)
        assert profile["tone"] == ""
        assert profile["audience"] == ""

    def test_none_segment(self) -> None:
        """None segment should produce empty strings."""
        profile = _build_segment_profile(None)
        assert profile == {"tone": "", "audience": ""}


# ── ContextCollector.collect ───────────────────────────────────────────────


class TestContextCollectorCollect:
    """Integration-style tests for ContextCollector.collect()."""

    async def test_collect_full_product(
        self,
        context_collector: ContextCollector,
        mock_db: AsyncMock,
        sample_product: Product,
    ) -> None:
        """Should assemble a full GenerationContext from a complete product."""
        mock_db.execute.return_value.unique.return_value.scalar_one_or_none.return_value = (
            sample_product
        )

        ctx = await context_collector.collect(mock_db, product_id=1)

        # Product specs
        assert ctx.product_specs["name"] == "SuperWidget XYZ-9000"
        assert ctx.product_specs["category"] == "Electronics"

        # Source documents
        assert len(ctx.source_documents) == 2
        assert ctx.source_documents[0]["title"] == "Technical Specification Sheet"

        # Segment profile
        assert ctx.segment_profile["tone"] == "Enthusiastic but credible"
        assert "Tech-savvy" in ctx.segment_profile["audience"]

        # Brand rules (should be loaded — either from files or defaults)
        assert isinstance(ctx.brand_rules, BrandRules)
        assert len(ctx.brand_rules.tone) > 0
        assert len(ctx.brand_rules.compliance) > 0
        assert len(ctx.brand_rules.style) > 0

    async def test_collect_minimal_product(
        self,
        context_collector: ContextCollector,
        mock_db: AsyncMock,
        sample_product_minimal: Product,
    ) -> None:
        """Should handle a product with no category, segment, or documents."""
        mock_db.execute.return_value.unique.return_value.scalar_one_or_none.return_value = (
            sample_product_minimal
        )

        ctx = await context_collector.collect(mock_db, product_id=2)

        assert ctx.product_specs["name"] == "Basic Widget 100"
        assert ctx.product_specs["category"] is None
        assert ctx.source_documents == []
        assert ctx.segment_profile == {"tone": "", "audience": ""}

    async def test_collect_product_not_found(
        self,
        context_collector: ContextCollector,
        mock_db: AsyncMock,
    ) -> None:
        """When the product doesn't exist, should return an empty context."""
        mock_db.execute.return_value.unique.return_value.scalar_one_or_none.return_value = (
            None
        )

        ctx = await context_collector.collect(mock_db, product_id=999)

        assert ctx.product_specs == {}
        assert ctx.source_documents == []
        assert ctx.segment_profile == {}
        assert isinstance(ctx.brand_rules, BrandRules)  # rules still loaded

    async def test_collect_with_custom_rules_dir(
        self, mock_db: AsyncMock, sample_product: Product, tmp_path: str
    ) -> None:
        """A custom rules directory should be respected by the loader."""
        mock_db.execute.return_value.unique.return_value.scalar_one_or_none.return_value = (
            sample_product
        )

        collector = ContextCollector(rules_dir=str(tmp_path))
        ctx = await collector.collect(mock_db, product_id=1)

        # With an empty tmp_path no rule files exist, so defaults are used.
        assert isinstance(ctx.brand_rules, BrandRules)
        assert len(ctx.brand_rules.tone) > 0


# ── ContextCollector initialisation ────────────────────────────────────────


class TestContextCollectorInit:
    """Tests for ContextCollector constructor."""

    def test_default_rules_dir_is_none(self) -> None:
        """Default collector stores None so the loader uses its own default."""
        collector = ContextCollector()
        assert collector._rules_dir is None

    def test_custom_rules_dir(self, tmp_path: str) -> None:
        """A custom rules dir is stored for later use."""
        collector = ContextCollector(rules_dir=str(tmp_path))
        assert collector._rules_dir == str(tmp_path)
