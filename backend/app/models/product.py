"""
Product model — the central entity in the PIM system.

Each product belongs to a category and a segment, and tracks its position
in the content marketing workflow via a Kanban-style stage enum.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class WorkflowStage(str, enum.Enum):
    """Kanban workflow stages for content marketing pipeline."""

    INGEST = "ingest"
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    EXPORTED = "exported"


class Product(Base):
    """A marketable product with SKU, metadata, and workflow tracking."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id"), default=None
    )
    segment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("segments.id"), default=None
    )
    workflow_stage: Mapped[WorkflowStage] = mapped_column(
        Enum(WorkflowStage, create_constraint=True),
        default=WorkflowStage.INGEST,
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────
    category: Mapped["Category | None"] = relationship(
        "Category", back_populates="products"
    )
    segment: Mapped["Segment | None"] = relationship(
        "Segment", back_populates="products"
    )
    documents: Mapped[list["ProductDocument"]] = relationship(
        "ProductDocument", back_populates="product"
    )
    claims: Mapped[list["ProductClaim"]] = relationship(
        "ProductClaim", back_populates="product"
    )
    versions: Mapped[list["ProductVersion"]] = relationship(
        "ProductVersion", back_populates="product"
    )
    exports: Mapped[list["ExportLog"]] = relationship(
        "ExportLog", back_populates="product"
    )
