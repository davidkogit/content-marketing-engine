"""
Pydantic request/response schemas for the CSV export module.

Defines the mapping configuration model, preview response, history
response, and the internal structures that drive field selection and
claim formatting during CSV generation.
"""


import enum
from datetime import datetime

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────


class ClaimMode(str, enum.Enum):
    """How claims appear in the exported CSV output."""

    INLINE = "inline"
    """Claims concatenated into a single cell, separated by ' | '."""
    EXPANDED = "expanded"
    """Each claim becomes its own row, with product fields repeated."""


# ── Mapping Configuration ────────────────────────────────────────────────────


class ExportFieldMapping(BaseModel):
    """Definition of a single column in the export mapping.

    Each mapping corresponds to one source field from the product/claim
    domain model, optionally renamed for the CSV header.
    """

    source: str = Field(
        ...,
        description="Internal field name (e.g. 'sku', 'name', 'claims').",
    )
    label: str = Field(
        ...,
        description="Column header label in the generated CSV.",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this field is included in the export.",
    )


class ExportMappingConfig(BaseModel):
    """Complete mapping configuration controlling CSV export structure.

    Saved via ``POST /api/export/config`` and used by the CSVExporter
    to determine which fields to emit and how claims should appear.
    """

    fields: list[ExportFieldMapping] = Field(
        ...,
        description="Ordered list of field mappings defining CSV columns.",
    )
    claim_mode: ClaimMode = Field(
        default=ClaimMode.INLINE,
        description="Whether claims appear concatenated in one cell or as separate rows.",
    )


# ── Response Schemas ─────────────────────────────────────────────────────────


class ExportPreviewCell(BaseModel):
    """A single cell value in the export preview grid."""

    column: str
    value: str | None


class ExportPreviewRow(BaseModel):
    """A single row in the export preview grid."""

    row_index: int
    cells: list[ExportPreviewCell]


class ExportPreviewResponse(BaseModel):
    """Response for ``GET /api/export/products/{id}/preview``.

    Shows exactly what data would appear in the CSV before generation,
    formatted as rows and columns for easy frontend rendering.
    """

    product_id: int
    product_name: str
    claim_mode: str
    total_rows: int
    rows: list[ExportPreviewRow]


class ExportHistoryItem(BaseModel):
    """A single entry in the export history log."""

    id: int
    product_id: int
    product_name: str | None = None
    exported_by: int
    exported_by_email: str | None = None
    mapping_config: ExportMappingConfig | None = None
    exported_at: datetime

    model_config = {"from_attributes": True}


class ExportHistoryResponse(BaseModel):
    """Paginated list of export history entries."""

    items: list[ExportHistoryItem]
    total: int
    page: int
    page_size: int
    total_pages: int
