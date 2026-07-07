"""
Product document model for storing source document references.

Documents are linked by URL (PDFs fetched and processed via pdfplumber,
web pages fetched via httpx). Extracted text is stored for RAG context.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocType(str, enum.Enum):
    """Supported document source types."""

    PDF = "pdf"
    URL = "url"


class ProductDocument(Base):
    """A source document attached to a product for claim generation."""

    __tablename__ = "product_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, default=None)
    doc_type: Mapped[DocType] = mapped_column(
        Enum(DocType, create_constraint=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────
    product: Mapped["Product"] = relationship(
        "Product", back_populates="documents"
    )
    claims: Mapped[list["ProductClaim"]] = relationship(
        "ProductClaim",
        foreign_keys="ProductClaim.source_doc_id",
        back_populates="source_doc",
    )
