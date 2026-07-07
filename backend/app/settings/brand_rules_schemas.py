"""
Pydantic request/response schemas for brand rules management.

Brand rules are markdown files (tone, compliance, style) stored in
``backend/data/rules/`` and managed by the SUPER_ADMIN through these
endpoints.
"""


from pydantic import BaseModel, Field


# ── Constants ───────────────────────────────────────────────────────────────

VALID_RULE_NAMES: set[str] = {"tone", "compliance", "style"}
"""The three brand rule documents supported by the system."""


# ── Request Schemas ─────────────────────────────────────────────────────────


class UpdateRuleRequest(BaseModel):
    """Request body for updating a brand rule's markdown content."""

    content: str = Field(
        ...,
        min_length=1,
        description="Full markdown content for the brand rule.",
    )


class PreviewRuleRequest(BaseModel):
    """Request body for previewing how a rule change affects generation."""

    content: str = Field(
        ...,
        min_length=1,
        description="Proposed new markdown content to preview.",
    )
    sample_input: str | None = Field(
        default=None,
        description=(
            "Optional sample product description or context to use in the "
            "preview. If omitted, a generic sample is used."
        ),
    )


# ── Response Schemas ────────────────────────────────────────────────────────


class RuleContentResponse(BaseModel):
    """Response containing a brand rule's full markdown content."""

    rule_name: str
    content: str


class RulePreviewResponse(BaseModel):
    """Response containing the preview of a proposed rule change."""

    rule_name: str
    current_content: str
    proposed_content: str
    sample_prompt: str
    diff_summary: str = Field(
        default="",
        description="Human-readable summary of what changed in the prompt.",
    )
