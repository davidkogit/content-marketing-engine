"""
OpenAI provider implementing the LLMProvider interface.

Uses the ``openai`` Python SDK with an async client to generate chat
completions, mapping the SDK response into the standard ``LLMResponse``.
"""


import logging
from typing import Any

from openai import APIError, AsyncOpenAI, AuthenticationError, RateLimitError
from openai.types.chat import ChatCompletion

from app.llm.provider_base import (
    LLMAuthError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMServerError,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """Async provider backed by the OpenAI chat-completions API."""

    def __init__(self, api_key: str, model: str = "gpt-4o", **client_kwargs: Any) -> None:
        """Create an OpenAI provider instance.

        Args:
            api_key: OpenAI API key.
            model: Model identifier (e.g. ``gpt-4o``, ``gpt-4o-mini``).
            **client_kwargs: Extra parameters forwarded to ``AsyncOpenAI``
                             (e.g. ``base_url``, ``timeout``).
        """
        self._model: str = model
        self._client: AsyncOpenAI = AsyncOpenAI(
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
        """Call the OpenAI chat-completions endpoint.

        See ``LLMProvider.generate`` for parameter documentation.
        """
        messages = self._build_messages(prompt, system_prompt)
        started_at = self._now_ms()

        try:
            completion: ChatCompletion = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                **kwargs,  # type: ignore[arg-type]
            )
        except AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except APIError as exc:
            status = getattr(exc, "status_code", None) or 0
            if 500 <= status < 600:
                raise LLMServerError(str(exc)) from exc
            raise LLMProviderError(str(exc)) from exc

        elapsed_ms = self._now_ms() - started_at
        return self._parse_response(completion, elapsed_ms)

    # ── Internal ────────────────────────────────────────────────────────────

    @staticmethod
    def _build_messages(prompt: str, system_prompt: str) -> list[dict[str, str]]:
        """Build the OpenAI messages payload from prompt and system prompt."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    @staticmethod
    def _parse_response(completion: ChatCompletion, elapsed_ms: float) -> LLMResponse:
        """Map an OpenAI ChatCompletion into our standard LLMResponse."""
        choice = completion.choices[0]
        content: str = choice.message.content or ""
        usage = completion.usage
        tokens_used: int = (usage.prompt_tokens + usage.completion_tokens) if usage else 0

        return LLMResponse(
            content=content,
            model_used=completion.model,
            tokens_used=tokens_used,
            finish_reason=choice.finish_reason or "stop",
            latency_ms=round(elapsed_ms, 2),
        )
