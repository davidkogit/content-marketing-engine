"""
Pydantic request/response schemas for the LLM settings API.

Provides models for fetching, updating, and testing LLM provider
configurations — all protected behind the SUPER_ADMIN role gate.
"""


from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ── Supported Providers ─────────────────────────────────────────────────────

SUPPORTED_PROVIDERS: set[str] = {"openai", "anthropic"}
"""Set of valid provider identifiers accepted by the settings API."""


# ── Request Schemas ─────────────────────────────────────────────────────────


class LLMConfigUpdateRequest(BaseModel):
    """Request body for updating the active LLM configuration.

    All three fields are required. The API key is accepted in plain
    text via the request and encrypted before storage.
    """

    provider: str = Field(
        ...,
        min_length=1,
        description="LLM provider identifier — 'openai' or 'anthropic'.",
    )
    model: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Model identifier (e.g. 'gpt-4o', 'claude-3-opus-20240229').",
    )
    api_key: str = Field(
        default="",
        description="API key. Leave blank to keep the existing stored key.",
    )
    api_base_url: str | None = Field(
        default=None,
        description="Optional custom API base URL (e.g. https://openrouter.ai/api/v1). Uses provider default if empty.",
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Normalise and validate the provider name."""
        normalised = v.lower().strip()
        if normalised not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider '{v}'. Choose from: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
            )
        return normalised


# ── Response Schemas ────────────────────────────────────────────────────────


class LLMConfigResponse(BaseModel):
    """Response containing the active LLM configuration with a masked API key.

    The API key never appears in plain text — only the first two and last
    four characters are visible (e.g. ``sk-...aBcD``).
    """

    provider: str
    model: str
    api_base_url: str | None = None
    masked_api_key: str = Field(
        ...,
        description="Partially masked API key — e.g. 'sk-...aBcD'.",
    )
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class LLMConfigTestResponse(BaseModel):
    """Response from the LLM connection test endpoint."""

    success: bool = Field(
        ...,
        description="Whether the provider accepted the connection and returned a valid response.",
    )
    latency_ms: float = Field(
        default=0.0,
        description="Measured round-trip latency in milliseconds.",
    )
    message: str = Field(
        ...,
        description="Human-readable result (e.g. 'Connection successful' or error details).",
    )
    model_used: str | None = Field(
        default=None,
        description="The model that responded to the test prompt.",
    )
