"""
URL content fetching service with retry, rate-limit awareness, and HTML-to-text conversion.

Provides URLFetcher with async fetch(url) → FetchedContent | FetchError. Handles
timeouts, connection errors, and non-200 responses gracefully — never throws.

Implements exponential backoff with jitter for 429/503 responses and respects
the Retry-After header. HTML is parsed to plain text using Python's built-in
html.parser, stripping <script>, <style>, and <noscript> elements.
"""


import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_TIMEOUT: float = 30.0
"""Default request timeout in seconds."""

DEFAULT_USER_AGENT: str = (
    "ContentMarketingEngine/0.1 (+https://github.com/davidkogit/content-marketing-engine)"
)
"""Default User-Agent header sent with requests."""

MAX_RETRIES: int = 3
"""Maximum number of retry attempts for transient / rate-limit errors."""

BASE_BACKOFF: float = 1.0
"""Base backoff delay in seconds for exponential backoff calculation."""

MAX_BACKOFF: float = 30.0
"""Upper cap on computed backoff delay in seconds."""

_MAX_RESPONSE_BYTES: int = 10 * 1024 * 1024  # 10 MiB
"""Maximum response body size to read (safety limit)."""

# SSRF protection — only permit http and https schemes.
_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

# HTTP status codes that trigger a retry.
_RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 503})

# ══════════════════════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════════════════════


class FetchedContent(BaseModel):
    """Successfully fetched and parsed web page content.

    Attributes:
        url: The original request URL (after redirects, if any).
        status_code: The final HTTP status code.
        content_type: The ``Content-Type`` response header value.
        title: The page title extracted from the ``<title>`` tag.
        raw_text: The page body converted to plain text with scripts/styles removed.
    """

    url: str
    status_code: int
    content_type: str
    title: str
    raw_text: str


class FetchError(BaseModel):
    """Structured error from a failed fetch operation.

    The service **never** raises exceptions from :meth:`URLFetcher.fetch` —
    consumers always receive either a :class:`FetchedContent` or a
    :class:`FetchError` instance.

    Attributes:
        url: The original request URL.
        error: Human-readable error description.
        status_code: The HTTP status code, if the server responded.
        retry_after_seconds: Seconds to wait before retrying, parsed from
                             a ``Retry-After`` header when present.
    """

    url: str
    error: str
    status_code: int | None = None
    retry_after_seconds: float | None = None


# ══════════════════════════════════════════════════════════════════════════════
# HTML-to-Text Converter
# ══════════════════════════════════════════════════════════════════════════════


class _HTMLToTextParser(HTMLParser):
    """Extract plain text and page title from HTML, skipping script/style blocks.

    Strips ``<script>``, ``<style>``, and ``<noscript>`` element content.
    Handles nested skip-tags safely via explicit open/close tracking.
    """

    _SKIP_TAGS: frozenset[str] = frozenset({"script", "style", "noscript"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._title_parts: list[str] = []
        self._in_title: bool = False
        # Tracking nested skip tags — a simple counter handles
        # ``<script>...<script>...</script>...</script>`` edge cases.
        self._skip_depth: int = 0

    # ── Handler callbacks ─────────────────────────────────────────────────

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        # Inject a newline before block-level elements for readability.
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        elif self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    # ── Accessors ─────────────────────────────────────────────────────────

    def get_text(self) -> str:
        """Return the accumulated plain text, paragraphs separated by double newlines."""
        # Collapse multiple consecutive newlines and trim
        raw = " ".join(self._parts)
        collapsed = re.sub(r"\n{3,}", "\n\n", raw)
        return collapsed.strip()

    def get_title(self) -> str:
        """Return the extracted page title, or empty string."""
        return " ".join(self._title_parts).strip()


# Block-level HTML elements that trigger a newline in plain-text output.
_BLOCK_TAGS: frozenset[str] = frozenset({
    "p", "div", "article", "section", "header", "footer", "main", "nav",
    "aside", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "blockquote",
    "pre", "form", "fieldset", "figure", "figcaption", "details", "summary",
    "br", "hr", "ul", "ol", "dl", "table", "address",
})


def _html_to_text(html: str) -> tuple[str, str]:
    """Convert an HTML string to (plain_text, title).

    Args:
        html: Raw HTML document string.

    Returns:
        A ``(plain_text, title)`` tuple.
    """
    parser = _HTMLToTextParser()
    parser.feed(html)
    parser.close()
    return parser.get_text(), parser.get_title()


# ══════════════════════════════════════════════════════════════════════════════
# URL Validation (SSRF Protection)
# ══════════════════════════════════════════════════════════════════════════════


def _validate_url(url: str) -> str | None:
    """Validate a URL for scheme and hostname presence.

    Only ``http`` and ``https`` schemes are permitted to prevent SSRF
    attacks (e.g. ``file:///etc/passwd`` or ``gopher://...``).

    Args:
        url: The URL string to validate.

    Returns:
        An error message string if invalid, or ``None`` if the URL is acceptable.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return f"Invalid URL format: {url!r}"

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return (
            f"Unsupported URL scheme {parsed.scheme!r}. "
            f"Only http and https are allowed."
        )

    if not parsed.hostname:
        # urlparse may parse "http:///path" as having no netloc.
        return f"URL has no hostname: {url!r}"

    return None


# ══════════════════════════════════════════════════════════════════════════════
# Retry-After Parser
# ══════════════════════════════════════════════════════════════════════════════


def _parse_retry_after(header_value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value into seconds.

    Supports both forms defined in :rfc:`7231` §7.1.3:
    * **Delay-seconds** — an integer or decimal number (e.g. ``120``).
    * **HTTP-date** — an IMF-fixdate (e.g. ``Wed, 21 Oct 2015 07:28:00 GMT``).

    Args:
        header_value: Raw header string, or ``None``.

    Returns:
        Seconds to wait as a float, or ``None`` if unparseable / absent.
    """
    if not header_value:
        return None

    value = header_value.strip()

    # Attempt delay-seconds form first.
    try:
        seconds = float(value)
        return max(0.0, seconds)
    except ValueError:
        pass

    # Attempt HTTP-date form.
    try:
        retry_time = parsedate_to_datetime(value)
        if retry_time is None:
            return None
        now = datetime.now(timezone.utc)
        delay = (retry_time - now).total_seconds()
        return max(0.0, delay)
    except (ValueError, OverflowError, TypeError):
        return None


# ══════════════════════════════════════════════════════════════════════════════
# URLFetcher Service
# ══════════════════════════════════════════════════════════════════════════════


class URLFetcher:
    """Async service for fetching and parsing web page content.

    Fetches URL content via ``httpx`` with configurable timeout and
    ``User-Agent`` header. Converts HTML to plain text, stripping
    ``<script>``, ``<style>``, and ``<noscript>`` elements. Handles
    errors gracefully — the public :meth:`fetch` method **never** throws;
    it always returns either a :class:`FetchedContent` or a :class:`FetchError`.

    Implements exponential backoff with jitter for 429 (Too Many Requests)
    and 503 (Service Unavailable) responses, and respects the ``Retry-After``
    header when present.

    Usage::

        fetcher = URLFetcher()
        result = await fetcher.fetch("https://example.com")
        if isinstance(result, FetchedContent):
            print(result.title, result.raw_text)
        else:
            print(f"Failed: {result.error}")
    """

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        max_retries: int = MAX_RETRIES,
        base_backoff: float = BASE_BACKOFF,
        max_backoff: float = MAX_BACKOFF,
    ) -> None:
        """Initialise the URL fetcher with configurable parameters.

        Args:
            timeout: Request timeout in seconds. Default 30.
            user_agent: ``User-Agent`` header string sent with every request.
            max_retries: Maximum number of retry attempts for transient or
                         rate-limit errors (HTTP 429, 503).
            base_backoff: Base delay in seconds for exponential backoff.
            max_backoff: Upper limit for computed backoff delay in seconds.
        """
        self._timeout: float = timeout
        self._user_agent: str = user_agent
        self._max_retries: int = max_retries
        self._base_backoff: float = base_backoff
        self._max_backoff: float = max_backoff

    # ── Public API ────────────────────────────────────────────────────────

    async def fetch(self, url: str) -> FetchedContent | FetchError:
        """Fetch and parse content from a URL.

        Validates the URL, fetches content via ``httpx`` with automatic
        retry and exponential backoff for rate-limited responses, then
        converts the HTML body to plain text.

        Args:
            url: The URL to fetch (must use ``http`` or ``https`` scheme).

        Returns:
            A :class:`FetchedContent` on success, or a :class:`FetchError`
            describing what went wrong. This method never raises exceptions.
        """
        # ── URL validation ────────────────────────────────────────────────
        validation_error = _validate_url(url)
        if validation_error is not None:
            logger.warning("URL validation failed for %r: %s", url, validation_error)
            return FetchError(url=url, error=validation_error)

        # ── Retry loop ────────────────────────────────────────────────────
        last_error: FetchError | None = None

        for attempt in range(self._max_retries + 1):
            try:
                return await self._do_fetch(url)
            except FetchError as exc:
                last_error = exc
                if attempt < self._max_retries and self._is_retryable(exc.status_code):
                    delay = self._compute_delay(attempt, exc)
                    logger.info(
                        "Retrying %r (attempt %d/%d) after %.1fs — HTTP %s",
                        url,
                        attempt + 1,
                        self._max_retries,
                        delay,
                        exc.status_code,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning("Fetch failed for %r: %s", url, exc.error)
                    return exc
            except Exception as exc:
                logger.exception("Unexpected error while fetching %r", url)
                return FetchError(url=url, error=f"Unexpected error: {exc}")

        # Should be unreachable, but satisfies the type checker.
        return last_error or FetchError(url=url, error="Unknown error")

    # ── Single-attempt Fetch ──────────────────────────────────────────────

    async def _do_fetch(self, url: str) -> FetchedContent:
        """Perform a single fetch attempt with no retry logic.

        Raises:
            FetchError: On any HTTP-level or network failure, including
                        non-200 status codes.
        """
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
            headers={"User-Agent": self._user_agent},
        ) as client:
            try:
                response = await client.get(url)
            except httpx.TimeoutException as exc:
                raise FetchError(
                    url=url,
                    error=f"Request timed out after {self._timeout:.0f}s",
                ) from exc
            except httpx.ConnectError as exc:
                raise FetchError(
                    url=url,
                    error=f"Connection refused or failed: {exc}",
                ) from exc
            except httpx.NetworkError as exc:
                raise FetchError(
                    url=url,
                    error=f"Network error: {exc}",
                ) from exc
            except httpx.HTTPError as exc:
                raise FetchError(
                    url=url,
                    error=f"HTTP protocol error: {exc}",
                ) from exc

            # ── Check status ──────────────────────────────────────────────
            if response.status_code != 200:
                retry_after = _parse_retry_after(
                    response.headers.get("Retry-After")
                )
                raise FetchError(
                    url=url,
                    error=(
                        f"HTTP {response.status_code}: "
                        f"{response.reason_phrase or 'Unknown'}"
                    ),
                    status_code=response.status_code,
                    retry_after_seconds=retry_after,
                )

            # ── Parse HTML body ───────────────────────────────────────────
            content_type = response.headers.get("content-type", "text/html")
            # httpx.text already handles charset detection (from headers or
            # <meta> tags when charset_normalizer or chardet is installed).
            html = response.text
            raw_text, title = _html_to_text(html)

            logger.info(
                "Fetched %r — %d chars text, title=%r",
                str(response.url),
                len(raw_text),
                title[:80] if title else "",
            )
            return FetchedContent(
                url=str(response.url),  # final URL after redirects
                status_code=response.status_code,
                content_type=content_type,
                title=title,
                raw_text=raw_text,
            )

    # ── Retry Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _is_retryable(status_code: int | None) -> bool:
        """Return ``True`` if the HTTP status code warrants a retry."""
        return status_code in _RETRYABLE_STATUSES

    def _compute_delay(self, attempt: int, error: FetchError) -> float:
        """Compute the backoff delay for the next retry attempt.

        If the error carries a ``retry_after_seconds`` value (parsed from a
        ``Retry-After`` header), that value is used directly. Otherwise,
        exponential backoff with ±25 % jitter is applied:
        ``min(base * 2^attempt, max_backoff) * (0.75 + random * 0.5)``.

        Args:
            attempt: Zero-based attempt number (0 = first retry).
            error: The :class:`FetchError` from the previous attempt.

        Returns:
            Delay in seconds (≥ 0).
        """
        # Respect explicit Retry-After from the server.
        if error.retry_after_seconds is not None:
            return error.retry_after_seconds

        delay: float = self._base_backoff * (2 ** attempt)
        delay = min(delay, self._max_backoff)
        # ±25 % jitter to avoid thundering-herd on rate-limited endpoints.
        jitter_factor: float = 0.75 + random.random() * 0.5  # [0.75, 1.25)
        return max(0.0, delay * jitter_factor)
