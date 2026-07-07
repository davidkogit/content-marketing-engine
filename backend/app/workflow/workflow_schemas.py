"""
Pydantic request/response schemas for workflow API endpoints.

Defines schemas for Kanban board view, stage transitions, approval
shortcuts, and workflow history timeline.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.product import WorkflowStage


# ── Board Schemas ────────────────────────────────────────────────────────────


class BoardProductItem(BaseModel):
    """Minimal product info displayed on Kanban board cards."""

    id: int
    sku: str
    name: str
    workflow_stage: str

    model_config = {"from_attributes": True}


class BoardColumn(BaseModel):
    """A single Kanban column — one workflow stage with its products and count."""

    stage: str = Field(..., description="Workflow stage identifier.")
    count: int = Field(..., description="Number of products in this column.")
    products: list[BoardProductItem] = Field(
        default_factory=list,
        description="Products currently in this workflow stage.",
    )


class BoardResponse(BaseModel):
    """Full Kanban board view — all columns with products grouped by stage."""

    columns: list[BoardColumn] = Field(
        ..., description="One column per workflow stage."
    )


# ── Transition Schemas ───────────────────────────────────────────────────────


class TransitionRequest(BaseModel):
    """Request body for transitioning a product to a new workflow stage."""

    to_stage: WorkflowStage = Field(
        ..., description="Target workflow stage for the transition."
    )
    comment: str | None = Field(
        None,
        max_length=500,
        description="Optional note explaining the transition reason.",
    )


class RequestChangesRequest(BaseModel):
    """Request body for sending a product back to draft for revisions."""

    comment: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Required explanation of what changes are needed.",
    )


class TransitionResponse(BaseModel):
    """Response after a successful workflow stage transition."""

    product_id: int = Field(..., description="ID of the transitioned product.")
    from_stage: str = Field(..., description="Previous workflow stage.")
    to_stage: str = Field(..., description="New workflow stage.")
    version_number: int = Field(
        ..., description="Version number created by this transition."
    )
    comment: str | None = Field(
        None, description="Comment attached to the transition."
    )


# ── History Schemas ──────────────────────────────────────────────────────────


class WorkflowHistoryItem(BaseModel):
    """A single entry in the workflow stage transition timeline."""

    id: int = Field(..., description="ProductVersion record ID.")
    version_number: int = Field(..., description="Sequential version number.")
    from_stage: str = Field(..., description="Stage before the transition.")
    to_stage: str = Field(..., description="Stage after the transition.")
    change_summary: str | None = Field(
        None, description="Human-readable summary of the change."
    )
    comment: str | None = Field(
        None, description="Optional comment from the transition."
    )
    created_by: int = Field(..., description="User ID who made the transition.")
    created_at: datetime = Field(..., description="Timestamp of the transition.")

    model_config = {"from_attributes": True}
