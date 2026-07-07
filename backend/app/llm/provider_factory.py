"""
Provider factory that resolves a provider name to a concrete LLMProvider instance.

Maps provider identifiers (``openai``, ``anthropic``) to their respective
provider classes and injects the API key and model configuration.
"""


from typing import Type

from app.llm.provider_base import LLMProvider
from app.llm.openai_provider import OpenAIProvider
from app.llm.anthropic_provider import AnthropicProvider

# ── Provider Registry ───────────────────────────────────────────────────────

_PROVIDER_MAP: dict[str, Type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}

# ── Public API ──────────────────────────────────────────────────────────────


def get_provider(provider_name: str, api_key: str, model: str) -> LLMProvider:
    """Return a configured LLM provider instance.

    Args:
        provider_name: Lowercase provider identifier (``openai`` | ``anthropic``).
        api_key: API key for the chosen provider.
        model: Model identifier (e.g. ``gpt-4o``, ``claude-3-opus-20240229``).

    Returns:
        A concrete ``LLMProvider`` instance ready to call ``.generate()``.

    Raises:
        ValueError: If *provider_name* is not in the supported provider registry.
    """
    normalized = provider_name.lower().strip()

    provider_cls = _PROVIDER_MAP.get(normalized)
    if provider_cls is None:
        supported = ", ".join(sorted(_PROVIDER_MAP.keys()))
        raise ValueError(
            f"Unsupported LLM provider {provider_name!r}. "
            f"Choose from: {supported}"
        )

    return provider_cls(api_key=api_key, model=model)


def list_providers() -> list[str]:
    """Return the list of supported provider identifiers."""
    return sorted(_PROVIDER_MAP.keys())


def is_valid_provider(provider_name: str) -> bool:
    """Check whether *provider_name* is a supported LLM provider."""
    return provider_name.lower().strip() in _PROVIDER_MAP
