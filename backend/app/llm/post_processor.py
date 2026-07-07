"""
Post-processor — parses raw LLM responses into structured ``GeneratedResponse``
objects with claim extraction, source anchoring, rule-violation detection, and
informational flags.

Works with both structured (JSON-like) and free-form LLM output.
"""


import json
import logging
import re

from app.llm.brand_rules import BrandRules
from app.llm.generation_schemas import (
    ExtractedClaim,
    GeneratedResponse,
    GenerationMetadata,
    RuleViolation,
    SourceRef,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# Patterns that signal the LLM returned structured JSON.
_JSON_PATTERN = re.compile(r"\{[\s\S]*\}", re.MULTILINE)

# Keywords that indicate a claim may be unsubstantiated.
_UNSUBSTANTIATED_INDICATORS = {
    "best", "leading", "top", "number one", "#1", "unmatched",
    "unrivaled", "revolutionary", "world-class", "industry-leading",
}

# Phrases that suggest tone violations (too casual / overly excited).
_TONE_VIOLATION_INDICATORS = {
    "!!!", "OMG", "LOL", "you guys", "ain't", "super duper",
}

# Regex for passive voice detection (simplified heuristic).
_PASSIVE_PATTERN = re.compile(
    r"\b(?:is|are|was|were|be|been|being)\s+\w+ed\b", re.IGNORECASE
)


# ── PostProcessor ────────────────────────────────────────────────────────────


class PostProcessor:
    """Parses raw LLM output and returns a structured ``GeneratedResponse``.

    Performs three stages:
    1. **Parsing** — extracts the main copy from the LLM response.
    2. **Claim anchoring** — cross-references claims with source documents.
    3. **Violation detection** — checks generated copy against brand rules.

    Usage::

        processor = PostProcessor()
        result = processor.process(
            raw_response="...",
            brand_rules=BrandRules(...),
            source_documents=[...],
            metadata=GenerationMetadata(...),
        )
    """

    # ── Public API ───────────────────────────────────────────────────────

    def process(
        self,
        raw_response: str,
        *,
        brand_rules: BrandRules,
        source_documents: list[dict[str, str | None]],
        metadata: GenerationMetadata,
    ) -> GeneratedResponse:
        """Process a raw LLM response into a structured ``GeneratedResponse``.

        Args:
            raw_response: The full text returned by the LLM.
            brand_rules: Brand-governance rules to check against.
            source_documents: Source documents available for claim anchoring.
            metadata: Generation metadata (model, tokens, latency).

        Returns:
            A fully-populated ``GeneratedResponse``.
        """
        # 1. Extract the main copy
        copy_text = self._extract_copy(raw_response)

        # 2. Build source refs from available documents
        sources = self._build_source_refs(source_documents)

        # 3. Extract and anchor claims
        claims = self._extract_claims(copy_text, source_documents)

        # 4. Detect brand-rule violations
        violations = self._detect_violations(copy_text, brand_rules)

        # 5. Generate informational flags
        flags = self._generate_flags(copy_text, claims, violations)

        return GeneratedResponse(
            copy=copy_text,
            claims=claims,
            flags=flags,
            sources=sources,
            violations=violations,
            metadata=metadata,
        )

    # ── Stage 1: Copy extraction ─────────────────────────────────────────

    @staticmethod
    def _extract_copy(raw_response: str) -> str:
        """Extract the main copy from the raw LLM response.

        If the LLM returned structured JSON with a ``copy`` field, use that.
        Otherwise, return the raw text stripped of obvious JSON wrappers.
        """
        # Attempt JSON parse
        parsed = _try_parse_json(raw_response)
        if parsed is not None:
            # Prefer explicit 'copy' field
            if isinstance(parsed, dict) and isinstance(parsed.get("copy"), str):
                logger.debug("Extracted copy from structured JSON response.")
                return parsed["copy"].strip()
            # If JSON but no 'copy' field, fall through to raw text

        # Remove surrounding ``` fences if present
        text = raw_response.strip()
        if text.startswith("```") and text.endswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if len(lines) > 2 else lines)

        return text.strip()

    # ── Stage 2: Source refs ─────────────────────────────────────────────

    @staticmethod
    def _build_source_refs(
        source_documents: list[dict[str, str | None]],
    ) -> list[SourceRef]:
        """Convert source document dicts into ``SourceRef`` objects.

        Each document contributes one ``SourceRef``.  Documents with no
        text are skipped.
        """
        refs: list[SourceRef] = []
        for doc in source_documents:
            title = doc.get("title", "Untitled") or "Untitled"
            text = (doc.get("extracted_text") or "").strip()
            if not text:
                continue
            refs.append(
                SourceRef(
                    doc_id=0,  # no ORM id available in context dicts
                    title=title,
                    relevant_excerpt=text[:500],  # keep reasonable
                )
            )
        return refs

    # ── Stage 3: Claim extraction & anchoring ────────────────────────────

    @staticmethod
    def _extract_claims(
        copy_text: str,
        source_documents: list[dict[str, str | None]],
    ) -> list[ExtractedClaim]:
        """Extract factual claims from the generated copy and anchor them.

        Splits copy into sentences and checks each against source document
        text for keyword overlap.  Only sentences that look like factual
        claims (containing measurable statements or product attributes)
        are included.

        Args:
            copy_text: The generated marketing copy.
            source_documents: Available source documents for anchoring.

        Returns:
            A list of ``ExtractedClaim`` objects with anchoring info.
        """
        if not copy_text or not source_documents:
            return []

        sentences = _split_sentences(copy_text)
        claims: list[ExtractedClaim] = []

        for sentence in sentences:
            s = sentence.strip()
            if len(s) < 15 or not _is_claim_like(s):
                continue

            # Find best-matching source document
            best_doc_id: int | None = None
            best_score: float = 0.0
            best_excerpt: str = ""

            for i, doc in enumerate(source_documents):
                doc_id_val = i + 1  # synthetic id from index
                doc_text = (doc.get("extracted_text") or "").lower()
                if not doc_text:
                    continue
                score = _claim_doc_similarity(s.lower(), doc_text)
                if score > best_score:
                    best_score = score
                    best_doc_id = doc_id_val

            claims.append(
                ExtractedClaim(
                    text=s,
                    source_doc_id=best_doc_id if best_score > 0.15 else None,
                    confidence_score=round(best_score, 2),
                )
            )

        return claims

    # ── Stage 4: Violation detection ─────────────────────────────────────

    @staticmethod
    def _detect_violations(
        copy_text: str,
        brand_rules: BrandRules,
    ) -> list[RuleViolation]:
        """Detect brand-rule violations in the generated copy.

        Checks against tone, compliance, and style rules using both
        heuristic pattern matching and keyword scanning.

        Args:
            copy_text: The generated copy to check.
            brand_rules: The brand rules to enforce.

        Returns:
            A list of ``RuleViolation`` objects (empty if compliant).
        """
        violations: list[RuleViolation] = []

        # ── Tone violations ──────────────────────────────────────────────
        lower = copy_text.lower()
        for indicator in _TONE_VIOLATION_INDICATORS:
            if indicator.lower() in lower:
                violations.append(
                    RuleViolation(
                        rule_type="tone",
                        description=f"Potentially inappropriate tone: found '{indicator}'",
                        rule_text=brand_rules.tone[:300],
                    )
                )
                break  # one tone violation flag is enough

        # ── Compliance: unsubstantiated superlatives ─────────────────────
        for indicator in _UNSUBSTANTIATED_INDICATORS:
            if indicator in lower:
                violations.append(
                    RuleViolation(
                        rule_type="compliance",
                        description=f"Unsubstantiated claim indicator: '{indicator}'. Ensure claim is backed by a source document.",
                        rule_text=brand_rules.compliance[:300],
                    )
                )
                break

        # ── Style: passive voice ─────────────────────────────────────────
        passive_hits = _PASSIVE_PATTERN.findall(copy_text)
        if len(passive_hits) >= 3:
            # Collapse duplicates for the description
            unique = sorted(set(h.lower() for h in passive_hits))
            sample = ", ".join(unique[:3])
            violations.append(
                RuleViolation(
                    rule_type="style",
                    description=f"Passive voice detected ({len(passive_hits)} instances: {sample}...). Consider using active voice.",
                    rule_text=brand_rules.style[:300],
                )
            )

        return violations

    # ── Stage 5: Flags ───────────────────────────────────────────────────

    @staticmethod
    def _generate_flags(
        copy_text: str,
        claims: list[ExtractedClaim],
        violations: list[RuleViolation],
    ) -> list[str]:
        """Generate informational flags about the generated content.

        Flags are non-critical observations that help the user understand
        the quality and completeness of the generation.

        Args:
            copy_text: The generated copy.
            claims: Extracted and anchored claims.
            violations: Detected rule violations.

        Returns:
            A list of human-readable flag strings.
        """
        flags: list[str] = []

        # Word count flag
        word_count = len(copy_text.split())
        if word_count < 10:
            flags.append("Generated copy is very short (fewer than 10 words).")
        elif word_count > 1000:
            flags.append("Generated copy is very long (more than 1000 words).")

        # Claim anchoring coverage
        if claims:
            anchored = sum(1 for c in claims if c.source_doc_id is not None)
            if anchored == 0 and len(claims) > 0:
                flags.append(
                    f"No claims could be anchored to source documents "
                    f"({len(claims)} claims extracted)."
                )
            elif anchored < len(claims):
                flags.append(
                    f"{anchored}/{len(claims)} claims anchored to source documents."
                )
        else:
            flags.append("No factual claims were extracted from the generated copy.")

        # Violations summary
        if violations:
            flags.append(f"{len(violations)} brand-rule violation(s) detected. Review recommended.")

        return flags


# ── Module-level helpers ─────────────────────────────────────────────────────-


def _try_parse_json(text: str) -> dict | list | str | None:
    """Attempt to parse *text* as JSON, returning the parsed value or None."""
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, TypeError):
        pass
    # Try extracting a JSON block from the text
    match = _JSON_PATTERN.search(text)
    if match:
        try:
            return json.loads(match.group(0))  # type: ignore[no-any-return]
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _split_sentences(text: str) -> list[str]:
    """Split *text* into sentences using a simple regex.

    Handles basic sentence terminators: ``.``, ``!``, ``?`` followed by
    whitespace or end-of-string.
    """
    # Regex: split on .!? followed by space/end, but not on digits (e.g., "3.5")
    parts = re.split(r"(?<!\d)(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _is_claim_like(sentence: str) -> bool:
    """Heuristic: does this sentence look like a factual product claim?

    Looks for measurable language, numbers, percentages, feature language,
    or comparison indicators.
    """
    lower = sentence.lower()
    claim_patterns = [
        r"\d+%?",                # numbers / percentages
        r"\bfeatures?\b",        # features / feature
        r"\b(?:provides?|offers?|delivers?|includes?)\b",
        r"\b(?:capable|ability|performance)\b",
        r"\b(?:faster|better|lighter|stronger|more|less)\b",
        r"\b(?:than|compared to|versus|vs\.?)\b",
        r"\b(?:certified|rated|tested|proven)\b",
    ]
    return any(re.search(p, lower) for p in claim_patterns)


def _claim_doc_similarity(claim_lower: str, doc_lower: str) -> float:
    """Compute a simple overlap score between a claim and a source document.

    Returns a value between 0.0 (no match) and 1.0 (perfect match).  Uses
    keyword overlap based on the claim's significant words.

    Args:
        claim_lower: Lowercased claim text.
        doc_lower: Lowercased document text.

    Returns:
        Similarity score in [0.0, 1.0].
    """
    claim_words = set(_significant_words(claim_lower))
    if not claim_words:
        return 0.0

    matches = sum(1 for w in claim_words if w in doc_lower)
    return matches / len(claim_words)


def _significant_words(text: str) -> list[str]:
    """Extract significant (non-stopword) words from *text*.

    Returns a list of lowercased words of 3+ characters, excluding
    common English stop words.
    """
    stopwords = {
        "the", "and", "for", "that", "this", "with", "from", "are",
        "was", "its", "not", "but", "has", "had", "have", "you",
        "can", "all", "will", "just", "about", "into", "over", "after",
        "than", "then", "also", "very", "been", "each", "more", "some",
        "such", "only", "other", "when", "where", "which", "what",
    }
    words = re.findall(r"\w+", text.lower())
    return [w for w in words if len(w) >= 3 and w not in stopwords]
