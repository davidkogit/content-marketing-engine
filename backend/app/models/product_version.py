"""
Product version model for tracking content edits and change history.

Each version captures a full snapshot of the product state at a point
in time, enabling rollback and audit trails.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProductVersion(Base):
    """A versioned snapshot of product content with change tracking."""

    __tablename__ = "product_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(String(500), default=None)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────
    product: Mapped["Product"] = relationship(
        "Product", back_populates="versions"
    )
    author: Mapped["User"] = relationship(
        "User", back_populates="product_versions"
    )
