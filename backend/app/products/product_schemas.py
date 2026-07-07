"""
Pydantic request/response schemas for product CRUD endpoints.

Defines ProductCreate, ProductUpdate, ProductResponse (with nested
relationships), and ProductListResponse (with pagination metadata).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.product import WorkflowStage


# ── Nested Response Schemas ─────────────────────────────────────────────────


class ProductCategoryResponse(BaseModel):
    """Minimal category info nested inside product responses."""

    id: int
    name: str

    model_config = {"from_attributes": True}


class ProductSegmentResponse(BaseModel):
    """Minimal segment info nested inside product responses."""

    id: int
    name: str

    model_config = {"from_attributes": True}


class ProductDocumentResponse(BaseModel):
    """Source document reference attached to a product."""

    id: int
    title: str
    url: str
    doc_type: str

    model_config = {"from_attributes": True}


class ProductClaimResponse(BaseModel):
    """Marketing claim generated for a product."""

    id: int
    claim_text: str
    source_doc_id: int | None
    status: str

    model_config = {"from_attributes": True}


class ProductVersionResponse(BaseModel):
    """Version history entry for a product edit."""

    id: int
    version_number: int
    change_summary: str | None
    created_by: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Request Schemas ─────────────────────────────────────────────────────────


class ProductCreate(BaseModel):
    """Request body for creating a new product.

    SKU must be unique across all products. Initial workflow_stage is
    always set to 'ingest' by the service layer.
    """

    sku: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique product SKU (stock-keeping unit).",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable product name.",
    )
    description: str | None = Field(
        None,
        description="Optional long-form product description.",
    )
    category_id: int | None = Field(
        None,
        description="ID of the category to assign.",
    )
    segment_id: int | None = Field(
        None,
        description="ID of the market segment to assign.",
    )


class ProductUpdate(BaseModel):
    """Request body for partially updating an existing product.

    All fields are optional — only supplied fields are changed.
    Updating the workflow_stage allows moving products through
    the Kanban pipeline.
    """

    name: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Updated product name.",
    )
    description: str | None = Field(
        None,
        description="Updated product description.",
    )
    category_id: int | None = Field(
        None,
        description="Updated category assignment.",
    )
    segment_id: int | None = Field(
        None,
        description="Updated segment assignment.",
    )
    workflow_stage: WorkflowStage | None = Field(
        None,
        description="Target Kanban workflow stage.",
    )


# ── Response Schemas ────────────────────────────────────────────────────────


class ProductListItem(BaseModel):
    """Flat product representation used in list/paginated responses.

    Does not include nested relationships — those require eager-loading
    which is only performed on the single-product detail endpoint.
    """

    id: int
    sku: str
    name: str
    description: str | None
    category_id: int | None
    segment_id: int | None
    workflow_stage: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductResponse(ProductListItem):
    """Full product response with all nested relationships eager-loaded.

    Returned by GET /api/products/{id}. Includes category, segment,
    documents, claims, and version history.
    """

    category: ProductCategoryResponse | None = None
    segment: ProductSegmentResponse | None = None
    documents: list[ProductDocumentResponse] = []
    claims: list[ProductClaimResponse] = []
    versions: list[ProductVersionResponse] = []

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    """Paginated list of products with metadata."""

    items: list[ProductListItem]
    total: int = Field(..., description="Total number of matching products.")
    page: int = Field(..., description="Current page number (1-based).")
    page_size: int = Field(..., description="Number of items per page.")
    total_pages: int = Field(..., description="Total number of pages.")
