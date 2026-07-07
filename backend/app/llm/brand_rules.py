"""
Brand rules loader — reads three authoritative markdown files that govern
every content generation: tone guidelines, compliance requirements, and
corporate style rules.

Falls back to sensible defaults when any rule file is missing so the
pipeline never breaks on missing configuration.
"""


import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Defaults used when a rules file cannot be read ──────────────────────────

_DEFAULT_TONE = (
    "Maintain a professional yet approachable tone. "
    "Be confident but not boastful. Speak directly to the reader."
)

_DEFAULT_COMPLIANCE = (
    "All claims must be truthful and substantiated by source documents. "
    "Do not make health, safety, or environmental claims without evidence. "
    "Comply with applicable advertising standards."
)

_DEFAULT_STYLE = (
    "Use active voice. Keep paragraphs short (2-4 sentences). "
    "Use bullet points for lists of features or benefits. "
    "Avoid jargon unless the audience is technical."
)

# ── Expected file names ─────────────────────────────────────────────────────

_RULE_FILES = ("tone.md", "compliance.md", "style.md")

# ── BrandRules dataclass ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class BrandRules:
    """Container for the three brand-governance documents.

    Each field holds the raw markdown text loaded from the corresponding
    rules file (or a built-in default when the file is missing).
    """

    tone: str
    compliance: str
    style: str

    def as_dict(self) -> dict[str, str]:
        """Return rules as a plain dict for serialisation / prompt assembly."""
        return {
            "tone": self.tone,
            "compliance": self.compliance,
            "style": self.style,
        }


# ── Loader ───────────────────────────────────────────────────────────────────


class BrandRulesLoader:
    """Reads brand-governance markdown files from the rules directory.

    Gracefully degrades: if a file is unreadable or doesn't exist the
    corresponding built-in default is used so content generation never
    fails due to missing configuration.
    """

    # Map of rule name → default text.
    _DEFAULT_MAP: dict[str, str] = {
        "tone": _DEFAULT_TONE,
        "compliance": _DEFAULT_COMPLIANCE,
        "style": _DEFAULT_STYLE,
    }

    @staticmethod
    def load_rules(rules_dir: str | Path | None = None) -> BrandRules:
        """Load brand rules from the given directory (or default location).

        Args:
            rules_dir: Path to the directory containing ``tone.md``,
                       ``compliance.md``, and ``style.md``.  When *None*,
                       defaults to ``backend/data/rules/`` relative to the
                       project root.

        Returns:
            A ``BrandRules`` instance populated with the file contents
            (or built-in defaults for any file that could not be read).
        """
        if rules_dir is None:
            rules_dir = Path(__file__).resolve().parent.parent.parent / "data" / "rules"
        else:
            rules_dir = Path(rules_dir)

        logger.debug("Loading brand rules from %s", rules_dir)

        return BrandRules(
            tone=BrandRulesLoader._read_rule(rules_dir, "tone"),
            compliance=BrandRulesLoader._read_rule(rules_dir, "compliance"),
            style=BrandRulesLoader._read_rule(rules_dir, "style"),
        )

    @staticmethod
    def _read_rule(rules_dir: Path, rule_name: str) -> str:
        """Attempt to read *rule_name*.md from *rules_dir*, falling back to default.

        Args:
            rules_dir: Absolute path to the directory holding rule files.
            rule_name: One of 'tone', 'compliance', 'style'.

        Returns:
            The file content (stripped) or the built-in default text.
        """
        file_path = rules_dir / f"{rule_name}.md"
        try:
            content = file_path.read_text(encoding="utf-8").strip()
            if content:
                logger.info("Loaded brand rule '%s' from %s", rule_name, file_path)
                return content
        except FileNotFoundError:
            logger.warning("Brand rule file not found: %s — using default", file_path)
        except OSError as exc:
            logger.error("Failed to read brand rule %s: %s — using default", file_path, exc)

        default = BrandRulesLoader._DEFAULT_MAP[rule_name]
        logger.info("Using built-in default for brand rule '%s'", rule_name)
        return default
