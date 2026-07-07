"""
Brand rules API router — read, update, and preview brand rule markdown.

Mounts under ``/settings/rules`` (prefixed by ``/api/v1`` in main.py) and
manages three markdown files (tone, compliance, style) stored in
``backend/data/rules/``.  An in-memory cache speeds up reads and is
invalidated automatically on update.

Reads are available to any authenticated user (rules are consumed by the
LLM orchestrator); writes require the SUPER_ADMIN role.
"""


import logging
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import RoleDTO
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/rules", tags=["settings"])

# ── Constants ───────────────────────────────────────────────────────────────

_RULES_DIR: Path = Path("data/rules")
"""Directory where brand rule markdown files are stored."""

_VALID_RULE_NAMES: set[str] = {"tone", "compliance", "style"}
"""The three recognised brand rule documents."""

_DEFAULT_RULES: dict[str, str] = {
    "tone": (
        "# Brand Tone of Voice\n\n"
        "## Guidelines\n\n"
        "Use a professional yet approachable tone. "
        "Avoid overly technical jargon unless the target audience "
        "is highly technical. Maintain a consistent brand voice "
        "across all marketing materials.\n\n"
        "## Examples\n\n"
        "- Good: \"Our solution simplifies your workflow in three easy steps.\"\n"
        "- Avoid: \"Our synergistic paradigm leverages cutting-edge innovation.\"\n"
    ),
    "compliance": (
        "# Compliance Rules\n\n"
        "## Mandatory Disclaimers\n\n"
        "All marketing claims must be substantiated. Include necessary "
        "legal disclaimers where required by applicable regulations.\n\n"
        "## Prohibited Language\n\n"
        "- No absolute superlatives without supporting data (e.g., 'best', 'fastest').\n"
        "- No medical or health claims without regulatory approval.\n"
        "- No comparative claims that cannot be verified.\n\n"
        "## Required Elements\n\n"
        "- Product specifications must match the official datasheet.\n"
        "- Pricing information must include currency and any applicable taxes.\n"
        "- Terms and conditions references where appropriate.\n"
    ),
    "style": (
        "# Brand Style Guide\n\n"
        "## Formatting\n\n"
        "- Use sentence case for headings.\n"
        "- Bullet points for feature lists.\n"
        "- Maximum paragraph length: 4 sentences.\n\n"
        "## Vocabulary\n\n"
        "- Preferred terms: 'solution' over 'product', 'customer' over 'user'.\n"
        "- Always spell out acronyms on first use.\n"
        "- Use active voice wherever possible.\n\n"
        "## Numbers & Measurements\n\n"
        "- Use metric units with imperial in parentheses where applicable.\n"
        "- Percentages: use '%' symbol, not 'percent'.\n"
    ),
}
"""Default content for brand rules when no file exists yet."""


# ── In-Memory Cache ─────────────────────────────────────────────────────────


class BrandRulesService:
    """Service for reading, writing, and caching brand rule markdown files.

    Rules are stored as ``{rule_name}.md`` files in ``_RULES_DIR``.  An
    in-memory ``_cache`` dict provides fast reads; updates flush the
    file to disk and invalidate the cached entry for that rule.
    """

    def __init__(self, rules_dir: Path | None = None):
        self._rules_dir: Path = rules_dir or _RULES_DIR
        self._cache: Dict[str, str] = {}
        # Ensure the rules directory exists.
        self._rules_dir.mkdir(parents=True, exist_ok=True)

    # ── Read ────────────────────────────────────────────────────────────────

    def get_rule(self, rule_name: str) -> str:
        """Return the full markdown content for *rule_name*.

        Checks the in-memory cache first; falls back to disk, then to
        the built-in default content.

        Args:
            rule_name: One of ``tone``, ``compliance``, or ``style``.

        Returns:
            The full markdown string.

        Raises:
            ValueError: If *rule_name* is not a valid rule identifier.
        """
        self._validate_rule_name(rule_name)

        # Cache hit
        if rule_name in self._cache:
            return self._cache[rule_name]

        # Disk read
        file_path = self._rule_path(rule_name)
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            self._cache[rule_name] = content
            return content

        # Fallback: write default to disk and cache
        default = _DEFAULT_RULES[rule_name]
        self._write_to_disk(rule_name, default)
        self._cache[rule_name] = default
        return default

    # ── Update ──────────────────────────────────────────────────────────────

    def update_rule(self, rule_name: str, content: str) -> None:
        """Replace a rule's content and invalidate the cache.

        Args:
            rule_name: One of ``tone``, ``compliance``, or ``style``.
            content: The new full markdown content.

        Raises:
            ValueError: If *rule_name* is not a valid rule identifier.
        """
        self._validate_rule_name(rule_name)

        self._write_to_disk(rule_name, content)
        self._cache[rule_name] = content  # update cache with new value

    # ── Preview ─────────────────────────────────────────────────────────────

    def build_preview_prompt(
        self, rule_name: str, proposed_content: str, sample_input: str | None = None
    ) -> str:
        """Build a sample system prompt showing how the rule would be applied.

        This is a dry-run preview — no LLM call is made.  It demonstrates
        how the proposed rule content would appear in the system prompt
        used during content generation.

        Args:
            rule_name: The rule being previewed.
            proposed_content: The proposed new markdown content.
            sample_input: Optional product description for context.

        Returns:
            A formatted string showing the complete prompt structure.
        """
        context = sample_input or (
            "WidgetPro X2000 — a high-performance industrial widget "
            "designed for manufacturing environments. Features include "
            "real-time monitoring, 99.9% uptime, and energy-efficient "
            "operation."
        )

        prompt = (
            f"## System Prompt Preview — {rule_name.upper()} Rule\n\n"
            f"### Rule Content\n"
            f"{proposed_content}\n\n"
            f"---\n\n"
            f"### Product Context\n"
            f"{context}\n\n"
            f"---\n\n"
            f"### Instructions to LLM\n"
            f"Generate marketing copy for the above product, strictly "
            f"following the {rule_name} rule guidelines above. "
            f"All claims must be substantiated. Output format: JSON "
            f"with {{copy, flags, sources, violations}}."
        )
        return prompt

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _rule_path(self, rule_name: str) -> Path:
        """Return the filesystem path for a rule file."""
        return self._rules_dir / f"{rule_name}.md"

    def _write_to_disk(self, rule_name: str, content: str) -> None:
        """Persist rule content to the markdown file on disk."""
        file_path = self._rule_path(rule_name)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        logger.debug("Wrote rule %r to %s", rule_name, file_path)

    @staticmethod
    def _validate_rule_name(rule_name: str) -> None:
        """Raise ValueError if *rule_name* is not a recognised rule."""
        if rule_name not in _VALID_RULE_NAMES:
            raise ValueError(
                f"Invalid rule name: {rule_name!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_RULE_NAMES))}."
            )


# ── Singleton ───────────────────────────────────────────────────────────────

_rules_service = BrandRulesService()


# ── GET /settings/rules/{rule_name} ─────────────────────────────────────────


@router.get(
    "/{rule_name}",
    summary="Get brand rule markdown content",
)
async def get_rule(
    rule_name: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Return the full markdown content of the requested brand rule.

    Available to **any authenticated user** — brand rules are read by the
    LLM orchestrator during content generation, not just by admins.

    Raises:
        HTTPException 404: If *rule_name* is not a valid rule identifier.
    """
    try:
        content = _rules_service.get_rule(rule_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return {"rule_name": rule_name, "content": content}


# ── PUT /settings/rules/{rule_name} ─────────────────────────────────────────


@router.put(
    "/{rule_name}",
    summary="Update brand rule markdown",
)
async def update_rule(
    rule_name: str,
    body: "dict",  # Forward ref — we import locally to avoid circular imports
    current_user: Annotated[User, Depends(require_role(RoleDTO.SUPER_ADMIN))],
) -> dict:
    """Replace the full markdown content of a brand rule.

    **super_admin only.**  The update is persisted to disk immediately
    and the in-memory cache is invalidated so subsequent reads pick up
    the new content.

    Request body:
        ``{"content": "..."}`` — the full markdown text.

    Raises:
        HTTPException 404: If *rule_name* is not a valid rule identifier.
        HTTPException 422: If the ``content`` field is missing or empty.
    """
    # Validate body manually (avoiding pydantic dependency overkill)
    content: str | None = body.get("content") if isinstance(body, dict) else None
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The 'content' field is required and must be a non-empty string.",
        )

    try:
        _rules_service.update_rule(rule_name, content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    logger.info(
        "Super admin id=%d updated rule %r", current_user.id, rule_name
    )
    return {"rule_name": rule_name, "message": "Rule updated successfully."}


# ── POST /settings/rules/{rule_name}/preview ────────────────────────────────


@router.post(
    "/{rule_name}/preview",
    summary="Preview how a rule change affects generation",
)
async def preview_rule_change(
    rule_name: str,
    body: "dict",
    current_user: Annotated[User, Depends(require_role(RoleDTO.SUPER_ADMIN))],
) -> dict:
    """Preview the effect of a proposed rule change on content generation.

    **super_admin only.**  Builds a sample system prompt using the proposed
    rule content alongside a sample product description, showing exactly
    what the LLM would receive.  No actual LLM call is made — this is a
    dry-run prompt builder.

    Request body:
        ``{"content": "...", "sample_input": "..."}`` — proposed rule
        content and optional product context.

    Returns:
        A dict with ``rule_name``, ``current_content``, ``proposed_content``,
        ``sample_prompt``, and ``diff_summary``.

    Raises:
        HTTPException 404: If *rule_name* is not a valid rule identifier.
    """
    content: str | None = body.get("content") if isinstance(body, dict) else None
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The 'content' field is required and must be a non-empty string.",
        )

    sample_input: str | None = body.get("sample_input") if isinstance(body, dict) else None

    try:
        current_content = _rules_service.get_rule(rule_name)
        sample_prompt = _rules_service.build_preview_prompt(
            rule_name, content, sample_input
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    # Build a simple diff summary
    diff_summary = _build_diff_summary(current_content, content)

    return {
        "rule_name": rule_name,
        "current_content": current_content,
        "proposed_content": content,
        "sample_prompt": sample_prompt,
        "diff_summary": diff_summary,
    }


# ── Helpers ─────────────────────────────────────────────────────────────────


def _build_diff_summary(old: str, new: str) -> str:
    """Build a human-readable summary of the differences between two texts.

    Simple line-count comparison — avoids pulling in a full diff library.
    """
    old_lines = old.strip().split("\n")
    new_lines = new.strip().split("\n")
    added = max(0, len(new_lines) - len(old_lines))
    removed = max(0, len(old_lines) - len(new_lines))
    if added == 0 and removed == 0:
        return "Content length unchanged; inline changes detected."
    parts = []
    if removed:
        parts.append(f"{removed} line(s) removed")
    if added:
        parts.append(f"{added} line(s) added")
    return "; ".join(parts) + "." if parts else "No structural changes detected."
