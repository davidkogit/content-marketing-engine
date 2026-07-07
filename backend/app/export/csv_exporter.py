"""
CSVExporter — generates CSV output from product data using a configurable
field mapping.

Supports two claim modes:
- ``inline``:  all claims concatenated into a single cell.
- ``expanded``:  each claim produces its own row, with product fields repeated.

The exporter is a plain class with no side-effects or I/O beyond what
the caller provides.  It accepts a Product ORM instance (with any
eager-loaded relationships) and an ExportMappingConfig, and returns
either a CSV string or a list of dicts suitable for JSON preview.
"""


import csv
import io
import logging
from functools import partial
from typing import Any, Callable

from app.export.export_schemas import (
    ClaimMode,
    ExportMappingConfig,
    ExportPreviewCell,
    ExportPreviewRow,
)

logger = logging.getLogger(__name__)

# ── Field value extractors ───────────────────────────────────────────────────

# Each extractor is a callable ``(product) -> str`` responsible for
# resolving a single source field name to a string value.  Extensions
# (future fields) can be added here without touching the core exporter.

ExtractorFn = Callable[[Any], str | None]


def _extract_sku(product: Any) -> str:
    return product.sku


def _extract_name(product: Any) -> str:
    return product.name


def _extract_description(product: Any) -> str | None:
    return product.description


def _extract_category(product: Any) -> str | None:
    return product.category.name if product.category else None


def _extract_segment(product: Any) -> str | None:
    return product.segment.name if product.segment else None


def _extract_workflow_stage(product: Any) -> str:
    return product.workflow_stage.value if hasattr(product.workflow_stage, "value") else str(product.workflow_stage)


_EXTRACTORS: dict[str, ExtractorFn] = {
    "sku": _extract_sku,
    "name": _extract_name,
    "description": _extract_description,
    "category": _extract_category,
    "segment": _extract_segment,
    "workflow_stage": _extract_workflow_stage,
}
"""Lookup of extractor functions keyed by source field name."""


def _resolve_value(product: Any, source: str) -> str | None:
    """Resolve a source field to its string value for the given product.

    If no extractor is registered for *source*, returns ``None``
    (the column will be empty but still present in the output).
    """
    extractor = _EXTRACTORS.get(source)
    if extractor is None:
        logger.debug("No extractor registered for source field %r", source)
        return None
    return extractor(product)


# ── Claim formatting ─────────────────────────────────────────────────────────


def _claims_inline(product: Any, *, separator: str = " | ") -> str:
    """Concatenate all verified claim texts into a single string."""
    parts = [
        c.claim_text
        for c in getattr(product, "claims", [])
        if hasattr(c, "claim_text") and c.claim_text
    ]
    return separator.join(parts)

# ── CSVExporter ──────────────────────────────────────────────────────────────


class CSVExporter:
    """Generates CSV from product data using a configurable field mapping.

    All methods are pure — they accept input data and return output
    without side effects.  The caller is responsible for providing
    the product ORM instance (with relationships loaded) and the
    mapping configuration.
    """

    def generate_csv(self, product: Any, mapping: ExportMappingConfig) -> str:
        """Produce a CSV string from *product* using *mapping*.

        Args:
            product: A Product ORM instance, ideally with ``claims`` eager-loaded.
            mapping: The field mapping configuration.

        Returns:
            A CSV string (with header row) ready for download.
        """
        rows = self._build_rows(product, mapping)
        if not rows:
            return ""

        buf = io.StringIO()
        writer = csv.writer(buf)

        # Header row — only enabled fields (plus per-claim text for expanded mode)
        headers = self._build_headers(mapping)
        writer.writerow(headers)

        for row in rows:
            writer.writerow(row)

        return buf.getvalue()

    def preview_data(
        self, product: Any, mapping: ExportMappingConfig
    ) -> list[ExportPreviewRow]:
        """Return a structured preview suitable for JSON serialisation.

        The preview mirrors exactly what ``generate_csv`` would produce,
        but as an in-memory list of rows with labelled cells.

        Args:
            product: A Product ORM instance with claims eager-loaded.
            mapping: The field mapping configuration.

        Returns:
            A list of ``ExportPreviewRow`` objects representing the grid.
        """
        headers = self._build_headers(mapping)
        rows = self._build_rows(product, mapping)

        preview_rows: list[ExportPreviewRow] = []
        for idx, row in enumerate(rows):
            cells = [
                ExportPreviewCell(
                    column=headers[col_idx] if col_idx < len(headers) else f"col_{col_idx}",
                    value=cell,
                )
                for col_idx, cell in enumerate(row)
            ]
            preview_rows.append(ExportPreviewRow(row_index=idx, cells=cells))

        return preview_rows

    # ── Internal helpers ─────────────────────────────────────────────────

    def _build_headers(self, mapping: ExportMappingConfig) -> list[str]:
        """Build the CSV header row based on the mapping config."""
        enabled = [f for f in mapping.fields if f.enabled]
        headers: list[str] = []
        for field in enabled:
            headers.append(field.label)
        if mapping.claim_mode == ClaimMode.EXPANDED and any(
            f.source == "claims" and f.enabled for f in enabled
        ):
            # When expanded, we add a "Claim #" column to indicate which claim
            # within the product is represented by the row.
            # Insert it just before the claim text column.
            pass  # claim text label is already in headers
        return headers

    def _build_rows(
        self, product: Any, mapping: ExportMappingConfig
    ) -> list[list[str]]:
        """Build CSV data rows from a product and mapping config.

        When *claim_mode* is ``expanded`` and the ``claims`` field is
        enabled, each claim becomes a separate row.  Otherwise, claims
        are concatenated into a single cell and a single row is produced.
        """
        enabled = [f for f in mapping.fields if f.enabled]
        has_claims_field = any(f.source == "claims" for f in enabled)
        claims = getattr(product, "claims", []) or []

        if mapping.claim_mode == ClaimMode.EXPANDED and has_claims_field and claims:
            return self._build_expanded_rows(product, enabled, claims)
        else:
            return [self._build_single_row(product, enabled)]

    def _build_single_row(
        self, product: Any, enabled_fields: list
    ) -> list[str]:
        """Build a single row (inline mode or no claims)."""
        row: list[str] = []
        for field in enabled_fields:
            if field.source == "claims":
                # inline mode: concatenate claims
                row.append(_claims_inline(product))
            else:
                val = _resolve_value(product, field.source)
                row.append(val if val is not None else "")
        return row

    def _build_expanded_rows(
        self, product: Any, enabled_fields: list, claims: list
    ) -> list[list[str]]:
        """Build one row per claim, repeating product fields.

        For fields that are NOT the ``claims`` source, the same value is
        repeated across every row.  The ``claims`` field produces one
        row per claim.
        """
        rows: list[list[str]] = []
        for claim in claims:
            row: list[str] = []
            for field in enabled_fields:
                if field.source == "claims":
                    row.append(claim.claim_text if hasattr(claim, "claim_text") else "")
                else:
                    val = _resolve_value(product, field.source)
                    row.append(val if val is not None else "")
            rows.append(row)
        return rows
