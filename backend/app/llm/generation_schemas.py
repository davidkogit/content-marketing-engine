"""
Pydantic schemas for the content generation pipeline.

Defines generation types, request/response models for the generate endpoint,
claim/source/violation anchors, and the async task-status polling response.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ── GenerationType ───────────────────────────────────────────────────────────


class GenerationType(str, Enum):
    """Content generation types supported by the LLM pipeline."""

    PRODUCT_DESCRIPTION = "product_description"
    FEATURE_BULLETS = "feature_bullets"
    SOCIAL_POST = "social_post"
    TAGLINE = "tagline"
    SEO_META = "seo_meta"
    EMAIL_BLAST = "email_blast"


# ── Request ─────────────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    """Request body for POST /api/generate/{product_id}."""

    generation_type: GenerationType = Field(
        default=GenerationType.PRODUCT_DESCRIPTION,
        description="Type of marketing content to generate.",
    )


# ── Structured anchors ─────────────────────────────────────────────────────


class ExtractedClaim(BaseModel):
    """A factual claim extracted from the LLM-generated copy.

    Each claim should be verifiable against a source document.  The
    ``confidence_score`` reflects how strongly the claim matches the
    cited source document (0.0–1.0).
    """

    text: str = Field(..., min_length=1, description="The claim text extracted from the generated copy.")
    source_doc_id: int | None = Field(
        None, description="ID of the source document anchoring this claim."
    )
    confidence_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Confidence that this claim is substantiated by the cited source."
    )


class SourceRef(BaseModel):
    """Reference to a source document used during generation."""

    doc_id: int
    title: str
    relevant_excerpt: str = Field(
        default="",
        description="The excerpt from the source document most relevant to the generated content.",
    )


class RuleViolation(BaseModel):
    """A detected violation of a brand-governance rule in the generated copy."""

    rule_type: str = Field(
        ...,
        description="Category of the violated rule: 'tone', 'compliance', or 'style'.",
    )
    description: str = Field(
        ...,
        description="Human-readable explanation of the violation.",
    )
    rule_text: str = Field(
        ...,
        description="The relevant excerpt from the brand rule that was violated.",
    )


# ── Metadata ────────────────────────────────────────────────────────────────


class GenerationMetadata(BaseModel):
    """Metadata about the LLM generation run."""

    model: str = Field(..., description="LLM model identifier (e.g. gpt-4o).")
    tokens: int = Field(default=0, ge=0, description="Total tokens consumed (prompt + completion).")
    latency: float = Field(default=0.0, ge=0.0, description="Total generation latency in milliseconds.")


# ── Main Response ───────────────────────────────────────────────────────────


class GeneratedResponse(BaseModel):
    """Structured response envelope returned by the generation pipeline.

    Contains the generated copy alongside claims, sources, flags, and any
    detected brand-rule violations — providing an audit trail directly in
    the response.
    """

    copy: str = Field(..., description="The generated marketing copy text.")
    claims: list[ExtractedClaim] = Field(
        default_factory=list,
        description="Factual claims extracted from the copy, anchored to source documents.",
    )
    flags: list[str] = Field(
        default_factory=list,
        description="Warnings or informational flags about the generated content.",
    )
    sources: list[SourceRef] = Field(
        default_factory=list,
        description="Source document references used during generation.",
    )
    violations: list[RuleViolation] = Field(
        default_factory=list,
        description="Brand rule violations detected in the generated copy.",
    )
    metadata: GenerationMetadata = Field(
        ..., description="Metadata about the LLM generation run."
    )


# ── Async Task Status ───────────────────────────────────────────────────────


class TaskStatus(str, Enum):
    """Lifecycle states for an async generation task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatusResponse(BaseModel):
    """Response model for GET /api/generate/status/{task_id}."""

    task_id: str = Field(..., description="Unique identifier for the generation task.")
    status: TaskStatus = Field(..., description="Current lifecycle state of the task.")
    result: GeneratedResponse | None = Field(
        None, description="The generated result (populated when status=completed)."
    )
    error: str | None = Field(
        None, description="Error message (populated when status=failed)."
    )
