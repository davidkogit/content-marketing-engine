"""
Pydantic request/response schemas for the product version history API.

Defines ``VersionResponse`` (with full snapshot payload) and
``VersionListResponse`` for paginated listing.
"""


from datetime import datetime

from pydantic import BaseModel, Field


# ── VersionResponse ──────────────────────────────────────────────────────────


class VersionResponse(BaseModel):
    """A single product version record with full snapshot data.

    Includes the complete ``snapshot_json`` payload so that consumers
    can inspect what the product looked like at that point in time.
    """

    id: int
    version_number: int = Field(..., description="Auto-increment per product.")
    snapshot_json: str = Field(
        ...,
        description="Full JSON snapshot of the product state at this version.",
    )
    change_summary: str | None = Field(
        None,
        description="Human-readable summary of which fields changed.",
    )
    created_by: int = Field(
        ...,
        description="ID of the user who triggered this version.",
    )
    created_at: datetime


# ── VersionListResponse ──────────────────────────────────────────────────────


class VersionListResponse(BaseModel):
    """Response for listing all versions of a product.

    Versions are ordered by ``version_number`` descending (newest first).
    """

    versions: list[VersionResponse] = Field(
        default_factory=list,
        description="Ordered list of version records (newest first).",
    )
    total: int = Field(
        ...,
        description="Total number of versions for this product.",
    )
