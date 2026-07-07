"""
Unit tests for the URL content fetching and HTML parsing service.

Covers success, redirects, HTTP errors, timeouts, connection failures,
rate-limit handling with exponential backoff and Retry-After, URL
validation, and HTML-to-text conversion.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.documents.url_fetcher import (
    URLFetcher,
    FetchedContent,
    FetchError,
    _html_to_text,
    _parse_retry_after,
    _validate_url,
)


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════


def _build_mock_response(
    status_code: int = 200,
    text: str = "<html><head><title>Example</title></head><body><p>Hello world.</p></body></html>",
    headers: dict[str, str] | None = None,
    url: str = "https://example.com",
) -> AsyncMock:
    """Create an AsyncMock that mimics httpx.Response."""
    resp = AsyncMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {"content-type": "text/html; charset=utf-8"}
    resp.url = url
    resp.reason_phrase = "OK" if status_code == 200 else "Error"
    return resp


def _patch_httpx_client(get_side_effect):
    """Patch httpx.AsyncClient so that `.get()` returns the controlled response.

    Returns the mock ``get`` method so tests can assert on call arguments.
    """
    mock_get = AsyncMock(side_effect=get_side_effect)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = mock_get

    return patch(
        "app.documents.url_fetcher.httpx.AsyncClient",
        return_value=mock_client,
    ), mock_get


@pytest.fixture
def fetcher() -> URLFetcher:
    """Return a URLFetcher instance with fast retry defaults for testing."""
    return URLFetcher(
        timeout=10.0,
        max_retries=3,
        base_backoff=0.01,  # tiny for fast tests
        max_backoff=0.1,
    )


# ══════════════════════════════════════════════════════════════════════════════
# HTTP-to-Text Conversion (pure-function tests, no mocking needed)
# ══════════════════════════════════════════════════════════════════════════════


class TestHTMLToText:
    """Tests for _html_to_text — HTML parsing and title extraction."""

    def test_extracts_title_and_body(self) -> None:
        """Simple HTML should yield the title and text content."""
        html = (
            "<html><head><title>My Page</title></head>"
            "<body><p>Some content</p><p>More content</p></body></html>"
        )
        text, title = _html_to_text(html)
        assert title == "My Page"
        assert "Some content" in text
        assert "More content" in text

    def test_strips_script_tags(self) -> None:
        """Content inside <script> tags should be removed."""
        html = (
            "<html><head><title>T</title>"
            "<script>console.log('secret');</script></head>"
            "<body><p>Visible text.</p></body></html>"
        )
        text, _ = _html_to_text(html)
        assert "console.log" not in text
        assert "secret" not in text
        assert "Visible text." in text

    def test_strips_style_tags(self) -> None:
        """Content inside <style> tags should be removed."""
        html = (
            "<html><head><title>T</title>"
            "<style>.hidden { display: none; }</style></head>"
            "<body><p>Visible.</p></body></html>"
        )
        text, _ = _html_to_text(html)
        assert "hidden" not in text
        assert "display" not in text
        assert "Visible." in text

    def test_strips_noscript_tags(self) -> None:
        """Content inside <noscript> tags should be removed."""
        html = (
            "<html><body>"
            "<noscript>JS is required</noscript>"
            "<p>Real content</p>"
            "</body></html>"
        )
        text, _ = _html_to_text(html)
        assert "JS is required" not in text
        assert "Real content" in text

    def test_handles_nested_skip_tags(self) -> None:
        """Nested script tags should not confuse the skip tracking."""
        html = (
            "<script>outer"
            "<script>inner</script>"
            "still outer</script>"
            "<p>Real text</p>"
        )
        text, _ = _html_to_text(html)
        assert "outer" not in text
        assert "inner" not in text
        assert "Real text" in text

    def test_handles_empty_html(self) -> None:
        """Empty HTML should produce empty text and title."""
        text, title = _html_to_text("")
        assert text == ""
        assert title == ""

    def test_handles_html_without_title(self) -> None:
        """HTML without a <title> should return empty title."""
        html = "<html><body><p>No title here.</p></body></html>"
        text, title = _html_to_text(html)
        assert title == ""
        assert "No title here." in text

    def test_collapses_whitespace(self) -> None:
        """Multiple whitespace should be collapsed into readable paragraphs."""
        html = (
            "<html><body>"
            "<p>First  paragraph.</p>"
            "<p>Second  paragraph.</p>"
            "</body></html>"
        )
        text, _ = _html_to_text(html)
        # Should have meaningful paragraph separation
        assert "First paragraph." in text
        assert "Second paragraph." in text


# ══════════════════════════════════════════════════════════════════════════════
# URL Validation (pure-function tests)
# ══════════════════════════════════════════════════════════════════════════════


class TestURLValidation:
    """Tests for _validate_url — SSRF protection and scheme checking."""

    def test_accepts_https_url(self) -> None:
        """A standard HTTPS URL should pass validation."""
        assert _validate_url("https://example.com/page") is None

    def test_accepts_http_url(self) -> None:
        """A standard HTTP URL should pass validation."""
        assert _validate_url("http://example.com/page") is None

    def test_rejects_file_scheme(self) -> None:
        """The file:// scheme must be rejected (SSRF protection)."""
        error = _validate_url("file:///etc/passwd")
        assert error is not None
        assert "file" in error.lower()

    def test_rejects_no_hostname(self) -> None:
        """A URL without a hostname should be rejected."""
        error = _validate_url("http:///path")
        assert error is not None

    def test_rejects_unsupported_scheme(self) -> None:
        """FTP, gopher, etc. should be rejected."""
        error = _validate_url("ftp://example.com/data")
        assert error is not None


# ══════════════════════════════════════════════════════════════════════════════
# Retry-After Parser (pure-function tests)
# ══════════════════════════════════════════════════════════════════════════════


class TestParseRetryAfter:
    """Tests for _parse_retry_after header parsing."""

    def test_parses_seconds_value(self) -> None:
        """Integer seconds value should be returned as float."""
        assert _parse_retry_after("120") == 120.0

    def test_parses_decimal_value(self) -> None:
        """Decimal seconds value should be returned as float."""
        result = _parse_retry_after("2.5")
        assert result == pytest.approx(2.5)

    def test_parses_stripped_value(self) -> None:
        """Whitespace padding should be ignored."""
        assert _parse_retry_after("  60  ") == 60.0

    def test_returns_none_for_none(self) -> None:
        """None input should return None."""
        assert _parse_retry_after(None) is None

    def test_returns_none_for_empty(self) -> None:
        """Empty string should return None."""
        assert _parse_retry_after("") is None

    def test_returns_none_for_garbage(self) -> None:
        """Unparseable value should return None."""
        assert _parse_retry_after("not-a-date-or-number") is None

    def test_parses_http_date(self) -> None:
        """An HTTP-date should be parsed to seconds from now."""
        from datetime import datetime, timedelta, timezone
        from email.utils import format_datetime

        future = datetime.now(timezone.utc) + timedelta(seconds=42)
        date_str = format_datetime(future, usegmt=True)
        result = _parse_retry_after(date_str)
        # Should be approximately 42 seconds (±5 for parsing delay and clock skew)
        assert result is not None
        assert 30 <= result <= 55


# ══════════════════════════════════════════════════════════════════════════════
# Successful Fetch
# ══════════════════════════════════════════════════════════════════════════════


class TestSuccessfulFetch:
    """Happy-path tests: 200 response with valid HTML."""

    async def test_returns_fetched_content(self, fetcher: URLFetcher) -> None:
        """A 200 response should produce FetchedContent with parsed fields."""
        html_text = (
            "<html><head><title>Test Page</title></head>"
            "<body><p>Hello world</p></body></html>"
        )
        response = _build_mock_response(200, text=html_text)

        patcher, mock_get = _patch_httpx_client([response])
        with patcher:
            result = await fetcher.fetch("https://example.com")

        assert isinstance(result, FetchedContent)
        assert result.url == "https://example.com"
        assert result.status_code == 200
        assert result.title == "Test Page"
        assert "Hello world" in result.raw_text
        assert "text/html" in result.content_type

    async def test_passes_custom_user_agent(self) -> None:
        """The fetcher should send the configured User-Agent header."""
        response = _build_mock_response(200)
        custom_ua = "TestBot/1.0"

        fetcher_custom = URLFetcher(user_agent=custom_ua)
        patcher, mock_get = _patch_httpx_client([response])

        with patcher as mock_async_client_cls:
            await fetcher_custom.fetch("https://example.com")
            # Verify the User-Agent was passed to httpx.AsyncClient constructor
            _, kwargs = mock_async_client_cls.call_args
            assert kwargs["headers"]["User-Agent"] == custom_ua

    async def test_strips_scripts_from_output(self, fetcher: URLFetcher) -> None:
        """Script content must not appear in raw_text."""
        html_text = (
            "<html><head><title>T</title></head>"
            "<body><script>var x=1;</script><p>Clean text</p></body></html>"
        )
        response = _build_mock_response(200, text=html_text)
        patcher, _ = _patch_httpx_client([response])
        with patcher:
            result = await fetcher.fetch("https://example.com")
        assert isinstance(result, FetchedContent)
        assert "var x" not in result.raw_text


# ══════════════════════════════════════════════════════════════════════════════
# Redirect Handling
# ══════════════════════════════════════════════════════════════════════════════


class TestRedirectHandling:
    """Tests that redirects are followed and the final URL is reported."""

    async def test_follows_redirects(self, fetcher: URLFetcher) -> None:
        """When httpx follows a redirect, the final URL should be reported."""
        # httpx with follow_redirects=True transparently follows redirects.
        # We simulate the final response having a different URL.
        html_text = "<html><head><title>Redirected</title></head><body>OK</body></html>"
        response = _build_mock_response(
            200,
            text=html_text,
            url="https://final-destination.example.com/page",
        )
        patcher, _ = _patch_httpx_client([response])
        with patcher:
            result = await fetcher.fetch("https://short.link/abc")
        assert isinstance(result, FetchedContent)
        assert result.url == "https://final-destination.example.com/page"


# ══════════════════════════════════════════════════════════════════════════════
# HTTP Error Handling (non-retryable)
# ══════════════════════════════════════════════════════════════════════════════


class TestHTTPErrors:
    """Tests for non-200 HTTP status codes that are NOT retried."""

    async def test_404_returns_fetch_error(self, fetcher: URLFetcher) -> None:
        """A 404 should return FetchError immediately (no retry)."""
        response = _build_mock_response(404, text="Not Found")
        # Only one response needed — 404 should not trigger a retry.
        patcher, _ = _patch_httpx_client([response])
        with patcher:
            result = await fetcher.fetch("https://example.com/missing")
        assert isinstance(result, FetchError)
        assert result.status_code == 404
        assert "404" in result.error

    async def test_500_returns_fetch_error(self, fetcher: URLFetcher) -> None:
        """A 500 should return FetchError (500 is not retryable by default)."""
        response = _build_mock_response(500, text="Internal Error")
        patcher, _ = _patch_httpx_client([response])
        with patcher:
            result = await fetcher.fetch("https://example.com")
        assert isinstance(result, FetchError)
        assert result.status_code == 500

    async def test_403_returns_fetch_error(self, fetcher: URLFetcher) -> None:
        """A 403 Forbidden should return FetchError."""
        response = _build_mock_response(403)
        patcher, _ = _patch_httpx_client([response])
        with patcher:
            result = await fetcher.fetch("https://example.com/forbidden")
        assert isinstance(result, FetchError)
        assert result.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# Timeout Handling
# ══════════════════════════════════════════════════════════════════════════════


class TestTimeout:
    """Tests for request timeout scenarios."""

    async def test_timeout_returns_fetch_error(self, fetcher: URLFetcher) -> None:
        """When httpx raises TimeoutException, FetchError is returned."""
        patcher, mock_get = _patch_httpx_client(
            httpx.TimeoutException("Request timed out")
        )
        with patcher:
            result = await fetcher.fetch("https://slow.example.com")
        assert isinstance(result, FetchError)
        assert "timed out" in result.error.lower()
        assert result.status_code is None

    async def test_timeout_is_not_retried(self, fetcher: URLFetcher) -> None:
        """Timeout exceptions should NOT trigger a retry."""
        timeout_exc = httpx.TimeoutException("timed out")
        patcher, mock_get = _patch_httpx_client(timeout_exc)
        with patcher:
            result = await fetcher.fetch("https://slow.example.com")
        assert isinstance(result, FetchError)
        # Should only call get() once — no retry for timeouts
        assert mock_get.call_count == 1


# ══════════════════════════════════════════════════════════════════════════════
# Connection / Network Error Handling
# ══════════════════════════════════════════════════════════════════════════════


class TestConnectionError:
    """Tests for connection and network failure scenarios."""

    async def test_connect_error_returns_fetch_error(self, fetcher: URLFetcher) -> None:
        """When the connection is refused, FetchError is returned."""
        patcher, _ = _patch_httpx_client(
            httpx.ConnectError("Connection refused")
        )
        with patcher:
            result = await fetcher.fetch("https://down.example.com")
        assert isinstance(result, FetchError)
        assert "refused" in result.error.lower()
        assert result.status_code is None

    async def test_network_error_returns_fetch_error(self, fetcher: URLFetcher) -> None:
        """A generic NetworkError should produce FetchError."""
        patcher, _ = _patch_httpx_client(
            httpx.NetworkError("Network unreachable")
        )
        with patcher:
            result = await fetcher.fetch("https://offline.example.com")
        assert isinstance(result, FetchError)
        assert "network" in result.error.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Rate-Limit Handling (retryable 429)
# ══════════════════════════════════════════════════════════════════════════════


class TestRateLimitRetry:
    """Tests for retry behaviour on 429 Too Many Requests."""

    async def test_429_success_on_retry(self, fetcher: URLFetcher) -> None:
        """A 429 then a 200 should succeed after one retry."""
        rate_limited = _build_mock_response(
            429, text="Too Many Requests",
            headers={"Retry-After": "0"},
        )
        success = _build_mock_response(
            200,
            text="<html><head><title>OK</title></head><body>Back</body></html>",
        )
        patcher, mock_get = _patch_httpx_client([rate_limited, success])
        with patcher:
            result = await fetcher.fetch("https://rate-limited.example.com")
        assert isinstance(result, FetchedContent)
        assert result.status_code == 200
        assert result.title == "OK"
        # Should have been called twice: 429 → retry → 200
        assert mock_get.call_count == 2

    async def test_429_respects_retry_after_header(self, fetcher: URLFetcher) -> None:
        """When Retry-After header is present, it should be used."""
        rate_limited = _build_mock_response(
            429,
            text="Slow down",
            headers={"Retry-After": "0.05"},  # 50ms — fast for tests
        )
        success = _build_mock_response(200, text="<html><head><title>OK</title></head><body></body></html>")
        patcher, _ = _patch_httpx_client([rate_limited, success])

        start = asyncio.get_event_loop().time()
        with patcher:
            result = await fetcher.fetch("https://rate-limited.example.com")
        elapsed = asyncio.get_event_loop().time() - start

        assert isinstance(result, FetchedContent)
        # Should have waited at least ~40ms (allowing for clock jitter)
        assert elapsed >= 0.03

    async def test_max_retries_exhausted_on_429(self) -> None:
        """After max_retries+1 429 responses, FetchError is returned."""
        fetcher_small = URLFetcher(max_retries=2, base_backoff=0.01, max_backoff=0.05)
        rate_limited = _build_mock_response(429, headers={"Retry-After": "0"})
        # 3 responses: initial + 2 retries = all 429
        patcher, mock_get = _patch_httpx_client(
            [rate_limited, rate_limited, rate_limited]
        )
        with patcher:
            result = await fetcher_small.fetch("https://always-limited.example.com")
        assert isinstance(result, FetchError)
        assert result.status_code == 429
        assert mock_get.call_count == 3


# ══════════════════════════════════════════════════════════════════════════════
# Server Error Retry (503)
# ══════════════════════════════════════════════════════════════════════════════


class TestServerErrorRetry:
    """Tests for retry behaviour on 503 Service Unavailable."""

    async def test_503_success_on_retry(self, fetcher: URLFetcher) -> None:
        """A 503 followed by a 200 should succeed after retry."""
        unavailable = _build_mock_response(503, text="Service Unavailable")
        success = _build_mock_response(
            200,
            text="<html><head><title>Recovered</title></head><body>OK</body></html>",
        )
        patcher, mock_get = _patch_httpx_client([unavailable, success])
        with patcher:
            result = await fetcher.fetch("https://flaky.example.com")
        assert isinstance(result, FetchedContent)
        assert mock_get.call_count == 2

    async def test_503_max_retries_exhausted(self) -> None:
        """After max retries of 503, FetchError is returned."""
        fetcher_small = URLFetcher(max_retries=1, base_backoff=0.01, max_backoff=0.05)
        unavailable = _build_mock_response(503)
        patcher, mock_get = _patch_httpx_client([unavailable, unavailable])
        with patcher:
            result = await fetcher_small.fetch("https://permanently-down.example.com")
        assert isinstance(result, FetchError)
        assert result.status_code == 503
        assert mock_get.call_count == 2

    async def test_404_is_not_retried(self, fetcher: URLFetcher) -> None:
        """404 errors should NOT be retried (only 429 and 503 are)."""
        not_found = _build_mock_response(404)
        patcher, mock_get = _patch_httpx_client([not_found])
        with patcher:
            result = await fetcher.fetch("https://example.com/missing")
        assert isinstance(result, FetchError)
        assert mock_get.call_count == 1


# ══════════════════════════════════════════════════════════════════════════════
# URL Validation at Fetch Level
# ══════════════════════════════════════════════════════════════════════════════


class TestFetchURLValidation:
    """Integration of URL validation within the fetch flow."""

    async def test_invalid_url_returns_error_without_http_call(self, fetcher: URLFetcher) -> None:
        """An invalid URL should be caught before any HTTP request is made."""
        patcher, mock_get = _patch_httpx_client([])
        with patcher:
            result = await fetcher.fetch("not-a-url")
        assert isinstance(result, FetchError)
        # No HTTP request should have been attempted
        mock_get.assert_not_called()

    async def test_file_scheme_rejected(self, fetcher: URLFetcher) -> None:
        """The file:// scheme must short-circuit with an error."""
        patcher, mock_get = _patch_httpx_client([])
        with patcher:
            result = await fetcher.fetch("file:///etc/passwd")
        assert isinstance(result, FetchError)
        mock_get.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# Configurable Parameters
# ══════════════════════════════════════════════════════════════════════════════


class TestConfigurability:
    """Tests that constructor parameters are respected."""

    async def test_custom_timeout_is_used(self) -> None:
        """The timeout parameter should be passed to httpx.AsyncClient."""
        custom_timeout = 45.0
        fetcher_custom = URLFetcher(timeout=custom_timeout)
        response = _build_mock_response(200)
        patcher, _ = _patch_httpx_client([response])

        with patcher as mock_async_client_cls:
            await fetcher_custom.fetch("https://example.com")
            _, kwargs = mock_async_client_cls.call_args
            timeout_arg = kwargs["timeout"]
            # httpx.Timeout wraps the numeric value
            assert timeout_arg.connect == custom_timeout
            assert timeout_arg.read == custom_timeout

    async def test_defaults_are_sensible(self) -> None:
        """Default constructor should create a working fetcher."""
        default_fetcher = URLFetcher()
        assert default_fetcher._timeout == 30.0
        assert default_fetcher._max_retries == 3
        assert "ContentMarketingEngine" in default_fetcher._user_agent
