"""
LLM settings API router — Super Admin endpoints for LLM provider configuration.

Mounts under ``/settings/llm`` and exposes:
- ``GET    /settings/llm`` — read the active LLM configuration (masked key).
- ``PUT    /settings/llm`` — update the LLM provider, model, and API key.
- ``POST   /settings/llm/test`` — test the active LLM provider connection.

All endpoints require ``SUPER_ADMIN`` role.
"""


import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.schemas import RoleDTO
from app.database import get_db
from app.llm.config_service import decrypt_api_key
from app.models.user import User
from app.settings.llm_schemas import (
    LLMConfigResponse,
    LLMConfigTestResponse,
    LLMConfigUpdateRequest,
)
from app.settings.llm_service import (
    get_active_llm_config,
    mask_api_key,
    test_llm_connection,
    update_llm_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/llm", tags=["settings"])

# All endpoints in this router require SUPER_ADMIN.  We apply the dependency
# at the router level by using ``require_role(RoleDTO.SUPER_ADMIN)`` on each
# endpoint individually (FastAPI does not support router-level dependencies
# that also influence ``response_model`` serialisation behaviour cleanly).

_SuperAdminDep = Annotated[User, Depends(require_role(RoleDTO.SUPER_ADMIN))]


# ── GET /settings/llm ───────────────────────────────────────────────────────


@router.get(
    "",
    response_model=LLMConfigResponse,
    summary="Get active LLM configuration",
)
async def get_llm_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: _SuperAdminDep,
) -> LLMConfigResponse:
    """Return the currently active LLM provider configuration.

    The API key is masked — only ``sk-...XXXX`` is visible.  If no
    configuration has been set, returns a 404.

    Returns:
        An ``LLMConfigResponse`` with provider, model, masked key, and metadata.

    Raises:
        HTTPException 404: If no active LLM configuration exists.
        HTTPException 403: If the caller is not a super admin.
    """
    config = await get_active_llm_config(db)

    if config is None:
        return LLMConfigResponse(
            provider="openai",
            model="",
            api_base_url=None,
            masked_api_key="",
            is_active=False,
            created_at=datetime.min,
        )

    decrypted = decrypt_api_key(config.api_key_encrypted)
    masked = mask_api_key(decrypted) if decrypted else "..."

    return LLMConfigResponse(
        provider=config.provider.value,
        model=config.model_name,
        api_base_url=config.api_base_url,
        masked_api_key=masked,
        is_active=config.is_active,
        created_at=config.created_at,
    )


# ── PUT /settings/llm ───────────────────────────────────────────────────────


@router.put(
    "",
    response_model=LLMConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Update active LLM configuration",
)
async def put_llm_config(
    body: LLMConfigUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: _SuperAdminDep,
) -> LLMConfigResponse:
    """Replace the active LLM provider configuration.

    The provided API key is encrypted before storage and never returned
    in plain text.  Any previously active configuration is deactivated.

    Returns:
        An ``LLMConfigResponse`` reflecting the newly persisted configuration.

    Raises:
        HTTPException 422: If the provider name is invalid (caught by Pydantic).
        HTTPException 403: If the caller is not a super admin.
    """
    try:
        logger.info("Saving LLM config: provider=%s model=%s base_url=%s key_len=%d",
                     body.provider, body.model, body.api_base_url, len(body.api_key))
        config = await update_llm_config(
            db,
            provider=body.provider,
            model=body.model,
            api_key=body.api_key,
            api_base_url=body.api_base_url,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    logger.info(
        "LLM config set: provider=%s model=%s", body.provider, body.model
    )

    return LLMConfigResponse(
        provider=config.provider.value,
        model=config.model_name,
        api_base_url=config.api_base_url,
        masked_api_key=mask_api_key(body.api_key or decrypt_api_key(config.api_key_encrypted) or "..."),
        is_active=config.is_active,
        created_at=config.created_at,
    )


# ── POST /settings/llm/test ─────────────────────────────────────────────────


@router.post(
    "/test",
    response_model=LLMConfigTestResponse,
    summary="Test active LLM provider connection",
)
async def test_llm_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: _SuperAdminDep,
) -> LLMConfigTestResponse:
    """Send a lightweight ping to the active LLM provider.

    Uses the currently active configuration (decrypting the stored API key),
    sends a minimal test prompt, and reports success or failure along with
    the measured round-trip latency.

    Returns:
        An ``LLMConfigTestResponse`` with ``success``, ``latency_ms``,
        ``message``, and ``model_used``.

    Raises:
        HTTPException 403: If the caller is not a super admin.
    """
    result = await test_llm_connection(db)

    return LLMConfigTestResponse(
        success=result["success"],
        latency_ms=result["latency_ms"],
        message=result["message"],
        model_used=result["model_used"],
    )
