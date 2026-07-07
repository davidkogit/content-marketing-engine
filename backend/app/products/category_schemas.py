"""
Pydantic request/response schemas for category endpoints.

Defines ``CategoryCreate``, ``CategoryUpdate``, and ``CategoryResponse``
models with validation rules matching the SQLAlchemy Category model.
"""


from datetime import datetime

from pydantic import BaseModel, Field


# ── Request Schemas ─────────────────────────────────────────────────────────


class CategoryCreate(BaseModel):
    """Request body for creating a new category.

    The ``name`` must be unique across all categories. ``description`` is
    optional free-form text providing additional context about the category.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Unique name for the category (1–255 characters).",
    )
    description: str | None = Field(
        default=None,
        description="Optional human-readable description of the category.",
    )


class CategoryUpdate(BaseModel):
    """Request body for updating an existing category.

    All fields are optional — only the supplied fields will be mutated.
    If ``name`` is provided it must pass uniqueness checks at the service layer.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="New unique name for the category (1–255 characters).",
    )
    description: str | None = Field(
        default=None,
        description="New description. Pass an empty string to clear.",
    )


# ── Response Schemas ────────────────────────────────────────────────────────


class CategoryResponse(BaseModel):
    """Response model for a single category including metadata.

    Includes the ``id``, ``name``, ``description``, timestamps, and a
    ``product_count`` that reflects how many products are linked to this
    category in the database. The count is populated dynamically via a
    subquery at read time — it is not stored on the model.

    Uses ``from_attributes=True`` to enable automatic conversion from
    SQLAlchemy ORM instances, with ``product_count`` set separately.
    """

    id: int
    name: str
    description: str | None
    product_count: int = Field(
        default=0,
        description="Number of products currently assigned to this category.",
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
