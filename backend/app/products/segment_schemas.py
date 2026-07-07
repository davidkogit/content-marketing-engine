"""
Pydantic request/response schemas for the Segments CRUD API.

Defines ``SegmentCreate``, ``SegmentUpdate``, and ``SegmentResponse``
models with validation rules for market-segment data.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── SegmentCreate ────────────────────────────────────────────────────────────


class SegmentCreate(BaseModel):
    """Schema for creating a new market segment.

    ``name`` must be unique across all segments (enforced at the service layer).
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Unique segment name (e.g. 'Enterprise B2B', 'SMB Direct').",
    )
    description: str | None = Field(
        default=None,
        description="Optional long-form description of the segment.",
    )
    target_audience: str | None = Field(
        default=None,
        description="Who this segment is targeting (e.g. 'Fortune 500 CTOs').",
    )
    tone: str | None = Field(
        default=None,
        max_length=255,
        description="Preferred tone or voice for content aimed at this segment.",
    )


# ── SegmentUpdate ────────────────────────────────────────────────────────────


class SegmentUpdate(BaseModel):
    """Schema for partially updating an existing market segment.

    All fields are optional — only provided fields are applied to the record.
    ``name`` is still validated for length and uniqueness if supplied.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="New unique segment name.",
    )
    description: str | None = Field(
        default=None,
        description="Updated long-form description.",
    )
    target_audience: str | None = Field(
        default=None,
        description="Updated target audience description.",
    )
    tone: str | None = Field(
        default=None,
        max_length=255,
        description="Updated tone or voice for content.",
    )


# ── SegmentResponse ──────────────────────────────────────────────────────────


class SegmentResponse(BaseModel):
    """Schema returned when reading segment data.

    Includes the computed ``product_count`` — the number of products
    currently assigned to this segment.
    """

    id: int
    name: str
    description: str | None
    target_audience: str | None
    tone: str | None
    created_at: datetime
    product_count: int = Field(
        default=0,
        description="Number of products assigned to this segment.",
    )

    model_config = {"from_attributes": True}
