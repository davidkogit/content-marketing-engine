"""
Anthropic provider implementing the LLMProvider interface.

Uses the ``anthropic`` Python SDK with an async client to generate messages,
mapping the SDK response into the standard ``LLMResponse``.
"""


import logging
from typing import Any

from anthropic import (
    APIStatusError,
    AsyncAnthropic,
    AuthenticationError,
    RateLimitError,
)
from anthropic.types import Message

from app.llm.provider_base import (
    LLMAuthError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMServerError,
)

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Async provider backed by the Anthropic Messages API."""

    # Anthropic requires max_tokens for every request.
    _DEFAULT_MAX_TOKENS: int = 4096

    def __init__(self, api_key: str, model: str = "claude-3-opus-20240229", **client_kwargs: Any) -> None:
        """Create an Anthropic provider instance.

        Args:
            api_key: Anthropic API key.
            model: Model identifier (e.g. ``claude-3-opus-20240229``).
            **client_kwargs: Extra parameters forwarded to ``AsyncAnthropic``
                             (e.g. ``base_url``, ``timeout``).
        """
        self._model: str = model
        self._client: AsyncAnthropic = AsyncAnthropic(
            api_key=api_key,
            **client_kwargs,
        )

    # ── Public API ──────────────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        **kwargs: object,
    ) -> LLMResponse:
        """Call the Anthropic Messages endpoint.

        See ``LLMProvider.generate`` for parameter documentation.
        """
        # Ensure max_tokens is always set (Anthropic requires it).
        params: dict[str, object] = {"max_tokens": self._DEFAULT_MAX_TOKENS}
        params.update(kwargs)

        started_at = self._now_ms()

        try:
            message: Message = await self._client.messages.create(
                model=self._model,
                system=system_prompt if system_prompt else None,  # type: ignore[arg-type]
                messages=[{"role": "user", "content": prompt}],
                **params,  # type: ignore[arg-type]
            )
        except AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except APIStatusError as exc:
            if 500 <= exc.status_code < 600:
                raise LLMServerError(str(exc)) from exc
            raise LLMProviderError(str(exc)) from exc

        elapsed_ms = self._now_ms() - started_at
        return self._parse_response(message, elapsed_ms)

    # ── Internal ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_response(message: Message, elapsed_ms: float) -> LLMResponse:
        """Map an Anthropic Message into our standard LLMResponse."""
        # Anthropic returns content as a list of blocks; extract text blocks.
        content_parts: list[str] = [
            block.text
            for block in message.content
            if block.type == "text" and hasattr(block, "text")
        ]
        content = "".join(content_parts)

        tokens_used: int = (
            message.usage.input_tokens + message.usage.output_tokens
            if message.usage
            else 0
        )

        return LLMResponse(
            content=content,
            model_used=message.model,
            tokens_used=tokens_used,
            finish_reason=message.stop_reason or "end_turn",
            latency_ms=round(elapsed_ms, 2),
        )
