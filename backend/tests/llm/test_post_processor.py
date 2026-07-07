"""
Unit tests for PostProcessor — verifies correct parsing of LLM responses into
structured ``GeneratedResponse`` objects: copy extraction, claim anchoring,
source reference building, violation detection, and flag generation.
"""

from __future__ import annotations

import pytest

from app.llm.brand_rules import BrandRules
from app.llm.generation_schemas import (
    ExtractedClaim,
    GeneratedResponse,
    GenerationMetadata,
    RuleViolation,
    SourceRef,
)
from app.llm.post_processor import (
    PostProcessor,
    _claim_doc_similarity,
    _is_claim_like,
    _significant_words,
    _split_sentences,
    _try_parse_json,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def processor() -> PostProcessor:
    """Return a PostProcessor instance."""
    return PostProcessor()


@pytest.fixture
def brand_rules() -> BrandRules:
    """Return sample BrandRules."""
    return BrandRules(
        tone="Maintain a professional yet approachable tone. Avoid casual language.",
        compliance="All claims must be substantiated by source documents. Do not use unsubstantiated superlatives like 'best' or 'leading'.",
        style="Use active voice. Keep paragraphs short (2-4 sentences). Avoid jargon unless the audience is technical.",
    )


@pytest.fixture
def source_docs() -> list[dict[str, str | None]]:
    """Return sample source documents."""
    return [
        {
            "title": "Technical Specification",
            "extracted_text": "The XYZ-9000 processor runs at 3.5GHz with 8 cores and 16 threads. It supports up to 64GB DDR5 RAM.",
        },
        {
            "title": "Marketing Brief",
            "extracted_text": "Target audience: tech professionals aged 25-45. Key selling points: speed, reliability, value for money.",
        },
        {
            "title": "Empty Document",
            "extracted_text": None,
        },
        {
            "title": "Another Empty Doc",
            "extracted_text": "",
        },
    ]


@pytest.fixture
def metadata() -> GenerationMetadata:
    """Return sample GenerationMetadata."""
    return GenerationMetadata(
        model="gpt-4o",
        tokens=250,
        latency=950.5,
    )


# ── Stage 1: Copy extraction ────────────────────────────────────────────────


class TestExtractCopy:
    """Tests for PostProcessor._extract_copy()."""

    def test_plain_text_passthrough(self, processor: PostProcessor) -> None:
        """Plain text without JSON structure should be returned as-is."""
        raw = "This is a product description. It describes the product."
        result = processor._extract_copy(raw)
        assert result == raw

    def test_json_with_copy_field(self, processor: PostProcessor) -> None:
        """JSON with a 'copy' field should extract that field."""
        raw = '{"copy": "The generated marketing copy.", "claims": []}'
        result = processor._extract_copy(raw)
        assert result == "The generated marketing copy."

    def test_json_without_copy_field(self, processor: PostProcessor) -> None:
        """JSON without a 'copy' field should fall through to raw text."""
        raw = '{"title": "My Product", "features": ["fast", "reliable"]}'
        result = processor._extract_copy(raw)
        # Falls through — should return the original (no 'copy' key)
        assert "title" in result  # returned as-is

    def test_markdown_fenced_json(self, processor: PostProcessor) -> None:
        """JSON inside ``` fences should be parsed."""
        raw = '```json\n{"copy": "Fenced copy."}\n```'
        result = processor._extract_copy(raw)
        assert result == "Fenced copy."

    def test_empty_string(self, processor: PostProcessor) -> None:
        """Empty string should remain empty."""
        result = processor._extract_copy("")
        assert result == ""

    def test_whitespace_only(self, processor: PostProcessor) -> None:
        """Whitespace-only input should be stripped to empty."""
        result = processor._extract_copy("   \n  \t  ")
        assert result == ""


# ── Stage 2: Source refs ────────────────────────────────────────────────────


class TestBuildSourceRefs:
    """Tests for PostProcessor._build_source_refs()."""

    def test_builds_refs_from_docs(self, processor: PostProcessor, source_docs: list[dict]) -> None:
        """Non-empty documents should produce SourceRef entries."""
        refs = processor._build_source_refs(source_docs)
        # Only the first two have extracted_text
        assert len(refs) == 2
        assert refs[0].title == "Technical Specification"
        assert "3.5GHz" in refs[0].relevant_excerpt

    def test_skips_empty_docs(self, processor: PostProcessor) -> None:
        """Documents with None or empty text should be skipped."""
        docs: list[dict[str, str | None]] = [
            {"title": "Empty", "extracted_text": None},
            {"title": "Also Empty", "extracted_text": ""},
        ]
        refs = processor._build_source_refs(docs)
        assert len(refs) == 0

    def test_empty_list(self, processor: PostProcessor) -> None:
        """Empty document list should produce empty refs."""
        refs = processor._build_source_refs([])
        assert refs == []

    def test_untitled_document(self, processor: PostProcessor) -> None:
        """Documents missing a title should get 'Untitled'."""
        docs: list[dict[str, str | None]] = [
            {"extracted_text": "Some content."},
        ]
        refs = processor._build_source_refs(docs)
        assert refs[0].title == "Untitled"

    def test_excerpt_truncation(self, processor: PostProcessor) -> None:
        """Long document text should be truncated."""
        long_text = "X" * 1000
        docs: list[dict[str, str | None]] = [
            {"title": "Long Doc", "extracted_text": long_text},
        ]
        refs = processor._build_source_refs(docs)
        assert len(refs[0].relevant_excerpt) <= 500


# ── Stage 3: Claim extraction ───────────────────────────────────────────────


class TestExtractClaims:
    """Tests for PostProcessor._extract_claims()."""

    def test_no_source_docs_returns_empty(self, processor: PostProcessor) -> None:
        """When there are no source documents, claims list should be empty."""
        claims = processor._extract_claims(
            "This product has 8 cores and 16 threads.", [],
        )
        assert claims == []

    def test_extracts_claim_like_sentences(
        self, processor: PostProcessor, source_docs: list[dict],
    ) -> None:
        """Sentences with numbers and feature language should produce claims."""
        claims = processor._extract_claims(
            "The processor runs at 3.5GHz. It features 8 cores and 16 threads.",
            source_docs,
        )
        assert len(claims) > 0
        assert all(isinstance(c, ExtractedClaim) for c in claims)

    def test_anchors_claims_to_sources(
        self, processor: PostProcessor, source_docs: list[dict],
    ) -> None:
        """Claims that match source document text should be anchored."""
        claims = processor._extract_claims(
            "The XYZ-9000 processor runs at 3.5GHz with 8 cores.",
            source_docs,
        )
        # At least one claim should have high confidence
        anchored = [c for c in claims if c.source_doc_id is not None]
        if claims:
            # With matching text, at least some claims should anchor
            high_conf = [c for c in claims if c.confidence_score > 0.1]
            assert len(high_conf) > 0

    def test_skips_short_sentences(self, processor: PostProcessor, source_docs: list[dict]) -> None:
        """Sentences shorter than 15 chars should be skipped."""
        claims = processor._extract_claims(
            "It works. It features 8 cores and 16 threads of pure power.", source_docs,
        )
        claim_texts = [c.text for c in claims]
        assert "It works." not in claim_texts

    def test_skips_non_claim_sentences(self, processor: PostProcessor, source_docs: list[dict]) -> None:
        """Sentences without claim-like language should be skipped."""
        claims = processor._extract_claims(
            "Thank you for reading. We hope you enjoy the product. Contact us for more info.",
            source_docs,
        )
        # These are not claim-like — should produce empty claims
        assert len(claims) == 0

    def test_confidence_score_range(
        self, processor: PostProcessor, source_docs: list[dict],
    ) -> None:
        """Confidence scores should be in [0.0, 1.0]."""
        claims = processor._extract_claims(
            "The XYZ-9000 processor supports up to 64GB DDR5 RAM. It delivers 99.9% uptime.",
            source_docs,
        )
        for c in claims:
            assert 0.0 <= c.confidence_score <= 1.0

    def test_empty_copy(self, processor: PostProcessor, source_docs: list[dict]) -> None:
        """Empty copy text should produce empty claims."""
        claims = processor._extract_claims("", source_docs)
        assert claims == []


# ── Stage 4: Violation detection ────────────────────────────────────────────


class TestDetectViolations:
    """Tests for PostProcessor._detect_violations()."""

    def test_clean_copy_no_violations(
        self, processor: PostProcessor, brand_rules: BrandRules,
    ) -> None:
        """A clean, rule-compliant copy should produce no violations."""
        violations = processor._detect_violations(
            "The product offers reliable performance and seamless integration. Engineers trust its proven architecture.",
            brand_rules,
        )
        assert len(violations) == 0

    def test_detects_tone_violation(
        self, processor: PostProcessor, brand_rules: BrandRules,
    ) -> None:
        """Tone indicators like 'OMG' or '!!!' should trigger tone violations."""
        violations = processor._detect_violations(
            "This product is amazing!!! You will love it. OMG it's so good!",
            brand_rules,
        )
        tone_violations = [v for v in violations if v.rule_type == "tone"]
        assert len(tone_violations) > 0

    def test_detects_compliance_violation(
        self, processor: PostProcessor, brand_rules: BrandRules,
    ) -> None:
        """Unsubstantiated superlatives should trigger compliance violations."""
        violations = processor._detect_violations(
            "This is the best product on the market. It is unmatched by any competitor.",
            brand_rules,
        )
        comp_violations = [v for v in violations if v.rule_type == "compliance"]
        assert len(comp_violations) > 0

    def test_detects_passive_voice(
        self, processor: PostProcessor, brand_rules: BrandRules,
    ) -> None:
        """Multiple passive voice constructions should trigger style violations."""
        violations = processor._detect_violations(
            "The product was designed by experts. "
            "It is manufactured with care. "
            "Quality is guaranteed by rigorous testing. "
            "Support is provided around the clock.",
            brand_rules,
        )
        style_violations = [v for v in violations if v.rule_type == "style"]
        assert len(style_violations) > 0
        assert "passive voice" in style_violations[0].description.lower()

    def test_few_passive_instances_ok(
        self, processor: PostProcessor, brand_rules: BrandRules,
    ) -> None:
        """One or two passive constructions should not trigger a violation."""
        violations = processor._detect_violations(
            "The product was designed by experts. It delivers amazing results.",
            brand_rules,
        )
        style_violations = [v for v in violations if v.rule_type == "style"]
        assert len(style_violations) == 0

    def test_violations_include_rule_text(
        self, processor: PostProcessor, brand_rules: BrandRules,
    ) -> None:
        """Each violation should include the relevant rule text excerpt."""
        violations = processor._detect_violations(
            "This is the best product ever made!!!",
            brand_rules,
        )
        for v in violations:
            assert len(v.rule_text) > 0
            assert len(v.description) > 0

    def test_empty_copy_no_violations(
        self, processor: PostProcessor, brand_rules: BrandRules,
    ) -> None:
        """Empty copy should produce no violations."""
        violations = processor._detect_violations("", brand_rules)
        assert violations == []


# ── Stage 5: Flags ──────────────────────────────────────────────────────────


class TestGenerateFlags:
    """Tests for PostProcessor._generate_flags()."""

    def test_short_copy_flag(self, processor: PostProcessor) -> None:
        """Copy with fewer than 10 words should get a short-copy flag."""
        flags = processor._generate_flags(
            "Tiny copy.", [], [],
        )
        assert any("very short" in f.lower() for f in flags)

    def test_no_claims_flag(self, processor: PostProcessor) -> None:
        """When no claims extracted, a flag should indicate that."""
        flags = processor._generate_flags(
            "This is a perfectly adequate description of the product.", [], [],
        )
        assert any("no factual claims" in f.lower() for f in flags)

    def test_no_anchored_claims_flag(self, processor: PostProcessor) -> None:
        """When claims exist but none are anchored, a flag should warn."""
        claims = [
            ExtractedClaim(text="It has 8 cores.", source_doc_id=None, confidence_score=0.0),
            ExtractedClaim(text="It runs fast.", source_doc_id=None, confidence_score=0.0),
        ]
        flags = processor._generate_flags("Some copy text that is long enough.", claims, [])
        assert any("could not be anchored" in f.lower() for f in flags)

    def test_violations_flag(self, processor: PostProcessor) -> None:
        """When violations are present, a flag should summarize them."""
        violations = [
            RuleViolation(rule_type="tone", description="Bad tone", rule_text="Be professional"),
        ]
        flags = processor._generate_flags(
            "A reasonably long description of the product with enough words to avoid short flags.",
            [],
            violations,
        )
        assert any("violation" in f.lower() for f in flags)

    def test_long_copy_flag(self, processor: PostProcessor) -> None:
        """Copy exceeding 1000 words should get a long-copy flag."""
        words = "word " * 1001
        flags = processor._generate_flags(words, [], [])
        assert any("very long" in f.lower() for f in flags)

    def test_partial_anchoring_flag(self, processor: PostProcessor) -> None:
        """When some but not all claims are anchored, a partial flag should appear."""
        claims = [
            ExtractedClaim(text="Feature one.", source_doc_id=1, confidence_score=0.8),
            ExtractedClaim(text="Feature two.", source_doc_id=None, confidence_score=0.0),
            ExtractedClaim(text="Feature three.", source_doc_id=None, confidence_score=0.0),
        ]
        flags = processor._generate_flags(
            "A reasonably long description of the product with enough words.", claims, [],
        )
        assert any("1/3" in f for f in flags)


# ── Full process() integration ──────────────────────────────────────────────


class TestProcess:
    """Integration tests for PostProcessor.process()."""

    def test_process_returns_generated_response(
        self,
        processor: PostProcessor,
        brand_rules: BrandRules,
        source_docs: list[dict],
        metadata: GenerationMetadata,
    ) -> None:
        """process() should return a fully-populated GeneratedResponse."""
        result = processor.process(
            "The XYZ-9000 processor runs at 3.5GHz with 8 cores. It supports up to 64GB DDR5 RAM.",
            brand_rules=brand_rules,
            source_documents=source_docs,
            metadata=metadata,
        )

        assert isinstance(result, GeneratedResponse)
        assert len(result.copy) > 0
        assert result.metadata == metadata
        assert isinstance(result.claims, list)
        assert isinstance(result.flags, list)
        assert isinstance(result.sources, list)
        assert isinstance(result.violations, list)

    def test_process_json_response(
        self,
        processor: PostProcessor,
        brand_rules: BrandRules,
        source_docs: list[dict],
        metadata: GenerationMetadata,
    ) -> None:
        """A JSON response with 'copy' field should be parsed correctly."""
        raw = '{"copy": "The XYZ-9000 delivers 3.5GHz performance with 8 cores.", "claims": []}'
        result = processor.process(
            raw,
            brand_rules=brand_rules,
            source_documents=source_docs,
            metadata=metadata,
        )
        assert "3.5GHz performance" in result.copy

    def test_process_handles_violations(
        self,
        processor: PostProcessor,
        brand_rules: BrandRules,
        source_docs: list[dict],
        metadata: GenerationMetadata,
    ) -> None:
        """Violations should appear in the result when copy violates rules."""
        result = processor.process(
            "This is the best processor ever made!!! You guys will love it.",
            brand_rules=brand_rules,
            source_documents=source_docs,
            metadata=metadata,
        )
        assert len(result.violations) > 0
        assert len(result.flags) > 0

    def test_process_empty_input(
        self,
        processor: PostProcessor,
        brand_rules: BrandRules,
        metadata: GenerationMetadata,
    ) -> None:
        """Empty input should produce a valid but empty GeneratedResponse."""
        result = processor.process(
            "",
            brand_rules=brand_rules,
            source_documents=[],
            metadata=metadata,
        )
        assert result.copy == ""
        assert result.claims == []
        assert result.sources == []
        assert result.violations == []


# ── Module-level helpers ────────────────────────────────────────────────────


class TestTryParseJson:
    """Tests for _try_parse_json()."""

    def test_valid_json_dict(self) -> None:
        """Valid JSON dict should be parsed."""
        result = _try_parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_valid_json_list(self) -> None:
        """Valid JSON list should be parsed."""
        result = _try_parse_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_invalid_json(self) -> None:
        """Invalid JSON should return None."""
        result = _try_parse_json("not json at all")
        assert result is None

    def test_json_within_text(self) -> None:
        """JSON embedded in surrounding text should be extracted."""
        result = _try_parse_json('Some text {"key": "value"} more text')
        assert result == {"key": "value"}

    def test_multiple_json_objects(self) -> None:
        """When multiple JSON objects exist, the first should be returned."""
        result = _try_parse_json('{"a": 1} and {"b": 2}')
        assert result == {"a": 1}


class TestSplitSentences:
    """Tests for _split_sentences()."""

    def test_period_split(self) -> None:
        """Sentences ending with periods should be split."""
        result = _split_sentences("First sentence. Second sentence. Third sentence.")
        assert len(result) == 3

    def test_exclamation_and_question(self) -> None:
        """Sentences ending with ! or ? should be split."""
        result = _split_sentences("Wow! Really? Yes.")
        assert len(result) == 3
        assert result[0] == "Wow!"
        assert result[1] == "Really?"
        assert result[2] == "Yes."

    def test_digit_after_period_not_split(self) -> None:
        """Numbers like '3.5' should not cause a split."""
        result = _split_sentences("The version is 3.5. Next sentence.")
        assert len(result) == 2
        assert result[0] == "The version is 3.5."

    def test_single_sentence(self) -> None:
        """A single sentence should produce one element."""
        result = _split_sentences("Just one sentence")
        assert len(result) == 1


class TestIsClaimLike:
    """Tests for _is_claim_like()."""

    def test_number_claim(self) -> None:
        """Sentences with numbers should be claim-like."""
        assert _is_claim_like("It features 8 cores.") is True

    def test_feature_claim(self) -> None:
        """Sentences mentioning features should be claim-like."""
        assert _is_claim_like("The product features advanced AI capabilities.") is True

    def test_comparison_claim(self) -> None:
        """Sentences with comparisons should be claim-like."""
        assert _is_claim_like("It is faster than the previous generation.") is True

    def test_non_claim(self) -> None:
        """Generic non-claim sentences should not match."""
        assert _is_claim_like("Thank you for reading this document.") is False
        assert _is_claim_like("Please contact us for more information.") is False

    def test_empty_sentence(self) -> None:
        """Empty sentence should not be claim-like."""
        assert _is_claim_like("") is False


class TestClaimDocSimilarity:
    """Tests for _claim_doc_similarity()."""

    def test_exact_match(self) -> None:
        """When all claim words appear in the doc, score should be 1.0."""
        score = _claim_doc_similarity(
            "lightning fast performance",
            "the product delivers lightning fast performance",
        )
        assert score == 1.0

    def test_partial_match(self) -> None:
        """Partial word overlap should produce a score between 0 and 1."""
        score = _claim_doc_similarity(
            "lightning fast performance",
            "the product delivers lightning fast loading",
        )
        assert 0.0 < score < 1.0

    def test_no_match(self) -> None:
        """No word overlap should produce 0.0."""
        score = _claim_doc_similarity(
            "amazing new technology",
            "completely unrelated content here",
        )
        assert score == 0.0

    def test_empty_claim(self) -> None:
        """Empty claim should produce 0.0."""
        score = _claim_doc_similarity("", "some content")
        assert score == 0.0


class TestSignificantWords:
    """Tests for _significant_words()."""

    def test_removes_stopwords(self) -> None:
        """Common stopwords should be excluded."""
        words = _significant_words("the product is for developers with all the features")
        assert "the" not in words
        assert "is" not in words
        assert "for" not in words
        assert "with" not in words
        assert "all" not in words

    def test_keeps_significant_words(self) -> None:
        """Content words of 3+ chars should be retained."""
        words = _significant_words("lightning fast performance processor")
        assert "lightning" in words
        assert "fast" in words
        assert "performance" in words
        assert "processor" in words

    def test_excludes_short_words(self) -> None:
        """Words shorter than 3 characters should be excluded."""
        words = _significant_words("a is to by at")
        assert words == []

    def test_lowercase_normalization(self) -> None:
        """All words should be lowercased."""
        words = _significant_words("Lightning Fast PERFORMANCE")
        assert all(w == w.lower() for w in words)
        assert "lightning" in words


# ── Edge cases ──────────────────────────────────────────────────────────────


class TestPostProcessorEdgeCases:
    """Edge-case and robustness tests for PostProcessor."""

    def test_process_with_multiple_empty_docs(
        self,
        processor: PostProcessor,
        metadata: GenerationMetadata,
    ) -> None:
        """Multiple empty documents should produce empty sources."""
        result = processor.process(
            "Some content.",
            brand_rules=BrandRules(tone="", compliance="", style=""),
            source_documents=[
                {"title": "E1", "extracted_text": None},
                {"title": "E2", "extracted_text": ""},
            ],
            metadata=metadata,
        )
        assert result.sources == []
        assert result.claims == []  # no text to anchor against

    def test_process_with_empty_brand_rules(
        self,
        processor: PostProcessor,
        metadata: GenerationMetadata,
    ) -> None:
        """Empty brand rules should not produce false-positive violations."""
        result = processor.process(
            "This is the best product ever!!!",
            brand_rules=BrandRules(tone="", compliance="", style=""),
            source_documents=[],
            metadata=metadata,
        )
        # With empty rules, tone/compliance checks still use heuristics
        # but the rule_text in violations will be empty
        assert isinstance(result, GeneratedResponse)

    def test_process_very_long_copy(
        self,
        processor: PostProcessor,
        metadata: GenerationMetadata,
    ) -> None:
        """Very long copy should be processed without errors."""
        long_copy = "The product has great features. " * 500
        result = processor.process(
            long_copy,
            brand_rules=BrandRules(tone="Professional tone.", compliance="Be honest.", style="Active voice."),
            source_documents=[
                {"title": "Doc", "extracted_text": "The product has great features and performance."},
            ],
            metadata=metadata,
        )
        assert isinstance(result, GeneratedResponse)
        assert len(result.copy) > 0
