"""
Unit tests for LLM providers: base class, OpenAIProvider, AnthropicProvider, and factory.

All external SDK calls are mocked so tests run without API keys or network.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.provider_base import (
    LLMAuthError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMServerError,
)
from app.llm.openai_provider import OpenAIProvider
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.provider_factory import get_provider, is_valid_provider, list_providers


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def openai_provider() -> OpenAIProvider:
    """Return an OpenAIProvider with a fake API key."""
    return OpenAIProvider(api_key="sk-test-key", model="gpt-4o")


@pytest.fixture
def anthropic_provider() -> AnthropicProvider:
    """Return an AnthropicProvider with a fake API key."""
    return AnthropicProvider(api_key="sk-ant-test-key", model="claude-3-opus-20240229")


# ── LLMResponse dataclass ──────────────────────────────────────────────────


class TestLLMResponse:
    """Tests for the LLMResponse dataclass."""

    def test_default_values(self) -> None:
        """LLMResponse should have sensible defaults for optional fields."""
        resp = LLMResponse(content="hello", model_used="test-model", tokens_used=100)
        assert resp.content == "hello"
        assert resp.model_used == "test-model"
        assert resp.tokens_used == 100
        assert resp.finish_reason == "stop"
        assert resp.latency_ms == 0.0

    def test_all_fields_populated(self) -> None:
        """All fields should be settable via constructor."""
        resp = LLMResponse(
            content="generated text",
            model_used="gpt-4o",
            tokens_used=350,
            finish_reason="length",
            latency_ms=1245.67,
        )
        assert resp.content == "generated text"
        assert resp.model_used == "gpt-4o"
        assert resp.tokens_used == 350
        assert resp.finish_reason == "length"
        assert resp.latency_ms == 1245.67


# ── LLMProvider base class ─────────────────────────────────────────────────


class TestLLMProviderAbstract:
    """LLMProvider cannot be instantiated directly (it's abstract)."""

    def test_cannot_instantiate_abstract(self) -> None:
        """Instantiating LLMProvider directly should raise TypeError."""
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]

    def test_concrete_subclass_can_instantiate(self) -> None:
        """A concrete subclass that implements generate should work."""

        class FakeProvider(LLMProvider):
            async def generate(self, prompt, *, system_prompt="", **kwargs):
                return LLMResponse(
                    content=f"echo: {prompt}",
                    model_used="fake",
                    tokens_used=10,
                )

        provider = FakeProvider()
        assert isinstance(provider, LLMProvider)

    async def test_subclass_generate_works(self) -> None:
        """Calling generate on a concrete subclass should work."""

        class EchoProvider(LLMProvider):
            async def generate(self, prompt, *, system_prompt="", **kwargs):
                return LLMResponse(
                    content=prompt.upper(),
                    model_used="echo",
                    tokens_used=len(prompt.split()),
                )

        provider = EchoProvider()
        response = await provider.generate("hello world")
        assert response.content == "HELLO WORLD"
        assert response.model_used == "echo"
        assert response.tokens_used == 2


# ── OpenAIProvider ──────────────────────────────────────────────────────────


class TestOpenAIProviderGenerate:
    """Tests for OpenAIProvider.generate() with mocked SDK client."""

    @pytest.fixture
    def mock_completion(self) -> MagicMock:
        """Build a mock ChatCompletion response."""
        completion = MagicMock()
        completion.model = "gpt-4o"
        completion.choices = [MagicMock()]
        completion.choices[0].message.content = "This is a test response."
        completion.choices[0].finish_reason = "stop"
        completion.usage = MagicMock()
        completion.usage.prompt_tokens = 50
        completion.usage.completion_tokens = 75
        return completion

    async def test_generate_returns_llm_response(
        self, openai_provider: OpenAIProvider, mock_completion: MagicMock
    ) -> None:
        """generate() should return an LLMResponse with content from the API."""
        with patch.object(
            openai_provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_completion,
        ):
            response = await openai_provider.generate("Write a tagline")

        assert isinstance(response, LLMResponse)
        assert response.content == "This is a test response."
        assert response.model_used == "gpt-4o"
        assert response.tokens_used == 125  # 50 + 75
        assert response.finish_reason == "stop"
        assert response.latency_ms >= 0

    async def test_generate_includes_system_prompt(
        self, openai_provider: OpenAIProvider, mock_completion: MagicMock
    ) -> None:
        """The system_prompt should be sent as a system message."""
        with patch.object(
            openai_provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_completion,
        ) as mock_create:
            await openai_provider.generate(
                "Write a tagline",
                system_prompt="You are a marketing expert.",
            )

        call_messages = mock_create.call_args.kwargs["messages"]
        assert call_messages[0] == {"role": "system", "content": "You are a marketing expert."}
        assert call_messages[1] == {"role": "user", "content": "Write a tagline"}

    async def test_generate_no_system_prompt(
        self, openai_provider: OpenAIProvider, mock_completion: MagicMock
    ) -> None:
        """When system_prompt is empty, only a user message should be sent."""
        with patch.object(
            openai_provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_completion,
        ) as mock_create:
            await openai_provider.generate("Write a tagline")

        call_messages = mock_create.call_args.kwargs["messages"]
        assert len(call_messages) == 1
        assert call_messages[0]["role"] == "user"

    async def test_generate_passes_kwargs_to_sdk(
        self, openai_provider: OpenAIProvider, mock_completion: MagicMock
    ) -> None:
        """Extra kwargs should be forwarded to the SDK call."""
        with patch.object(
            openai_provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_completion,
        ) as mock_create:
            await openai_provider.generate(
                "prompt",
                temperature=0.7,
                max_tokens=256,
                top_p=0.9,
            )

        assert mock_create.call_args.kwargs["temperature"] == 0.7
        assert mock_create.call_args.kwargs["max_tokens"] == 256
        assert mock_create.call_args.kwargs["top_p"] == 0.9

    async def test_generate_measures_latency(
        self, openai_provider: OpenAIProvider, mock_completion: MagicMock
    ) -> None:
        """The latency_ms field should be populated with elapsed milliseconds."""
        with patch.object(
            openai_provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_completion,
        ):
            response = await openai_provider.generate("ping")
        assert response.latency_ms >= 0

    async def test_generate_handles_empty_content(
        self, openai_provider: OpenAIProvider, mock_completion: MagicMock
    ) -> None:
        """If the API returns None content, it should default to empty string."""
        mock_completion.choices[0].message.content = None
        with patch.object(
            openai_provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_completion,
        ):
            response = await openai_provider.generate("prompt")
        assert response.content == ""

    async def test_generate_handles_missing_usage(
        self, openai_provider: OpenAIProvider, mock_completion: MagicMock
    ) -> None:
        """If usage data is None, tokens_used should default to 0."""
        mock_completion.usage = None
        with patch.object(
            openai_provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_completion,
        ):
            response = await openai_provider.generate("prompt")
        assert response.tokens_used == 0


# ── OpenAIProvider Error Handling ───────────────────────────────────────────


class TestOpenAIProviderErrors:
    """Error handling tests for OpenAIProvider."""

    async def test_authentication_error(self) -> None:
        """Invalid API key should raise LLMAuthError."""
        from openai import AuthenticationError

        provider = OpenAIProvider(api_key="bad-key")
        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=AuthenticationError(
                message="Incorrect API key",
                response=MagicMock(),
                body=None,
            ),
        ):
            with pytest.raises(LLMAuthError, match="Incorrect API key"):
                await provider.generate("prompt")

    async def test_rate_limit_error(self) -> None:
        """Rate limiting should raise LLMRateLimitError."""
        from openai import RateLimitError

        provider = OpenAIProvider(api_key="sk-test")
        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=RateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(),
                body=None,
            ),
        ):
            with pytest.raises(LLMRateLimitError, match="Rate limit"):
                await provider.generate("prompt")

    async def test_server_error(self) -> None:
        """5xx responses should raise LLMServerError."""
        from openai import InternalServerError

        provider = OpenAIProvider(api_key="sk-test")
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=InternalServerError(
                message="Service unavailable",
                response=mock_resp,
                body=None,
            ),
        ):
            with pytest.raises(LLMServerError, match="Service unavailable"):
                await provider.generate("prompt")

    async def test_generic_api_error(self) -> None:
        """Non-auth, non-rate, non-server API errors should raise LLMProviderError."""
        from openai import APIError

        provider = OpenAIProvider(api_key="sk-test")
        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=APIError(
                message="Unknown API error",
                request=MagicMock(),
                body=None,
            ),
        ):
            with pytest.raises(LLMProviderError, match="Unknown API error"):
                await provider.generate("prompt")

    async def test_error_is_base_class(self) -> None:
        """All specific errors should be subclasses of LLMProviderError."""
        assert issubclass(LLMAuthError, LLMProviderError)
        assert issubclass(LLMRateLimitError, LLMProviderError)
        assert issubclass(LLMServerError, LLMProviderError)


# ── AnthropicProvider ───────────────────────────────────────────────────────


class TestAnthropicProviderGenerate:
    """Tests for AnthropicProvider.generate() with mocked SDK client."""

    @pytest.fixture
    def mock_message(self) -> MagicMock:
        """Build a mock Anthropic Message response."""
        msg = MagicMock()
        msg.model = "claude-3-opus-20240229"
        # content as list of blocks mimicking the Anthropic shape
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Claude response text."
        msg.content = [text_block]
        msg.stop_reason = "end_turn"
        msg.usage = MagicMock()
        msg.usage.input_tokens = 100
        msg.usage.output_tokens = 200
        return msg

    async def test_generate_returns_llm_response(
        self, anthropic_provider: AnthropicProvider, mock_message: MagicMock
    ) -> None:
        """generate() should return an LLMResponse with content from the API."""
        with patch.object(
            anthropic_provider._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_message,
        ):
            response = await anthropic_provider.generate("Describe the product")

        assert isinstance(response, LLMResponse)
        assert response.content == "Claude response text."
        assert response.model_used == "claude-3-opus-20240229"
        assert response.tokens_used == 300  # 100 + 200
        assert response.finish_reason == "end_turn"
        assert response.latency_ms >= 0

    async def test_generate_includes_system_prompt(
        self, anthropic_provider: AnthropicProvider, mock_message: MagicMock
    ) -> None:
        """The system_prompt should be passed via the `system` parameter."""
        with patch.object(
            anthropic_provider._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_message,
        ) as mock_create:
            await anthropic_provider.generate(
                "Write copy",
                system_prompt="You are a copywriter.",
            )

        assert mock_create.call_args.kwargs["system"] == "You are a copywriter."

    async def test_generate_empty_system_prompt(
        self, anthropic_provider: AnthropicProvider, mock_message: MagicMock
    ) -> None:
        """An empty system_prompt should pass None as the system parameter."""
        with patch.object(
            anthropic_provider._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_message,
        ) as mock_create:
            await anthropic_provider.generate("Write copy", system_prompt="")

        assert mock_create.call_args.kwargs["system"] is None

    async def test_generate_always_includes_max_tokens(
        self, anthropic_provider: AnthropicProvider, mock_message: MagicMock
    ) -> None:
        """Anthropic requires max_tokens — the provider should set a default."""
        with patch.object(
            anthropic_provider._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_message,
        ) as mock_create:
            await anthropic_provider.generate("prompt")

        assert mock_create.call_args.kwargs["max_tokens"] == 4096

    async def test_generate_overrides_max_tokens(
        self, anthropic_provider: AnthropicProvider, mock_message: MagicMock
    ) -> None:
        """Caller-supplied max_tokens should override the default."""
        with patch.object(
            anthropic_provider._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_message,
        ) as mock_create:
            await anthropic_provider.generate("prompt", max_tokens=512)

        assert mock_create.call_args.kwargs["max_tokens"] == 512

    async def test_generate_text_blocks_are_joined(
        self, anthropic_provider: AnthropicProvider, mock_message: MagicMock
    ) -> None:
        """Multiple text content blocks should be concatenated."""
        block1 = MagicMock()
        block1.type = "text"
        block1.text = "Part one. "
        block2 = MagicMock()
        block2.type = "text"
        block2.text = "Part two."
        block3 = MagicMock()
        block3.type = "tool_use"  # non-text block — should be ignored
        mock_message.content = [block1, block2, block3]

        with patch.object(
            anthropic_provider._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_message,
        ):
            response = await anthropic_provider.generate("prompt")

        assert response.content == "Part one. Part two."

    async def test_generate_handles_missing_usage(
        self, anthropic_provider: AnthropicProvider, mock_message: MagicMock
    ) -> None:
        """If usage data is None, tokens_used should default to 0."""
        mock_message.usage = None
        with patch.object(
            anthropic_provider._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_message,
        ):
            response = await anthropic_provider.generate("prompt")
        assert response.tokens_used == 0

    async def test_generate_none_stop_reason_defaults(
        self, anthropic_provider: AnthropicProvider, mock_message: MagicMock
    ) -> None:
        """If stop_reason is None, default to 'end_turn'."""
        mock_message.stop_reason = None
        with patch.object(
            anthropic_provider._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_message,
        ):
            response = await anthropic_provider.generate("prompt")
        assert response.finish_reason == "end_turn"


# ── AnthropicProvider Error Handling ───────────────────────────────────────


class TestAnthropicProviderErrors:
    """Error handling tests for AnthropicProvider."""

    async def test_authentication_error(self) -> None:
        """Invalid API key should raise LLMAuthError."""
        from anthropic import AuthenticationError

        provider = AnthropicProvider(api_key="bad-key")
        with patch.object(
            provider._client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=AuthenticationError(
                message="Invalid API key",
                response=MagicMock(),
                body=None,
            ),
        ):
            with pytest.raises(LLMAuthError, match="Invalid API key"):
                await provider.generate("prompt")

    async def test_rate_limit_error(self) -> None:
        """Rate limiting should raise LLMRateLimitError."""
        from anthropic import RateLimitError

        provider = AnthropicProvider(api_key="sk-ant-test")
        with patch.object(
            provider._client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=RateLimitError(
                message="Too many requests",
                response=MagicMock(),
                body=None,
            ),
        ):
            with pytest.raises(LLMRateLimitError, match="Too many requests"):
                await provider.generate("prompt")

    async def test_server_error(self) -> None:
        """5xx responses should raise LLMServerError."""
        from anthropic import APIStatusError

        provider = AnthropicProvider(api_key="sk-ant-test")
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch.object(
            provider._client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=APIStatusError(
                message="Overloaded",
                response=mock_resp,
                body=None,
            ),
        ):
            with pytest.raises(LLMServerError, match="Overloaded"):
                await provider.generate("prompt")

    async def test_generic_api_error(self) -> None:
        """Non-5xx API errors should raise LLMProviderError."""
        from anthropic import APIStatusError

        provider = AnthropicProvider(api_key="sk-ant-test")
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        with patch.object(
            provider._client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=APIStatusError(
                message="Bad request",
                response=mock_resp,
                body=None,
            ),
        ):
            with pytest.raises(LLMProviderError, match="Bad request"):
                await provider.generate("prompt")


# ── ProviderFactory ─────────────────────────────────────────────────────────


class TestProviderFactory:
    """Tests for get_provider, list_providers, and is_valid_provider."""

    def test_get_provider_openai(self) -> None:
        """get_provider with 'openai' should return an OpenAIProvider."""
        provider = get_provider("openai", api_key="sk-test", model="gpt-4o")
        assert isinstance(provider, OpenAIProvider)

    def test_get_provider_anthropic(self) -> None:
        """get_provider with 'anthropic' should return an AnthropicProvider."""
        provider = get_provider("anthropic", api_key="sk-ant-test", model="claude-3-opus")
        assert isinstance(provider, AnthropicProvider)

    def test_get_provider_case_insensitive(self) -> None:
        """Provider lookup should be case-insensitive and trim whitespace."""
        variants = ["OpenAI", "OPENAI", " openai ", "Anthropic", "ANTHROPIC"]
        classes = [OpenAIProvider, OpenAIProvider, OpenAIProvider, AnthropicProvider, AnthropicProvider]
        for variant, expected_cls in zip(variants, classes):
            provider = get_provider(variant, api_key="sk-test", model="test")
            assert isinstance(provider, expected_cls)

    def test_unsupported_provider_raises(self) -> None:
        """An unrecognised provider name should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            get_provider("cohere", api_key="test", model="command-r")

    def test_list_providers(self) -> None:
        """list_providers should return both supported providers."""
        providers = list_providers()
        assert "openai" in providers
        assert "anthropic" in providers

    def test_is_valid_provider(self) -> None:
        """is_valid_provider should return True for known providers."""
        assert is_valid_provider("openai") is True
        assert is_valid_provider("anthropic") is True
        assert is_valid_provider("cohere") is False
        assert is_valid_provider("") is False


# ── Error Hierarchy ────────────────────────────────────────────────────────


class TestErrorHierarchy:
    """The error classes should form a sensible hierarchy."""

    def test_provider_errors_are_exceptions(self) -> None:
        """All LLM errors should be subclasses of Exception."""
        assert issubclass(LLMProviderError, Exception)
        assert issubclass(LLMAuthError, Exception)
        assert issubclass(LLMRateLimitError, Exception)
        assert issubclass(LLMServerError, Exception)

    def test_specific_errors_extend_base(self) -> None:
        """Auth, rate-limit, and server errors should extend LLMProviderError."""
        assert issubclass(LLMAuthError, LLMProviderError)
        assert issubclass(LLMRateLimitError, LLMProviderError)
        assert issubclass(LLMServerError, LLMProviderError)
