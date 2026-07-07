"""
Pydantic request/response schemas for product claim endpoints.

Defines ClaimCreate, ClaimUpdate, and ClaimResponse (with optional
nested document reference).
"""


from datetime import datetime

from pydantic import BaseModel, Field

from app.models.product_claim import ClaimStatus


# ── Nested Response Schemas ─────────────────────────────────────────────────


class ClaimDocumentResponse(BaseModel):
    """Minimal document reference nested inside claim responses."""

    id: int
    title: str
    url: str

    model_config = {"from_attributes": True}


# ── Request Schemas ─────────────────────────────────────────────────────────


class ClaimCreate(BaseModel):
    """Request body for creating a new product claim.

    The ``source_doc_id`` is optional; if provided, the referenced document
    must belong to the same product.  The claim ``status`` defaults to
    ``pending_review`` when not explicitly set.
    """

    claim_text: str = Field(
        ...,
        min_length=1,
        description="The marketing claim text.",
    )
    source_doc_id: int | None = Field(
        None,
        description="Optional ID of the source document anchoring this claim.",
    )
    status: ClaimStatus = Field(
        default=ClaimStatus.PENDING_REVIEW,
        description="Claim verification status.",
    )


class ClaimUpdate(BaseModel):
    """Request body for updating an existing claim.

    All fields are optional — only supplied fields are changed.
    """

    claim_text: str | None = Field(
        None,
        min_length=1,
        description="Updated claim text.",
    )
    status: ClaimStatus | None = Field(
        None,
        description="Updated claim verification status.",
    )


# ── Response Schemas ────────────────────────────────────────────────────────


class ClaimResponse(BaseModel):
    """Response model for a product claim, with optional nested document."""

    id: int
    product_id: int
    claim_text: str
    source_doc_id: int | None = None
    status: str
    assigned_to: int | None = None
    created_at: datetime
    source_doc: ClaimDocumentResponse | None = None

    model_config = {"from_attributes": True}
