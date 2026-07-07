"""
User authentication model with role-based access control.

Defines the User ORM model and UserRole enum for the four hardcoded
roles: super_admin, admin, editor, viewer.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    """Hardcoded access roles for the application."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class User(Base):
    """Authenticated user with hashed password and role."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        default=UserRole.VIEWER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        doc="Incremented on refresh to invalidate all prior refresh tokens.",
    )

    # ── Relationships ──────────────────────────────────────────────────
    documents_assigned: Mapped[list["ProductClaim"]] = relationship(
        "ProductClaim",
        foreign_keys="ProductClaim.assigned_to",
        back_populates="assignee",
    )
    product_versions: Mapped[list["ProductVersion"]] = relationship(
        "ProductVersion", back_populates="author"
    )
    export_logs: Mapped[list["ExportLog"]] = relationship(
        "ExportLog", back_populates="exporter"
    )
