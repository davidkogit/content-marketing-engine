"""
Application configuration loaded from environment variables.

Uses pydantic-settings for .env file support, sensible defaults,
and startup validation to fail-fast on misconfiguration.
"""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=True,
    )

    # ── Application ────────────────────────────────────────────────────────
    ENVIRONMENT: str = Field(
        default="development",
        description="Runtime environment (development, staging, production).",
    )

    # ── Security ───────────────────────────────────────────────────────────
    SECRET_KEY: str = Field(
        ...,
        min_length=32,
        description="Secret key for JWT token signing. Must be at least 32 characters.",
    )
    JWT_EXPIRY_MINUTES: int = Field(
        default=60,
        ge=1,
        description="JWT token expiry time in minutes.",
    )
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:5173",
        description="Comma-separated list of allowed CORS origins.",
    )
    SECURE_COOKIES: bool = Field(
        default=True,
        description="Set cookies with Secure flag. Disable when running on HTTP (no TLS).",
    )

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./data/products.db",
        description="Database connection URL. Defaults to local SQLite file.",
    )

    # ── LLM Configuration ──────────────────────────────────────────────────
    LLM_PROVIDER: str = Field(
        default="openai",
        description="LLM provider: 'openai' or 'anthropic'.",
    )
    LLM_API_KEY: SecretStr | None = Field(
        default=None,
        description="Fallback API key (used only if no DB config exists). Set via Settings page in UI.",
    )
    LLM_MODEL: str = Field(
        default="gpt-4o",
        description="Fallback model identifier (used only if no DB config exists).",
    )

    @field_validator("LLM_PROVIDER")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        """Ensure LLM provider is one of the supported values."""
        allowed = {"openai", "anthropic"}
        if v.lower() not in allowed:
            raise ValueError(
                f"LLM_PROVIDER must be one of {allowed!r}, got {v!r}"
            )
        return v.lower()

    @model_validator(mode="after")
    def validate_llm_config(self) -> "Settings":
        """Validate LLM provider name. API key is optional here — it can be set via the Admin UI."""
        return self

    # ── Derived Properties ─────────────────────────────────────────────────

    @property
    def database_path(self) -> Path:
        """Extract the filesystem path from the database URL."""
        # sqlite+aiosqlite:///./data/products.db → ./data/products.db
        db_part = self.DATABASE_URL.replace("sqlite+aiosqlite:///", "", 1)
        return Path(db_part)

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse ALLOWED_ORIGINS into a list of URLs."""
        return [
            origin.strip()
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]


def load_settings() -> Settings:
    """Load and validate application settings from the environment."""
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load application configuration: {exc}"
        ) from exc


# Singleton instance — import this throughout the application.
settings: Settings = load_settings()
