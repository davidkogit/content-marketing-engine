"""
Unit tests for PromptBuilder — verifies that system and user prompts are
correctly assembled from GenerationContext data, including brand rules,
product specs, source documents, and segment profiles.
"""

from __future__ import annotations

import pytest

from app.llm.brand_rules import BrandRules
from app.llm.context_collector import GenerationContext
from app.llm.prompt_builder import PromptBuilder


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def full_context() -> GenerationContext:
    """A fully-populated GenerationContext for prompt building tests."""
    rules = BrandRules(
        tone="Maintain a professional yet approachable tone.",
        compliance="All claims must be substantiated by source documents.",
        style="Use active voice. Keep paragraphs short (2-4 sentences).",
    )
    return GenerationContext(
        product_specs={
            "name": "SuperWidget XYZ-9000",
            "sku": "XYZ-9000",
            "description": "A high-performance widget for professional use.",
            "category": "Electronics",
            "segment": "Tech Enthusiasts",
        },
        source_documents=[
            {
                "title": "Technical Specification Sheet",
                "extracted_text": "The XYZ-9000 features a 5nm processor.",
            },
            {
                "title": "Marketing Brief",
                "extracted_text": "Target audience values speed and battery life.",
            },
        ],
        brand_rules=rules,
        segment_profile={
            "tone": "Enthusiastic but credible",
            "audience": "Tech-savvy professionals aged 25-45",
        },
    )


@pytest.fixture
def minimal_context() -> GenerationContext:
    """A GenerationContext with minimal data (empty product, no docs)."""
    rules = BrandRules(tone="", compliance="", style="")
    return GenerationContext(
        product_specs={"name": "Widget", "sku": "", "description": "", "category": None, "segment": None},
        source_documents=[],
        brand_rules=rules,
        segment_profile={},
    )


@pytest.fixture
def builder() -> PromptBuilder:
    """Return a PromptBuilder instance."""
    return PromptBuilder()


# ── System Prompt ───────────────────────────────────────────────────────────


class TestBuildSystemPrompt:
    """Tests for PromptBuilder.build_system_prompt()."""

    def test_includes_role_assignment(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """The system prompt should start with a role assignment."""
        prompt = builder.build_system_prompt(full_context)
        assert "professional marketing copywriter" in prompt.lower()

    def test_includes_tone_guidelines(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """Tone guidelines from brand rules should appear in the prompt."""
        prompt = builder.build_system_prompt(full_context)
        assert "approachable tone" in prompt

    def test_includes_compliance_requirements(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """Compliance rules should appear in the prompt."""
        prompt = builder.build_system_prompt(full_context)
        assert "substantiated by source documents" in prompt

    def test_includes_style_guide(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """Style rules should appear in the prompt."""
        prompt = builder.build_system_prompt(full_context)
        assert "active voice" in prompt.lower()

    def test_includes_segment_profile(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """The segment tone and audience should appear in the prompt."""
        prompt = builder.build_system_prompt(full_context)
        assert "Tech-savvy professionals" in prompt
        assert "Enthusiastic but credible" in prompt

    def test_omits_segment_when_empty(self, builder: PromptBuilder, minimal_context: GenerationContext) -> None:
        """When segment_profile is empty, no Segment Profile section should appear."""
        prompt = builder.build_system_prompt(minimal_context)
        assert "Segment Profile" not in prompt

    def test_omits_empty_rule_sections(self, builder: PromptBuilder, minimal_context: GenerationContext) -> None:
        """Empty brand rules should not generate their sections."""
        prompt = builder.build_system_prompt(minimal_context)
        assert "Tone Guidelines" not in prompt
        assert "Compliance Requirements" not in prompt
        assert "Style Guide" not in prompt

    def test_system_prompt_is_non_empty(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """Even with full context, the result should be a non-empty string."""
        prompt = builder.build_system_prompt(full_context)
        assert isinstance(prompt, str)
        assert len(prompt) > 50

    def test_system_prompt_returns_string_for_empty(self, builder: PromptBuilder, minimal_context: GenerationContext) -> None:
        """Even minimal context should produce a valid (non-empty) string."""
        prompt = builder.build_system_prompt(minimal_context)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_segment_profile_partial(
        self, builder: PromptBuilder, full_context: GenerationContext,
    ) -> None:
        """Segment with only tone or only audience should still produce output."""
        rules = BrandRules(tone="Friendly", compliance="Honest", style="Short")
        ctx = GenerationContext(
            product_specs={},
            source_documents=[],
            brand_rules=rules,
            segment_profile={"tone": "Casual", "audience": ""},
        )
        prompt = builder.build_system_prompt(ctx)
        assert "Casual" in prompt

    def test_segment_profile_only_audience(
        self, builder: PromptBuilder,
    ) -> None:
        """Segment with only audience (no tone) should still produce output."""
        rules = BrandRules(tone="Friendly", compliance="Honest", style="Short")
        ctx = GenerationContext(
            product_specs={},
            source_documents=[],
            brand_rules=rules,
            segment_profile={"tone": "", "audience": "Young professionals"},
        )
        prompt = builder.build_system_prompt(ctx)
        assert "Young professionals" in prompt


# ── User Prompt ─────────────────────────────────────────────────────────────


class TestBuildUserPrompt:
    """Tests for PromptBuilder.build_user_prompt()."""

    def test_includes_product_name(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """The user prompt should include the product name."""
        prompt = builder.build_user_prompt(full_context, "Write a tagline")
        assert "SuperWidget XYZ-9000" in prompt

    def test_includes_sku(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """The SKU should appear in the prompt."""
        prompt = builder.build_user_prompt(full_context, "Write a tagline")
        assert "XYZ-9000" in prompt

    def test_includes_category(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """The category should appear when set."""
        prompt = builder.build_user_prompt(full_context, "Write a tagline")
        assert "Category: Electronics" in prompt

    def test_omits_category_when_none(
        self, builder: PromptBuilder, minimal_context: GenerationContext,
    ) -> None:
        """A None category should be omitted from the prompt."""
        prompt = builder.build_user_prompt(minimal_context, "Write a tagline")
        assert "Category:" not in prompt

    def test_includes_segment_label(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """The market segment name should appear."""
        prompt = builder.build_user_prompt(full_context, "Write a tagline")
        assert "Market Segment: Tech Enthusiasts" in prompt

    def test_includes_description(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """The product description should appear."""
        prompt = builder.build_user_prompt(full_context, "Write a tagline")
        assert "high-performance widget" in prompt

    def test_includes_source_documents(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """Source documents with text should appear under ## Source Documents."""
        prompt = builder.build_user_prompt(full_context, "Write a tagline")
        assert "## Source Documents" in prompt
        assert "5nm processor" in prompt
        assert "Technical Specification Sheet" in prompt

    def test_omits_source_documents_when_empty(
        self, builder: PromptBuilder, minimal_context: GenerationContext,
    ) -> None:
        """When there are no source documents, the section should be absent."""
        prompt = builder.build_user_prompt(minimal_context, "Write a tagline")
        assert "Source Documents" not in prompt

    def test_omits_source_documents_with_empty_text(
        self, builder: PromptBuilder,
    ) -> None:
        """Documents with empty extracted_text should not produce output."""
        rules = BrandRules(tone="", compliance="", style="")
        ctx = GenerationContext(
            product_specs={"name": "P", "sku": "", "description": "", "category": None, "segment": None},
            source_documents=[{"title": "Empty Doc", "extracted_text": ""}],
            brand_rules=rules,
            segment_profile={},
        )
        prompt = builder.build_user_prompt(ctx, "Do something")
        assert "Source Documents" not in prompt

    def test_includes_instruction(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """The specific generation instruction should appear under ## Task."""
        prompt = builder.build_user_prompt(full_context, "Write a 3-sentence product description")
        assert "## Task" in prompt
        assert "Write a 3-sentence product description" in prompt

    def test_user_prompt_is_non_empty(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """The result should be a non-empty string."""
        prompt = builder.build_user_prompt(full_context, "Any instruction")
        assert isinstance(prompt, str)
        assert len(prompt) > 20

    def test_user_prompt_structure(self, builder: PromptBuilder, full_context: GenerationContext) -> None:
        """Sections should appear in the correct order."""
        prompt = builder.build_user_prompt(full_context, "Do X")
        product_idx = prompt.index("Product:")
        source_idx = prompt.index("## Source Documents")
        task_idx = prompt.index("## Task")
        assert product_idx < source_idx < task_idx


# ── Edge cases ──────────────────────────────────────────────────────────────


class TestPromptBuilderEdgeCases:
    """Edge-case tests for PromptBuilder."""

    def test_instruction_with_special_characters(self, builder: PromptBuilder, minimal_context: GenerationContext) -> None:
        """Instructions with newlines, quotes, or braces should be preserved."""
        instruction = 'Write a description with "\'quotes\'" and {braces}...'
        prompt = builder.build_user_prompt(minimal_context, instruction)
        assert '"\'quotes\'"' in prompt
        assert "{braces}" in prompt

    def test_context_with_long_document_text(self, builder: PromptBuilder) -> None:
        """Long document text should be included without truncation."""
        long_text = "Lorem ipsum " * 100
        rules = BrandRules(tone="", compliance="", style="")
        ctx = GenerationContext(
            product_specs={"name": "P", "sku": "", "description": "", "category": None, "segment": None},
            source_documents=[{"title": "Long Doc", "extracted_text": long_text}],
            brand_rules=rules,
            segment_profile={},
        )
        prompt = builder.build_user_prompt(ctx, "Summarize")
        assert "Lorem ipsum" in prompt
        # Long text should appear intact
        assert long_text in prompt

    def test_default_context_builds_without_errors(self, builder: PromptBuilder) -> None:
        """A completely default GenerationContext should build prompts without errors."""
        ctx = GenerationContext()
        system = builder.build_system_prompt(ctx)
        user = builder.build_user_prompt(ctx, "test")
        assert isinstance(system, str)
        assert isinstance(user, str)
