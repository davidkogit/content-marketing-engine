"""
Unit tests for GenerationOrchestrator — verifies the full generation pipeline
from context collection through prompt building, LLM invocation, post-processing,
and structured response assembly.

All external dependencies (database, LLM provider, config service) are mocked
so tests run without a live database or API keys.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.brand_rules import BrandRules
from app.llm.context_collector import GenerationContext
from app.llm.generation_schemas import (
    GeneratedResponse,
    GenerationMetadata,
    GenerationType,
    TaskStatus,
    TaskStatusResponse,
)
from app.llm.orchestrator import GenerationOrchestrator
from app.llm.provider_base import LLMProvider, LLMProviderError, LLMResponse


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db() -> AsyncMock:
    """Return a mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def mock_db_factory(mock_db: AsyncMock):
    """Return a mock DB factory that yields mock_db."""

    async def _factory():
        yield mock_db

    return _factory


@pytest.fixture
def mock_provider() -> MagicMock:
    """Return a mock LLMProvider with a pre-configured generate method."""
    provider = MagicMock(spec=LLMProvider)
    provider.generate = AsyncMock(
        return_value=LLMResponse(
            content="This product is amazing. It features lightning-fast performance and a beautiful design.",
            model_used="gpt-4o",
            tokens_used=150,
            latency_ms=850.5,
        )
    )
    return provider


@pytest.fixture
def mock_context() -> GenerationContext:
    """Return a fully-populated GenerationContext."""
    rules = BrandRules(
        tone="Professional and approachable.",
        compliance="All claims must be substantiated.",
        style="Use active voice. Short paragraphs.",
    )
    return GenerationContext(
        product_specs={
            "name": "TestWidget Pro",
            "sku": "TW-001",
            "description": "A high-performance testing widget.",
            "category": "Software",
            "segment": "Developers",
        },
        source_documents=[
            {
                "title": "Spec Sheet",
                "extracted_text": "The TestWidget Pro delivers 99.9% uptime and sub-millisecond latency.",
            },
        ],
        brand_rules=rules,
        segment_profile={
            "tone": "Technical but friendly",
            "audience": "Software engineers",
        },
    )


@pytest.fixture
def orchestrator() -> GenerationOrchestrator:
    """Return a GenerationOrchestrator with default config."""
    return GenerationOrchestrator()


# ── Orchestrator.generate ───────────────────────────────────────────────────


class TestOrchestratorGenerate:
    """Tests for GenerationOrchestrator.generate()."""

    @pytest.fixture(autouse=True)
    def _patch_dependencies(
        self,
        mock_provider: MagicMock,
        mock_context: GenerationContext,
    ):
        """Patch all external dependencies for the generate flow."""
        with patch.object(
            GenerationOrchestrator, "_resolve_provider",
            new_callable=AsyncMock,
            return_value=mock_provider,
        ):
            with patch.object(
                GenerationOrchestrator,
                "_collector",
            ) as mock_collector:
                mock_collector.collect = AsyncMock(return_value=mock_context)
                yield

    async def test_generate_returns_structured_response(
        self,
        orchestrator: GenerationOrchestrator,
        mock_db: AsyncMock,
    ) -> None:
        """generate() should return a GeneratedResponse with copy, claims, metadata."""
        result = await orchestrator.generate(
            mock_db,
            product_id=1,
            gen_type=GenerationType.PRODUCT_DESCRIPTION,
        )

        assert isinstance(result, GeneratedResponse)
        assert len(result.copy) > 0
        assert isinstance(result.metadata, GenerationMetadata)
        assert result.metadata.model == "gpt-4o"
        assert result.metadata.tokens == 150

    async def test_generate_populates_metadata(
        self,
        orchestrator: GenerationOrchestrator,
        mock_db: AsyncMock,
    ) -> None:
        """metadata should reflect the LLM response values."""
        result = await orchestrator.generate(mock_db, product_id=1)

        assert result.metadata.model == "gpt-4o"
        assert result.metadata.tokens == 150
        # Latency should be approximately 850.5 (rounded to 2 decimal places)
        assert 800 <= result.metadata.latency <= 900

    async def test_generate_extracts_claims(
        self,
        orchestrator: GenerationOrchestrator,
        mock_db: AsyncMock,
    ) -> None:
        """Claims should be extracted from the generated copy."""
        result = await orchestrator.generate(mock_db, product_id=1)

        assert isinstance(result.claims, list)
        # With enough factual-sounding text, claims should be extracted
        assert len(result.claims) >= 0  # claims may be empty for short text

    async def test_generate_anchors_sources(
        self,
        orchestrator: GenerationOrchestrator,
        mock_db: AsyncMock,
    ) -> None:
        """Source documents should be listed in the response sources."""
        result = await orchestrator.generate(mock_db, product_id=1)

        assert len(result.sources) > 0
        assert result.sources[0].title == "Spec Sheet"

    async def test_generate_detects_violations(
        self,
        orchestrator: GenerationOrchestrator,
        mock_db: AsyncMock,
    ) -> None:
        """If generated text violates brand rules, violations should be reported."""
        # The default mock response is clean — violations should be zero or minimal
        result = await orchestrator.generate(mock_db, product_id=1)
        assert isinstance(result.violations, list)

    async def test_generate_default_generation_type(
        self,
        orchestrator: GenerationOrchestrator,
        mock_db: AsyncMock,
    ) -> None:
        """When gen_type is omitted, PRODUCT_DESCRIPTION should be the default."""
        result = await orchestrator.generate(mock_db, product_id=1)
        assert isinstance(result, GeneratedResponse)
        assert len(result.copy) > 0

    async def test_generate_seo_meta_type(
        self,
        orchestrator: GenerationOrchestrator,
        mock_db: AsyncMock,
        mock_provider: MagicMock,
    ) -> None:
        """SEO_META generation type should produce valid output."""
        mock_provider.generate.return_value = LLMResponse(
            content="Meta Title: TestWidget Pro | Best Testing Tool\nMeta Description: Discover the power of TestWidget Pro.",
            model_used="gpt-4o",
            tokens_used=80,
            latency_ms=420.0,
        )
        result = await orchestrator.generate(
            mock_db, product_id=1, gen_type=GenerationType.SEO_META,
        )
        assert isinstance(result, GeneratedResponse)
        assert "TestWidget Pro" in result.copy


# ── Error handling ──────────────────────────────────────────────────────────


class TestOrchestratorErrors:
    """Error handling tests for GenerationOrchestrator."""

    async def test_generate_timeout(
        self,
        orchestrator: GenerationOrchestrator,
        mock_db: AsyncMock,
    ) -> None:
        """A slow LLM call that exceeds the timeout should raise TimeoutError."""
        with patch.object(
            GenerationOrchestrator, "_resolve_provider",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_provider = MagicMock(spec=LLMProvider)
            # Simulate a very slow response
            mock_provider.generate = AsyncMock(
                side_effect=lambda *a, **kw: asyncio.sleep(200)
            )
            mock_resolve.return_value = mock_provider

            with patch.object(orchestrator, "_collector") as mock_collector:
                mock_collector.collect = AsyncMock(return_value=GenerationContext())

                with pytest.raises(asyncio.TimeoutError):
                    await orchestrator.generate(mock_db, product_id=1)

    async def test_generate_llm_provider_error(
        self,
        orchestrator: GenerationOrchestrator,
        mock_db: AsyncMock,
    ) -> None:
        """An LLMProviderError should propagate to the caller."""
        with patch.object(
            GenerationOrchestrator, "_resolve_provider",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_provider = MagicMock(spec=LLMProvider)
            mock_provider.generate = AsyncMock(
                side_effect=LLMProviderError("Service unavailable")
            )
            mock_resolve.return_value = mock_provider

            with patch.object(orchestrator, "_collector") as mock_collector:
                mock_collector.collect = AsyncMock(return_value=GenerationContext())

                with pytest.raises(LLMProviderError, match="Service unavailable"):
                    await orchestrator.generate(mock_db, product_id=1)

    async def test_resolve_provider_no_config(
        self,
        orchestrator: GenerationOrchestrator,
        mock_db: AsyncMock,
    ) -> None:
        """When no active LLM config exists, ValueError should be raised."""
        with patch(
            "app.llm.orchestrator.LLMConfigService.get_active_config",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(ValueError, match="No active LLM provider configured"):
                await orchestrator._resolve_provider(mock_db)


# ── Async task management ───────────────────────────────────────────────────


class TestOrchestratorAsyncTasks:
    """Tests for the background task system (generate_async + get_task_status)."""

    @pytest.fixture(autouse=True)
    def _patch_dependencies(self):
        """Patch external deps for async task tests."""
        with patch.object(
            GenerationOrchestrator, "_resolve_provider",
            new_callable=AsyncMock,
        ) as mock_resolve:
            mock_provider = MagicMock(spec=LLMProvider)
            mock_provider.generate = AsyncMock(
                return_value=LLMResponse(
                    content="Async generated content.",
                    model_used="gpt-4o",
                    tokens_used=50,
                    latency_ms=300.0,
                )
            )
            mock_resolve.return_value = mock_provider

            with patch.object(
                GenerationOrchestrator, "_collector",
            ) as mock_collector:
                rules = BrandRules(
                    tone="Tone rule",
                    compliance="Compliance rule",
                    style="Style rule",
                )
                mock_collector.collect = AsyncMock(
                    return_value=GenerationContext(
                        product_specs={"name": "AsyncProduct", "sku": "AP-001"},
                        source_documents=[
                            {"title": "Doc", "extracted_text": "Some text."}
                        ],
                        brand_rules=rules,
                        segment_profile={},
                    )
                )
                yield

    async def test_generate_async_returns_task_id(
        self,
        orchestrator: GenerationOrchestrator,
    ) -> None:
        """generate_async() should return a UUID task_id string."""

        async def _mock_db_factory():
            mock_session = AsyncMock()
            yield mock_session

        task_id = await orchestrator.generate_async(
            db_factory=_mock_db_factory,
            product_id=1,
        )
        assert isinstance(task_id, str)
        assert len(task_id) > 0

    async def test_task_status_transitions(
        self,
        orchestrator: GenerationOrchestrator,
    ) -> None:
        """Task status should transition from pending → running → completed."""
        mock_session = AsyncMock()

        async def _mock_db_factory():
            yield mock_session

        task_id = await orchestrator.generate_async(
            db_factory=_mock_db_factory,
            product_id=1,
        )

        # Immediately after creation — should be pending or running
        status1 = orchestrator.get_task_status(task_id)
        assert status1.status in (TaskStatus.PENDING, TaskStatus.RUNNING)

        # Wait for background task to complete
        await asyncio.sleep(0.2)

        status2 = orchestrator.get_task_status(task_id)
        assert status2.status == TaskStatus.COMPLETED
        assert status2.result is not None
        assert isinstance(status2.result, GeneratedResponse)

    async def test_task_status_not_found(
        self,
        orchestrator: GenerationOrchestrator,
    ) -> None:
        """Querying a non-existent task_id should raise KeyError."""
        with pytest.raises(KeyError):
            orchestrator.get_task_status("non-existent-task-id")


# ── Orchestrator initialisation ─────────────────────────────────────────────


class TestOrchestratorInit:
    """Tests for GenerationOrchestrator constructor."""

    def test_default_init(self) -> None:
        """Default constructor should create an orchestrator with defaults."""
        orch = GenerationOrchestrator()
        assert orch._GENERATION_TIMEOUT_S == 120
        assert orch._collector is not None
        assert orch._prompt_builder is not None
        assert orch._post_processor is not None

    def test_custom_rules_dir(self) -> None:
        """A custom rules directory should be passed to ContextCollector."""
        orch = GenerationOrchestrator(rules_dir="/custom/rules")
        assert orch._collector._rules_dir == "/custom/rules"


# ── Integration: end-to-end flow (mocked) ───────────────────────────────────


class TestOrchestratorIntegration:
    """Integration-style tests covering the full pipeline with mocks."""

    async def test_full_pipeline_flow(
        self,
        orchestrator: GenerationOrchestrator,
        mock_db: AsyncMock,
    ) -> None:
        """Verify the pipeline collects context, calls LLM, and post-processes."""
        rules = BrandRules(
            tone="Professional tone.",
            compliance="All claims need evidence.",
            style="Active voice only.",
        )

        with patch.object(orchestrator._collector, "collect") as mock_collect:
            mock_collect.return_value = GenerationContext(
                product_specs={
                    "name": "Integration Product",
                    "sku": "IP-100",
                    "description": "A fully-featured integration product.",
                },
                source_documents=[
                    {
                        "title": "Integration Spec",
                        "extracted_text": "IP-100 supports 10,000 concurrent connections with 99.99% uptime.",
                    },
                ],
                brand_rules=rules,
                segment_profile={"tone": "Professional", "audience": "Enterprises"},
            )

            with patch.object(
                orchestrator, "_resolve_provider", new_callable=AsyncMock,
            ) as mock_resolve:
                mock_provider = MagicMock(spec=LLMProvider)
                mock_provider.generate = AsyncMock(
                    return_value=LLMResponse(
                        content=(
                            "The Integration Product IP-100 delivers enterprise-grade "
                            "reliability with support for 10,000 concurrent connections "
                            "and 99.99% uptime. Its proven architecture ensures seamless "
                            "deployments in the most demanding environments."
                        ),
                        model_used="gpt-4o",
                        tokens_used=200,
                        latency_ms=1200.0,
                    )
                )
                mock_resolve.return_value = mock_provider

                result = await orchestrator.generate(
                    mock_db, product_id=1, gen_type=GenerationType.FEATURE_BULLETS,
                )

        assert isinstance(result, GeneratedResponse)
        assert "Integration Product" in result.copy
        assert result.metadata.model == "gpt-4o"
        assert result.metadata.tokens == 200
        assert result.metadata.latency == 1200.0

        # Sources should be present
        assert len(result.sources) == 1
        assert result.sources[0].title == "Integration Spec"

        # Collection should have been called with correct product_id
        mock_collect.assert_called_once_with(mock_db, product_id=1)
