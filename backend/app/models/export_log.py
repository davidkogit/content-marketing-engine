"""
Export log model for tracking CSV export history.

Records when a user exports a product's content with a specific
field mapping configuration.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ExportLog(Base):
    """Audit log entry for product content exports."""

    __tablename__ = "export_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False
    )
    exported_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    mapping_config_json: Mapped[str | None] = mapped_column(
        Text, default=None
    )
    exported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────
    product: Mapped["Product"] = relationship(
        "Product", back_populates="exports"
    )
    exporter: Mapped["User"] = relationship(
        "User", back_populates="export_logs"
    )
