"""
Abstract base class for LLM providers and the LLMResponse data model.

Defines the contract that every provider must implement and the standard
response envelope returned to callers.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """Standard envelope for all LLM provider responses.

    Provides a uniform interface regardless of the underlying provider
    (OpenAI, Anthropic, etc.).
    """

    content: str
    model_used: str
    tokens_used: int = field(metadata={"description": "Sum of prompt + completion tokens"})
    finish_reason: str = "stop"
    latency_ms: float = 0.0


class LLMProvider(ABC):
    """Abstract base defining the async generate contract.

    Every concrete provider (OpenAI, Anthropic, ...) must implement
    ``generate`` and return an ``LLMResponse``.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        **kwargs: object,
    ) -> LLMResponse:
        """Send a prompt to the LLM and return a standardised response.

        Args:
            prompt: The user-facing content or instruction to send.
            system_prompt: Optional system-level instruction (persona, rules).
            **kwargs: Provider-specific extras forwarded to the SDK (e.g.
                      ``temperature``, ``max_tokens``, ``top_p``).

        Returns:
            An ``LLMResponse`` with content, model info, token counts,
            finish reason, and measured latency.

        Raises:
            LLMProviderError: On provider-level failures (auth, rate-limit,
                              server error, etc.).
        """
        ...

    @staticmethod
    def _now_ms() -> float:
        """High-resolution monotonic clock in milliseconds."""
        return time.monotonic() * 1000


class LLMProviderError(Exception):
    """Base exception for all LLM provider failures."""


class LLMAuthError(LLMProviderError):
    """Authentication / invalid API key error."""


class LLMRateLimitError(LLMProviderError):
    """Rate limit exceeded — caller should back off and retry."""


class LLMServerError(LLMProviderError):
    """Provider-side server error (5xx)."""
