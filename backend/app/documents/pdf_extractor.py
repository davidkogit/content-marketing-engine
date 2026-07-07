"""
PDF text extraction service using the pdfplumber library.

Provides ``PDFExtractor``, a concrete implementation of the
``DocumentExtractor`` interface that extracts all text from PDF pages
while preserving paragraph structure.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pdfplumber
from pdfplumber.pdf import PDF

from app.documents.extractor_base import DocumentExtractor, ExtractedContent

logger = logging.getLogger(__name__)

# ── Domain Exceptions ────────────────────────────────────────────────────────


class ExtractionError(Exception):
    """Raised when a document cannot be parsed (corrupted, encrypted, etc.)."""


class DownloadError(Exception):
    """Raised when a remote document cannot be fetched."""


# ── Constants ────────────────────────────────────────────────────────────────

_MAX_DOWNLOAD_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MiB safety cap
"""Maximum number of bytes to download from a remote URL."""

_DOWNLOAD_CHUNK_SIZE: int = 64 * 1024  # 64 KiB per chunk
"""Chunk size used when streaming a remote document to a temp file."""

_SUPPORTED_URL_SCHEMES: frozenset[str] = frozenset({"http", "https"})
"""URL schemes accepted by the download helper."""

_PDF_METADATA_FIELDS: tuple[str, ...] = (
    "Title",
    "Author",
    "Subject",
    "Creator",
    "Producer",
    "CreationDate",
    "ModDate",
)
"""Metadata keys extracted from a PDF's info dictionary when present."""


# ── PDFExtractor ─────────────────────────────────────────────────────────────


class PDFExtractor(DocumentExtractor):
    """Extract full text and metadata from PDF documents using pdfplumber.

    Supports both local file paths and remote URLs.  Remote PDFs are
    downloaded to a temporary file before extraction.

    Paragraph structure is preserved by joining each page's text with
    a double-newline separator (``\\n\\n``), which matches the default
    behaviour of ``page.extract_text()``.

    Usage::

        async with httpx.AsyncClient() as client:
            extractor = PDFExtractor(http_client=client)
            content = await extractor.extract("/docs/report.pdf")
            assert content.page_count > 0
    """

    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        """Initialise the PDF extractor.

        Args:
            http_client: An optional shared ``httpx.AsyncClient`` for
                         downloading remote PDFs.  If not supplied, a
                         new client is created per download (less
                         efficient for multiple remote extractions).
        """
        self._http_client: httpx.AsyncClient | None = http_client

    # ── Public API ───────────────────────────────────────────────────────

    async def extract(self, url_or_path: str) -> ExtractedContent:
        """Extract all text and metadata from a PDF.

        See :meth:`DocumentExtractor.extract` for the full contract.
        """
        local_path, needs_cleanup = await self._resolve_source(url_or_path)

        try:
            return await self._extract_from_file(local_path)
        except ExtractionError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error extracting PDF: %s", exc)
            raise ExtractionError(f"Failed to extract PDF content: {exc}") from exc
        finally:
            if needs_cleanup:
                self._cleanup_temp(local_path)

    # ── Source Resolution ────────────────────────────────────────────────

    async def _resolve_source(self, url_or_path: str) -> tuple[Path, bool]:
        """Normalise the input string into a guaranteed-local file path.

        Returns a ``(path, needs_cleanup)`` tuple.  ``needs_cleanup`` is
        ``True`` when the file was downloaded to a temp location and should
        be removed after extraction.

        Args:
            url_or_path: A local path or a ``http(s)://`` URL.

        Returns:
            Tuple of ``(resolved_path, needs_cleanup)``.

        Raises:
            ValueError: If the string is empty or has an unsupported scheme.
            FileNotFoundError: If it looks like a local path but is missing.
            DownloadError: If a remote download fails.
        """
        if not url_or_path or not url_or_path.strip():
            raise ValueError("url_or_path must be a non-empty string.")

        if self._is_url(url_or_path):
            return await self._download_to_temp(url_or_path), True

        file_path = Path(url_or_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"PDF file not found: {file_path}")
        return file_path, False

    @staticmethod
    def _is_url(value: str) -> bool:
        """Check whether a string looks like a remote URL."""
        parsed = urlparse(value)
        return parsed.scheme in _SUPPORTED_URL_SCHEMES and bool(parsed.netloc)

    @staticmethod
    def _cleanup_temp(path: Path) -> None:
        """Remove a temporary file, ignoring any OS-level errors."""
        try:
            path.unlink(missing_ok=True)
            logger.debug("Cleaned up temp file: %s", path)
        except OSError as exc:
            logger.warning("Failed to clean up temp file %s: %s", path, exc)

    # ── Remote Download ──────────────────────────────────────────────────

    async def _download_to_temp(self, url: str) -> Path:
        """Stream a remote PDF to a temporary file on disk.

        Args:
            url: The remote URL pointing to a PDF document.

        Returns:
            Path to the downloaded temp file (caller **must** clean up).

        Raises:
            DownloadError: If the download fails, the status code is
                           non-2xx, or the content exceeds the size cap.
        """
        client = self._http_client or httpx.AsyncClient()

        async def _download() -> Path:
            try:
                async with client.stream("GET", url, follow_redirects=True) as resp:
                    self._check_download_response(resp)
                    return await self._stream_to_file(resp)
            except httpx.HTTPError as exc:
                raise DownloadError(f"Failed to download PDF from {url}: {exc}") from exc

        if self._http_client is None:
            async with client:
                return await _download()
        return await _download()

    @staticmethod
    def _check_download_response(
        resp: httpx.Response,
    ) -> None:
        """Validate the HTTP response before streaming content."""
        if resp.is_error:
            raise DownloadError(
                f"Received HTTP {resp.status_code} when downloading PDF"
            )
        content_length = resp.headers.get("content-length")
        if content_length and int(content_length) > _MAX_DOWNLOAD_SIZE_BYTES:
            raise DownloadError(
                f"PDF exceeds maximum download size "
                f"({_MAX_DOWNLOAD_SIZE_BYTES // (1024 * 1024)} MiB)"
            )

    async def _stream_to_file(
        self,
        resp: httpx.Response,
    ) -> Path:
        """Write the response body to a temp file in chunks."""
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        try:
            total = 0
            async for chunk in resp.aiter_bytes(chunk_size=_DOWNLOAD_CHUNK_SIZE):
                total += len(chunk)
                if total > _MAX_DOWNLOAD_SIZE_BYTES:
                    raise DownloadError("Download size exceeded safety cap mid-stream.")
                tmp.write(chunk)
            tmp.flush()
            return Path(tmp.name)
        except BaseException:
            # Clean up the temp file on any failure.
            Path(tmp.name).unlink(missing_ok=True)
            raise

    # ── Core Extraction Logic ─────────────────────────────────────────────

    async def _extract_from_file(self, file_path: Path) -> ExtractedContent:
        """Open a local PDF with pdfplumber and extract text + metadata.

        Args:
            file_path: Resolved ``Path`` to an existing PDF file.

        Returns:
            Populated ``ExtractedContent`` value.

        Raises:
            ExtractionError: If the PDF is corrupted, password-protected,
                             or otherwise unparseable by pdfplumber.
        """
        logger.info("Extracting text from PDF: %s", file_path)

        try:
            with pdfplumber.open(file_path) as pdf:
                page_count = len(pdf.pages)
                raw_text = self._build_text(pdf)
                metadata = self._build_metadata(pdf)
        except pdfplumber.PDFSyntaxError as exc:
            raise ExtractionError(f"PDF appears to be corrupted: {exc}") from exc
        except Exception as exc:
            raise ExtractionError(f"Failed to parse PDF: {exc}") from exc

        logger.info(
            "Extraction complete — %d pages, %d chars of text.",
            page_count,
            len(raw_text),
        )
        return ExtractedContent(
            raw_text=raw_text,
            page_count=page_count,
            metadata=metadata,
        )

    @staticmethod
    def _build_text(pdf: PDF) -> str:
        """Concatenate the text of every page with double-newline separators.

        Pages that return ``None`` from ``extract_text()`` (e.g. purely
        graphical pages) are skipped silently rather than halting.
        """
        parts: list[str] = []
        for page_num, page in enumerate(pdf.pages, start=1):
            try:
                page_text = page.extract_text()
            except Exception:
                logger.warning("Failed to extract text from page %d", page_num)
                continue
            if page_text:
                parts.append(page_text.strip())
        return "\n\n".join(parts)

    @staticmethod
    def _build_metadata(pdf: PDF) -> dict[str, str]:
        """Extract well-known metadata fields from the PDF info dictionary.

        Returns a flat ``dict`` containing only non-empty string values.
        Keys are the standard PDF names (e.g. ``Title``, ``Author``).
        """
        raw = pdf.metadata or {}
        return {
            key: str(value)
            for key in _PDF_METADATA_FIELDS
            if (value := raw.get(key)) and str(value).strip()
        }
