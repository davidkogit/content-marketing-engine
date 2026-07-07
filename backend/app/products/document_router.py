"""
Documents API router — link source documents to products, list, and delete.

Mounts under ``/api/v1`` (prefixed by ``main.py``) and exposes:
- ``POST   /api/products/{id}/documents`` — link a document, auto-fetch title
- ``GET    /api/products/{id}/documents`` — list documents for a product
- ``DELETE /api/documents/{id}``           — remove document link (admin+ only)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import RoleDTO
from app.database import get_db
from app.models.user import User
from app.products.document_schemas import DocumentCreate, DocumentResponse
from app.products.document_service import DocumentService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])

# ── Singleton ───────────────────────────────────────────────────────────────

_document_service = DocumentService()


# ── GET /api/products/{product_id}/documents ─────────────────────────────────


@router.get(
    "/products/{product_id}/documents",
    response_model=list[DocumentResponse],
    summary="List documents for a product",
)
async def list_product_documents(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[DocumentResponse]:
    """Return all documents linked to the specified product.

    Any authenticated user may list documents.
    """
    docs = await _document_service.list_documents(db, product_id)
    return [DocumentResponse.model_validate(d) for d in docs]


# ── POST /api/products/{product_id}/documents ────────────────────────────────


@router.post(
    "/products/{product_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Link a document to a product",
)
async def create_document(
    product_id: int,
    body: DocumentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> DocumentResponse:
    """Link a source document (URL) to a product.  Requires admin or higher.

    The document title is automatically fetched from the URL.  If the fetch
    fails, a fallback title (derived from the URL path) is used.
    """
    try:
        doc = await _document_service.create_document(
            db,
            product_id=product_id,
            url=body.url,
            doc_type=body.doc_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    logger.info(
        "Document id=%d linked to product_id=%d by user_id=%d",
        doc.id,
        product_id,
        current_user.id,
    )
    return DocumentResponse.model_validate(doc)


# ── DELETE /api/documents/{document_id} ─────────────────────────────────────


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a document link",
)
async def delete_document(
    document_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(RoleDTO.ADMIN))],
) -> None:
    """Permanently delete a document link and its associated claims.  Requires admin+.

    Returns ``204 No Content`` on success.
    """
    try:
        await _document_service.delete_document(db, document_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    logger.info(
        "Document id=%d deleted by user_id=%d", document_id, current_user.id
    )
