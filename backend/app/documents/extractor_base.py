"""
Abstract base class and shared types for document extraction.

Defines the ``DocumentExtractor`` interface and the ``ExtractedContent``
dataclass that all concrete extractors must implement.
"""


from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# ── ExtractedContent ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExtractedContent:
    """Immutable result container returned by every ``DocumentExtractor``.

    Attributes:
        raw_text: The full extracted text content, with paragraph breaks
                  represented by double-newline separators.
        page_count: Number of pages processed (1 for non-paginated sources).
        metadata: Arbitrary key-value metadata from the source document
                  (e.g. PDF ``Title`` and ``Author`` fields).
    """

    raw_text: str
    """All text extracted from the document, paragraphs separated by blank lines."""

    page_count: int
    """Total number of pages (always >= 1 for a successful extraction)."""

    metadata: dict[str, str] = field(default_factory=dict)
    """Source-document metadata such as title, author, and creation date."""


# ── DocumentExtractor ────────────────────────────────────────────────────────


class DocumentExtractor(ABC):
    """Abstract interface for document text extraction.

    Concrete implementations handle specific document formats (PDF, HTML,
    plain-text, etc.) and produce an :class:`ExtractedContent` value.

    All implementations must be async and accept either a local file path
    or a remote URL.  URL-based sources are downloaded to a temporary file
    before processing.

    Usage::

        extractor = PDFExtractor(http_client=client)
        content = await extractor.extract("/path/to/report.pdf")
        print(content.raw_text)
    """

    @abstractmethod
    async def extract(self, url_or_path: str) -> ExtractedContent:
        """Extract text and metadata from the given document source.

        Args:
            url_or_path: A local filesystem path (``str`` or ``Path``) or a
                         remote ``http://`` / ``https://`` URL pointing to
                         the document.

        Returns:
            An :class:`ExtractedContent` value containing the full text,
            page count, and available metadata.

        Raises:
            FileNotFoundError: If the argument is a local path that does
                               not exist on disk.
            ValueError: If the source is neither a valid URL nor a
                        resolvable local path.
            ExtractionError: For format-specific failures such as a
                             corrupted or password-protected document.
        """
        ...
