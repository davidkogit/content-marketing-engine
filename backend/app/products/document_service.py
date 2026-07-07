"""
Document service layer — async operations for linking source documents to products.

Provides DocumentService with methods for creating (auto-fetching title from URL),
listing, and deleting product documents.  All methods accept ``db`` as the first
positional argument for callers to control session boundaries.
"""


import logging
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.url_fetcher import FetchError, FetchedContent, URLFetcher
from app.models.product import Product
from app.models.product_document import DocType, ProductDocument

logger = logging.getLogger(__name__)

# ── DocumentService ─────────────────────────────────────────────────────────


class DocumentService:
    """Async service for product document CRUD operations.

    Uses ``URLFetcher`` to auto-fetch document titles from URLs during creation.
    All mutation methods validate that the parent product exists and is active.

    Usage::

        service = DocumentService()
        doc = await service.create_document(db, product_id=1, url="https://...", doc_type=DocType.URL)
        docs = await service.list_documents(db, product_id=1)
    """

    def __init__(self, *, fetcher: URLFetcher | None = None) -> None:
        """Initialise with an optional URLFetcher (defaults to a new instance)."""
        self._fetcher = fetcher or URLFetcher()

    # ── Create ──────────────────────────────────────────────────────────

    async def create_document(
        self,
        db: AsyncSession,
        *,
        product_id: int,
        url: str,
        doc_type: DocType,
    ) -> ProductDocument:
        """Link a source document (by URL) to a product, auto-fetching its title.

        Validates that the product exists and is active.  Fetches the URL via
        ``URLFetcher`` to extract the page title; if the fetch fails the title
        falls back to the URL's path component.

        Args:
            db: Active database session.
            product_id: The parent product's primary key.
            url: Document URL (must use http or https scheme).
            doc_type: Either ``DocType.PDF`` or ``DocType.URL``.

        Returns:
            The newly created ``ProductDocument`` ORM instance.

        Raises:
            ValueError: If the product is not found or is soft-deleted.
        """
        # Guard: product must exist and be active
        product = await db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.is_deleted == False,  # noqa: E712
            )
        )
        if product.scalar_one_or_none() is None:
            raise ValueError(f"Product with id={product_id!r} not found.")

        # Auto-fetch title from URL
        title = await self._fetch_title(url)

        document = ProductDocument(
            product_id=product_id,
            title=title,
            url=url,
            doc_type=doc_type,
        )
        db.add(document)
        await db.flush()
        await db.refresh(document)

        logger.info(
            "Created document id=%d for product_id=%d title=%r",
            document.id,
            product_id,
            title[:80] if len(title) > 80 else title,
        )
        return document

    # ── Read ────────────────────────────────────────────────────────────

    async def get_by_id(
        self, db: AsyncSession, document_id: int
    ) -> ProductDocument | None:
        """Fetch a single document by its primary key.

        Args:
            db: Active database session.
            document_id: The document's primary key.

        Returns:
            The matching ``ProductDocument``, or ``None`` if not found.
        """
        result = await db.execute(
            select(ProductDocument).where(ProductDocument.id == document_id)
        )
        return result.scalar_one_or_none()

    async def list_documents(
        self, db: AsyncSession, product_id: int
    ) -> list[ProductDocument]:
        """List all documents linked to a product.

        Args:
            db: Active database session.
            product_id: The parent product's primary key.

        Returns:
            A (possibly empty) list of ``ProductDocument`` instances.
        """
        result = await db.execute(
            select(ProductDocument)
            .where(ProductDocument.product_id == product_id)
            .order_by(ProductDocument.created_at)
        )
        return list(result.scalars().all())

    # ── Delete ──────────────────────────────────────────────────────────

    async def delete_document(
        self, db: AsyncSession, document_id: int
    ) -> ProductDocument:
        """Permanently delete a document and its associated claims.

        Cascading is handled by SQLAlchemy relationships — child claims
        referencing this document are also deleted.

        Args:
            db: Active database session.
            document_id: The document's primary key.

        Returns:
            The deleted ``ProductDocument`` instance (detached).

        Raises:
            ValueError: If the document is not found.
        """
        result = await db.execute(
            select(ProductDocument).where(ProductDocument.id == document_id)
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise ValueError(f"Document with id={document_id!r} not found.")

        await db.delete(document)
        await db.flush()

        logger.info("Deleted document id=%d", document_id)
        return document

    # ── Helpers ─────────────────────────────────────────────────────────

    async def _fetch_title(self, url: str) -> str:
        """Fetch the page title from a URL, falling back to the path on failure.

        Args:
            url: The URL to fetch.

        Returns:
            The extracted page title, or the URL's path component as a fallback.
        """
        try:
            result = await self._fetcher.fetch(url)
        except Exception:
            logger.warning("Unexpected error fetching title from %r", url)
            return self._title_fallback(url)

        if isinstance(result, FetchedContent) and result.title:
            return result.title
        elif isinstance(result, FetchError):
            logger.warning("Fetch failed for %r: %s", url, result.error)

        return self._title_fallback(url)

    @staticmethod
    def _title_fallback(url: str) -> str:
        """Return a fallback title from the URL's path component."""
        path = urlparse(url).path.strip("/")
        if path:
            return path.rsplit("/", 1)[-1] if "/" in path else path
        # If no path, use the hostname
        hostname = urlparse(url).hostname or "unknown"
        return hostname
