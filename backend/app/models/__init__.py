"""
Models module — SQLite schema and SQLAlchemy ORM models.

Re-exports all model classes and enums for convenient importing:

    from app.models import User, UserRole, Product, WorkflowStage, ...
"""

from app.models.category import Category
from app.models.export_log import ExportLog
from app.models.llm_config import LLMConfig, LLMProvider
from app.models.product import Product, WorkflowStage
from app.models.product_claim import ClaimStatus, ProductClaim
from app.models.product_document import DocType, ProductDocument
from app.models.product_version import ProductVersion
from app.models.segment import Segment
from app.models.user import User, UserRole

__all__ = [
    "Category",
    "ClaimStatus",
    "DocType",
    "ExportLog",
    "LLMConfig",
    "LLMProvider",
    "Product",
    "ProductClaim",
    "ProductDocument",
    "ProductVersion",
    "Segment",
    "User",
    "UserRole",
    "WorkflowStage",
]
