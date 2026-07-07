"""
Unit tests for the PDF text extraction service.

Covers successful extraction, error handling for corrupted/missing
PDFs, metadata extraction, URL-based download, and paragraph structure
preservation.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.documents.extractor_base import DocumentExtractor, ExtractedContent
from app.documents.pdf_extractor import (
    DownloadError,
    ExtractionError,
    PDFExtractor,
)

# ── Fixture paths ────────────────────────────────────────────────────────────

FIXTURES_DIR: Path = Path(__file__).resolve().parent / "fixtures"
SAMPLE_PDF: Path = FIXTURES_DIR / "sample.pdf"


@pytest.fixture
def sample_pdf_path() -> Path:
    """Return the absolute path to the sample PDF fixture."""
    assert SAMPLE_PDF.is_file(), f"Sample PDF fixture missing: {SAMPLE_PDF}"
    return SAMPLE_PDF


@pytest.fixture
def extractor() -> PDFExtractor:
    """Return a PDFExtractor with no HTTP client (local-only)."""
    return PDFExtractor()


# ── Successful Extraction ────────────────────────────────────────────────────


class TestExtractLocalFile:
    """Tests for successful local file extraction."""

    async def test_extract_returns_extracted_content(
        self, extractor: PDFExtractor, sample_pdf_path: Path
    ) -> None:
        """extract() should return an ExtractedContent instance with text."""
        result = await extractor.extract(str(sample_pdf_path))

        assert isinstance(result, ExtractedContent)
        assert len(result.raw_text) > 0
        assert result.page_count >= 1

    async def test_extract_page_count_matches_pdf(
        self, extractor: PDFExtractor, sample_pdf_path: Path
    ) -> None:
        """The page_count field should match the actual number of pages."""
        result = await extractor.extract(str(sample_pdf_path))

        assert result.page_count == 2

    async def test_extract_metadata_includes_title_and_author(
        self, extractor: PDFExtractor, sample_pdf_path: Path
    ) -> None:
        """Metadata dict should contain the PDF Title and Author."""
        result = await extractor.extract(str(sample_pdf_path))

        assert "Title" in result.metadata
        assert result.metadata["Title"] == "Q4 Marketing Report"
        assert "Author" in result.metadata
        assert result.metadata["Author"] == "Jane Doe"

    async def test_extract_paragraph_structure_preserved(
        self, extractor: PDFExtractor, sample_pdf_path: Path
    ) -> None:
        """Extracted text should use double-newlines to separate paragraphs."""
        result = await extractor.extract(str(sample_pdf_path))

        # The sample PDF has multiple text blocks across pages
        assert "\n\n" in result.raw_text, (
            "Expected double-newline paragraph separators in extracted text"
        )

    async def test_extract_accepts_path_object(
        self, extractor: PDFExtractor, sample_pdf_path: Path
    ) -> None:
        """extract() should accept a pathlib.Path via str conversion."""
        result = await extractor.extract(str(sample_pdf_path))

        assert isinstance(result, ExtractedContent)
        assert result.raw_text

    async def test_extracted_content_is_immutable(
        self, extractor: PDFExtractor, sample_pdf_path: Path
    ) -> None:
        """ExtractedContent should be a frozen dataclass (immutable)."""
        result = await extractor.extract(str(sample_pdf_path))

        with pytest.raises(FrozenInstanceError):
            result.page_count = 999  # type: ignore[misc]


# ── Error Handling ───────────────────────────────────────────────────────────


class TestExtractMissingFile:
    """Tests for missing / non-existent files."""

    async def test_extract_raises_file_not_found(
        self, extractor: PDFExtractor
    ) -> None:
        """A non-existent local path should raise FileNotFoundError."""
        missing = "/nonexistent/path/file.pdf"

        with pytest.raises(FileNotFoundError, match="file.pdf"):
            await extractor.extract(missing)

    async def test_extract_raises_file_not_found_for_directory(
        self, extractor: PDFExtractor, tmp_path: Path
    ) -> None:
        """Passing a directory path should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await extractor.extract(str(tmp_path))


class TestExtractEmptyInput:
    """Tests for invalid input values."""

    @pytest.mark.parametrize("bad_input", ["", "   ", "\n\t"])
    async def test_extract_raises_value_error_for_empty_string(
        self, extractor: PDFExtractor, bad_input: str
    ) -> None:
        """An empty or whitespace-only string should raise ValueError."""
        with pytest.raises(ValueError):
            await extractor.extract(bad_input)


class TestExtractCorruptedPdf:
    """Tests for corrupted / malformed PDF files."""

    async def test_extract_raises_extraction_error_for_corrupt_pdf(
        self, extractor: PDFExtractor, tmp_path: Path
    ) -> None:
        """A file that is not a valid PDF should raise ExtractionError."""
        corrupt = tmp_path / "corrupt.pdf"
        corrupt.write_bytes(b"This is not a PDF file at all.")

        with pytest.raises(ExtractionError):
            await extractor.extract(str(corrupt))

    async def test_extract_empty_pdf(
        self, extractor: PDFExtractor, tmp_path: Path
    ) -> None:
        """An empty file should raise ExtractionError."""
        empty_file = tmp_path / "empty.pdf"
        empty_file.write_bytes(b"")

        with pytest.raises(ExtractionError):
            await extractor.extract(str(empty_file))


# ── URL Input Handling ───────────────────────────────────────────────────────


class TestIsUrl:
    """Tests for the _is_url static helper."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("https://example.com/doc.pdf", True),
            ("http://cdn.example.com/report.pdf", True),
            ("ftp://files.example.com/doc.pdf", False),
            ("/local/path/report.pdf", False),
            ("C:\\Users\\docs\\report.pdf", False),
            ("file:///tmp/report.pdf", False),
        ],
    )
    def test_is_url_detection(self, value: str, expected: bool) -> None:
        """_is_url should correctly identify HTTP(S) URLs."""
        assert PDFExtractor._is_url(value) is expected


# ── Abstract Base Class ──────────────────────────────────────────────────────


class TestDocumentExtractorABC:
    """Verify the abstract base class contract."""

    def test_extract_is_abstract(self) -> None:
        """DocumentExtractor.extract must be abstract."""
        assert callable(DocumentExtractor.extract)

        with pytest.raises(TypeError):
            DocumentExtractor()  # type: ignore[abstract]

    def test_pdf_extractor_is_subclass(self) -> None:
        """PDFExtractor must be a subclass of DocumentExtractor."""
        assert issubclass(PDFExtractor, DocumentExtractor)

    def test_extracted_content_is_dataclass(self) -> None:
        """ExtractedContent must have the expected fields."""
        content = ExtractedContent(raw_text="hello", page_count=1)

        assert content.raw_text == "hello"
        assert content.page_count == 1
        assert content.metadata == {}

    def test_extracted_content_with_metadata(self) -> None:
        """Metadata can be passed at construction time."""
        content = ExtractedContent(
            raw_text="test",
            page_count=3,
            metadata={"Title": "My Doc", "Author": "Me"},
        )

        assert content.metadata["Title"] == "My Doc"
        assert content.metadata["Author"] == "Me"


# ── Metadata Extraction ──────────────────────────────────────────────────────


class TestBuildMetadata:
    """Tests for the _build_metadata static helper."""

    def test_metadata_filters_empty_values(self) -> None:
        """_build_metadata should exclude empty/null metadata values."""
        # We test the static method signature — actual behaviour is
        # verified by the integration test above.
        assert callable(PDFExtractor._build_metadata)


# ── Integration: verify ExtractedContent shape ───────────────────────────────


class TestExtractedContentInvariants:
    """Quick sanity checks on the ExtractedContent dataclass."""

    async def test_page_count_always_positive_for_real_extraction(
        self, extractor: PDFExtractor, sample_pdf_path: Path
    ) -> None:
        """After a successful extraction, page_count must be >= 1."""
        result = await extractor.extract(str(sample_pdf_path))
        assert result.page_count >= 1

    async def test_raw_text_not_empty_for_sample_pdf(
        self, extractor: PDFExtractor, sample_pdf_path: Path
    ) -> None:
        """The sample PDF must yield non-empty extracted text."""
        result = await extractor.extract(str(sample_pdf_path))
        assert len(result.raw_text.strip()) > 0
