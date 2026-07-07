"""
LLM settings service — business logic layer for the Super Admin settings API.

Wraps the lower-level ``LLMConfigService`` (encryption / DB persistence) with:
- In-memory caching of the active configuration (invalidated on update).
- API key masking for safe exposure in responses.
- Connection testing via the provider factory.
"""


import logging
import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.config_service import LLMConfigService, decrypt_api_key
from app.llm.provider_base import (
    LLMAuthError,
    LLMProviderError,
    LLMRateLimitError,
    LLMServerError,
)
from app.llm.provider_factory import get_provider, is_valid_provider
from app.models.llm_config import LLMConfig, LLMProvider
from app.settings.llm_schemas import SUPPORTED_PROVIDERS

logger = logging.getLogger(__name__)


# ── Cache ────────────────────────────────────────────────────────────────────

# Sentinel value used to distinguish "cache has never been loaded" from
# "cache was loaded but the result is None (no active config)".
_CACHE_UNSET: object = object()

# Module-level in-memory cache for the active LLM configuration.
# Reset to _CACHE_UNSET on every config update so the next read fetches fresh data.
_cached_active_config: LLMConfig | None | object = _CACHE_UNSET


def _invalidate_cache() -> None:
    """Clear the in-memory active-config cache.

    Called automatically after any update so the next ``get_active_config()``
    call hits the database for fresh data.
    """
    global _cached_active_config
    _cached_active_config = _CACHE_UNSET
    logger.debug("LLM settings cache invalidated.")


# ── Masking ──────────────────────────────────────────────────────────────────


def mask_api_key(plain_text: str) -> str:
    """Obscure an API key so only part of it is visible.

    Returns a string like ``sk-...aBcD`` (first two chars + last four).
    If the key is too short to mask safely, the entire string is replaced
    with ``...``.

    Args:
        plain_text: The full, unencrypted API key.

    Returns:
        A masked representation safe for inclusion in API responses.
    """
    if not plain_text:
        return "..."

    prefix = plain_text[:2]
    suffix = plain_text[-4:] if len(plain_text) >= 6 else ""
    return f"{prefix}...{suffix}"


# ── Configuration Read ───────────────────────────────────────────────────────


async def get_active_llm_config(db: AsyncSession) -> LLMConfig | None:
    """Retrieve the currently active LLM configuration, using cache if available.

    On first call (or after a cache invalidation) the database is queried
    and the result is cached. Subsequent calls return the cached instance
    without hitting the database.

    Args:
        db: An active async database session.

    Returns:
        The active ``LLMConfig`` row, or ``None`` if no configuration
        has been marked active.
    """
    global _cached_active_config

    if _cached_active_config is not _CACHE_UNSET:
        return _cached_active_config  # type: ignore[return-value]

    config = await LLMConfigService.get_active_config(db)
    _cached_active_config = config
    logger.debug("LLM settings cache populated: %s", config is not None)
    return config


# ── Configuration Update ─────────────────────────────────────────────────────


async def update_llm_config(
    db: AsyncSession,
    *,
    provider: str,
    model: str,
    api_key: str,
    api_base_url: str | None = None,
) -> LLMConfig:
    """Persist a new active LLM configuration, encrypting the API key first.

    Deactivates any previously active configuration, creates a new row,
    and invalidates the in-memory cache so the next read fetches fresh data.

    Args:
        db: An active async database session.
        provider: ``openai`` or ``anthropic``.
        model: Model identifier (e.g. ``gpt-4o``).
        api_key: Plain-text API key — encrypted before storage.

    Returns:
        The newly created (and flushed) ``LLMConfig`` row.

    Raises:
        ValueError: If *provider* is not a supported ``LLMProvider``.
    """
    config = await LLMConfigService.set_config(
        db,
        provider=provider,
        api_key=api_key,
        model=model,
        api_base_url=api_base_url,
        make_active=True,
    )
    # Immediately invalidate cache so callers get the fresh config.
    _invalidate_cache()
    logger.info(
        "LLM config updated: provider=%s model=%s", provider, model
    )
    return config


# ── Connection Test ──────────────────────────────────────────────────────────


async def test_llm_connection(
    db: AsyncSession,
) -> dict:
    """Test the active LLM provider connection with a lightweight ping.

    Retrieves the active config (decrypts the stored key), instantiates
    the appropriate provider via ``ProviderFactory``, sends a minimal
    test prompt, and measures the round-trip latency.

    Args:
        db: An active async database session.

    Returns:
        A dict with keys ``success`` (bool), ``latency_ms`` (float),
        ``message`` (str), and ``model_used`` (str | None).
    """
    config = await get_active_llm_config(db)

    if config is None:
        return {
            "success": False,
            "latency_ms": 0.0,
            "message": "No active LLM configuration found. Configure an LLM provider first.",
            "model_used": None,
        }

    decrypted_key = decrypt_api_key(config.api_key_encrypted)
    if decrypted_key is None:
        return {
            "success": False,
            "latency_ms": 0.0,
            "message": "Failed to decrypt the stored API key. The encryption key may have been rotated.",
            "model_used": None,
        }

    provider_name = config.provider.value if isinstance(config.provider, LLMProvider) else str(config.provider)

    try:
        provider = get_provider(
            provider_name=provider_name,
            api_key=decrypted_key,
            model=config.model_name,
        )
    except ValueError as exc:
        return {
            "success": False,
            "latency_ms": 0.0,
            "message": f"Unsupported provider: {exc}",
            "model_used": None,
        }

    start = time.monotonic()
    try:
        response = await provider.generate(
            prompt='Respond with exactly the word "ok" and nothing else.',
            system_prompt="You are a connection test. Respond as briefly as possible.",
            max_tokens=10,
        )
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "success": True,
            "latency_ms": round(latency_ms, 2),
            "message": "Connection successful.",
            "model_used": response.model_used,
        }
    except LLMAuthError as exc:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "success": False,
            "latency_ms": round(latency_ms, 2),
            "message": f"Authentication failed. Check your API key. Details: {exc}",
            "model_used": None,
        }
    except LLMRateLimitError as exc:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "success": False,
            "latency_ms": round(latency_ms, 2),
            "message": f"Rate limit exceeded. Try again later. Details: {exc}",
            "model_used": None,
        }
    except LLMServerError as exc:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "success": False,
            "latency_ms": round(latency_ms, 2),
            "message": f"Provider server error. Details: {exc}",
            "model_used": None,
        }
    except LLMProviderError as exc:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "success": False,
            "latency_ms": round(latency_ms, 2),
            "message": f"Provider error: {exc}",
            "model_used": None,
        }
