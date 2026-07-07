"""
Generation API router — endpoints for triggering and monitoring LLM content
generation.

Mounts under ``/api/v1/generate`` and exposes:

- ``POST /api/generate/{product_id}`` — triggers generation (editor+),
  returns 202 Accepted with a task_id for async polling.
- ``GET  /api/generate/status/{task_id}`` — polls the status of an async task.
"""


import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.schemas import RoleDTO
from app.database import get_db
from app.llm.generation_schemas import (
    GenerateRequest,
    GeneratedResponse,
    TaskStatusResponse,
)
from app.llm.orchestrator import GenerationOrchestrator
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["generation"])

# ── Singleton ───────────────────────────────────────────────────────────────

_orchestrator = GenerationOrchestrator()


# ── POST /api/generate/{product_id} ──────────────────────────────────────────


@router.post(
    "/{product_id}",
    response_model=GeneratedResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate marketing content for a product (synchronous)",
)
async def generate_content_sync(
    product_id: int,
    body: GenerateRequest = GenerateRequest(),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[User, Depends(require_role(RoleDTO.EDITOR))] = None,
) -> GeneratedResponse:
    """Run the full content generation pipeline synchronously.

    Collects product context, builds prompts, calls the configured LLM
    provider, post-processes the response, and returns a structured result
    with claims, sources, violations, and generation metadata.

    **Requires editor role or higher.**
    **Timeout: 120 seconds.**

    Raises:
        400: If no LLM provider is configured.
        500: If the LLM call fails or times out.
        404: If the product is not found.
    """
    try:
        result = await _orchestrator.generate(
            db,
            product_id=product_id,
            gen_type=body.generation_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM generation timed out after 120 seconds. Try again or split the request.",
        )
    except Exception as exc:
        logger.exception("Generation failed for product_id=%d", product_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Content generation failed: {exc}",
        )

    logger.info(
        "Sync generation complete: product_id=%d type=%s user_id=%d",
        product_id,
        body.generation_type.value,
        current_user.id,
    )
    return result


# ── POST /api/generate/async/{product_id} ────────────────────────────────────


@router.post(
    "/async/{product_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger async content generation (returns task_id for polling)",
    response_model=dict,
)
async def generate_content_async(
    product_id: int,
    body: GenerateRequest = GenerateRequest(),
    current_user: Annotated[User, Depends(require_role(RoleDTO.EDITOR))] = None,
) -> dict:
    """Start content generation in the background.

    Returns a ``task_id`` immediately.  Poll ``GET /api/generate/status/{task_id}``
    to check completion and retrieve results.

    **Requires editor role or higher.**

    Returns:
        ``{"task_id": "<uuid>", "status": "pending"}`` with HTTP 202.
    """
    from app.database import AsyncSessionFactory

    task_id = await _orchestrator.generate_async(
        db_factory=lambda: _session_factory_context(AsyncSessionFactory),
        product_id=product_id,
        gen_type=body.generation_type,
    )

    logger.info(
        "Async generation queued: task_id=%s product_id=%d type=%s user_id=%d",
        task_id,
        product_id,
        body.generation_type.value,
        current_user.id,
    )

    return {"task_id": task_id, "status": "pending"}


# ── GET /api/generate/status/{task_id} ───────────────────────────────────────


@router.get(
    "/status/{task_id}",
    response_model=TaskStatusResponse,
    summary="Poll the status of an async generation task",
)
async def get_generation_status(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> TaskStatusResponse:
    """Check the status of a previously submitted async generation task.

    Returns ``status`` of ``pending``, ``running``, ``completed`` (with
    ``result``), or ``failed`` (with ``error``).

    Raises:
        404: If the task_id is not found (may have expired after 1 hour).
    """
    try:
        return _orchestrator.get_task_status(task_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {task_id}. Tasks expire after 1 hour.",
        )


# ── Helper ──────────────────────────────────────────────────────────────────


async def _session_factory_context(session_factory):
    """Yield a single database session from a factory for background tasks.

    Used to bridge the async session factory into the orchestrator's
    background execution context.
    """
    async with session_factory() as session:
        yield session
