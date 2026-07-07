"""Unit tests for the CSVExporter class — CSV generation and data preview.

Uses plain dataclass-based stubs to exercise field extraction, claim
formatting (inline vs expanded), and header generation without requiring
a database or ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.export.csv_exporter import CSVExporter
from app.export.export_schemas import (
    ClaimMode,
    ExportFieldMapping,
    ExportMappingConfig,
)


# ── Stubs ────────────────────────────────────────────────────────────────────


@dataclass
class StubCategory:
    id: int
    name: str


@dataclass
class StubSegment:
    id: int
    name: str


@dataclass
class StubClaim:
    id: int
    claim_text: str


@dataclass
class StubWorkflowStage:
    value: str


@dataclass
class StubProduct:
    id: int = 1
    sku: str = "SKU-001"
    name: str = "Test Widget"
    description: str | None = "A wonderful widget."
    category: StubCategory | None = None
    segment: StubSegment | None = None
    workflow_stage: StubWorkflowStage = field(
        default_factory=lambda: StubWorkflowStage("ingest")
    )
    claims: list[StubClaim] = field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_config(
    fields: list[tuple[str, str, bool]] | None = None,
    claim_mode: ClaimMode = ClaimMode.INLINE,
) -> ExportMappingConfig:
    """Quickly build an ExportMappingConfig from a list of (source, label, enabled)."""
    if fields is None:
        fields = [
            ("sku", "SKU", True),
            ("name", "Product Name", True),
            ("claims", "Claims", True),
        ]
    return ExportMappingConfig(
        fields=[
            ExportFieldMapping(source=s, label=l, enabled=e)
            for s, l, e in fields
        ],
        claim_mode=claim_mode,
    )


def _make_product(**overrides) -> StubProduct:
    """Create a StubProduct with optional attribute overrides."""
    kwargs: dict = {
        "id": 1,
        "sku": "SKU-001",
        "name": "Test Widget",
        "description": "A wonderful widget.",
        "category": StubCategory(id=1, name="Electronics"),
        "segment": StubSegment(id=1, name="Enterprise"),
        "claims": [
            StubClaim(id=1, claim_text="Best in class"),
            StubClaim(id=2, claim_text="99% uptime guarantee"),
        ],
    }
    kwargs.update(overrides)
    return StubProduct(**kwargs)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestGenerateCSV:
    """Tests for CSVExporter.generate_csv()"""

    def test_basic_csv_generation(self):
        """Generate CSV with default fields and inline claims."""
        exporter = CSVExporter()
        product = _make_product()
        config = _make_config()

        csv_output = exporter.generate_csv(product, config)

        lines = csv_output.strip().split("\r\n")
        assert len(lines) == 2  # header + 1 data row
        assert lines[0] == "SKU,Product Name,Claims"
        # Claims are inline with separator
        assert "Best in class | 99% uptime guarantee" in lines[1]

    def test_csv_with_only_product_fields(self):
        """Generate CSV without claims field enabled."""
        exporter = CSVExporter()
        product = _make_product()
        config = _make_config(
            fields=[
                ("sku", "SKU", True),
                ("name", "Name", True),
                ("description", "Desc", True),
            ]
        )

        csv_output = exporter.generate_csv(product, config)
        lines = csv_output.strip().split("\r\n")
        assert len(lines) == 2
        assert lines[0] == "SKU,Name,Desc"
        assert lines[1] == "SKU-001,Test Widget,A wonderful widget."

    def test_csv_with_disabled_fields(self):
        """Disabled fields should not appear in headers or data."""
        exporter = CSVExporter()
        product = _make_product()
        config = _make_config(
            fields=[
                ("sku", "SKU", True),
                ("name", "Name", False),
                ("claims", "Claims", True),
            ]
        )

        csv_output = exporter.generate_csv(product, config)
        lines = csv_output.strip().split("\r\n")
        assert lines[0] == "SKU,Claims"
        assert "SKU-001" in lines[1]
        assert "Test Widget" not in lines[1]  # name was disabled

    def test_csv_with_category_and_segment(self):
        """Category and segment extractors produce the related name."""
        exporter = CSVExporter()
        product = _make_product()
        config = _make_config(
            fields=[
                ("sku", "SKU", True),
                ("category", "Category", True),
                ("segment", "Segment", True),
            ]
        )

        csv_output = exporter.generate_csv(product, config)
        lines = csv_output.strip().split("\r\n")
        assert lines[0] == "SKU,Category,Segment"
        assert lines[1] == "SKU-001,Electronics,Enterprise"

    def test_csv_category_none_produces_empty(self):
        """When product has no category, the cell is empty."""
        exporter = CSVExporter()
        product = _make_product(category=None)
        config = _make_config(
            fields=[("category", "Category", True)]
        )

        csv_output = exporter.generate_csv(product, config)
        lines = csv_output.strip().split("\r\n")
        assert lines[1] == ""  # empty cell

    def test_csv_workflow_stage(self):
        """Workflow stage is rendered as its string value."""
        exporter = CSVExporter()
        product = _make_product(workflow_stage=StubWorkflowStage("approved"))
        config = _make_config(
            fields=[("workflow_stage", "Stage", True)]
        )

        csv_output = exporter.generate_csv(product, config)
        lines = csv_output.strip().split("\r\n")
        assert lines[1] == "approved"

    def test_csv_with_no_claims(self):
        """Product without claims produces empty claims cell."""
        exporter = CSVExporter()
        product = _make_product(claims=[])
        config = _make_config()

        csv_output = exporter.generate_csv(product, config)
        lines = csv_output.strip().split("\r\n")
        assert lines[1].endswith("SKU-001,Test Widget,")  # empty claims cell

    def test_expanded_mode_creates_one_row_per_claim(self):
        """In expanded mode, each claim becomes its own row."""
        exporter = CSVExporter()
        product = _make_product()
        config = _make_config(claim_mode=ClaimMode.EXPANDED)

        csv_output = exporter.generate_csv(product, config)
        lines = csv_output.strip().split("\r\n")
        # header + 2 claim rows
        assert len(lines) == 3
        assert "Best in class" in lines[1]
        assert "99% uptime guarantee" in lines[2]
        # Product fields are repeated
        assert lines[1].startswith("SKU-001,Test Widget,")
        assert lines[2].startswith("SKU-001,Test Widget,")

    def test_expanded_mode_with_no_claims_single_row(self):
        """Expanded mode with no claims still produces one row (empty claims)."""
        exporter = CSVExporter()
        product = _make_product(claims=[])
        config = _make_config(claim_mode=ClaimMode.EXPANDED)

        csv_output = exporter.generate_csv(product, config)
        lines = csv_output.strip().split("\r\n")
        assert len(lines) == 2  # header + 1 row with empty claims

    def test_empty_product_no_enabled_fields(self):
        """Edge case: all fields disabled produces only header."""
        exporter = CSVExporter()
        product = _make_product()
        config = _make_config(
            fields=[
                ("sku", "SKU", False),
                ("name", "Name", False),
            ]
        )

        csv_output = exporter.generate_csv(product, config)
        lines = csv_output.strip().split("\r\n")
        assert len(lines) == 2
        assert lines[0] == ""
        assert lines[1] == ""

    def test_unknown_source_field_produces_empty(self):
        """A source field with no registered extractor yields empty string."""
        exporter = CSVExporter()
        product = _make_product()
        config = ExportMappingConfig(
            fields=[
                ExportFieldMapping(source="nonexistent", label="Ghost", enabled=True),
            ]
        )

        csv_output = exporter.generate_csv(product, config)
        lines = csv_output.strip().split("\r\n")
        assert lines[0] == "Ghost"
        assert lines[1] == ""


class TestPreviewData:
    """Tests for CSVExporter.preview_data()"""

    def test_preview_returns_structured_rows(self):
        """Preview returns labelled cells in a structured format."""
        exporter = CSVExporter()
        product = _make_product()
        config = _make_config()

        preview = exporter.preview_data(product, config)

        assert len(preview) == 1
        row = preview[0]
        assert row.row_index == 0
        assert len(row.cells) == 3
        assert row.cells[0].column == "SKU"
        assert row.cells[0].value == "SKU-001"
        assert row.cells[1].column == "Product Name"
        assert row.cells[1].value == "Test Widget"
        assert row.cells[2].column == "Claims"
        assert "Best in class" in (row.cells[2].value or "")

    def test_preview_expanded_mode(self):
        """Expanded preview has one row per claim."""
        exporter = CSVExporter()
        product = _make_product()
        config = _make_config(claim_mode=ClaimMode.EXPANDED)

        preview = exporter.preview_data(product, config)

        assert len(preview) == 2
        assert preview[0].row_index == 0
        assert preview[1].row_index == 1

    def test_preview_no_claims(self):
        """Preview with no claims still returns a row."""
        exporter = CSVExporter()
        product = _make_product(claims=[])
        config = _make_config()

        preview = exporter.preview_data(product, config)

        assert len(preview) == 1
        claim_cell = [c for c in preview[0].cells if c.column == "Claims"][0]
        assert claim_cell.value == ""
