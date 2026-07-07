"""
LLM configuration model for admin-managed provider settings.

Stores encrypted API keys and provider/model selection. Only
super_admin users can manage these configurations.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LLMProvider(str, enum.Enum):
    """Supported LLM API providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LLMConfig(Base):
    """Configuration for an LLM provider with encrypted credentials."""

    __tablename__ = "llm_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[LLMProvider] = mapped_column(
        Enum(LLMProvider, create_constraint=True), nullable=False
    )
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
