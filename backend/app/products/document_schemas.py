"""
Pydantic request/response schemas for product document endpoints.

Defines DocumentCreate (for linking a URL to a product) and
DocumentResponse (returned to API consumers).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.product_document import DocType


# ── Request Schemas ─────────────────────────────────────────────────────────


class DocumentCreate(BaseModel):
    """Request body for linking a document (URL) to a product.

    The document title is auto-fetched from the URL by the service layer.
    The doc_type is automatically detected from the URL extension (.pdf → pdf).
    """

    url: str = Field(
        ...,
        min_length=1,
        description="URL of the source document (PDF or web page).",
    )
    doc_type: DocType = Field(
        ...,
        description="Document type: 'pdf' for PDF files, 'url' for web pages.",
    )


# ── Response Schemas ────────────────────────────────────────────────────────


class DocumentResponse(BaseModel):
    """Response model for a linked product document."""

    id: int
    product_id: int
    title: str
    url: str
    doc_type: str
    extracted_text: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
