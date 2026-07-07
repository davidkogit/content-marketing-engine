"""
Generation orchestrator — coordinates the full LLM content-generation pipeline.

Collects RAG context → builds prompts → calls the configured LLM provider →
post-processes the response → returns a structured ``GeneratedResponse``.

Also provides an async task management layer for background generation with
timeout handling and status polling.
"""


import asyncio
import logging
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.config_service import LLMConfigService, decrypt_api_key
from app.llm.context_collector import ContextCollector, GenerationContext
from app.llm.generation_schemas import (
    GeneratedResponse,
    GenerationMetadata,
    GenerationType,
    TaskStatus,
    TaskStatusResponse,
)
from app.llm.post_processor import PostProcessor
from app.llm.prompt_builder import PromptBuilder
from app.llm.provider_base import LLMProviderError, LLMResponse
from app.llm.provider_factory import get_provider

logger = logging.getLogger(__name__)

# ── Generation instructions per type ─────────────────────────────────────────

_GENERATION_INSTRUCTIONS: dict[GenerationType, str] = {
    GenerationType.PRODUCT_DESCRIPTION: (
        "Write a compelling product description (2–3 paragraphs) that highlights "
        "key features, benefits, and differentiators. Use the source documents "
        "for factual accuracy. Anchor every factual claim to a specific source "
        "document by citing it."
    ),
    GenerationType.FEATURE_BULLETS: (
        "Generate a bulleted list of 5–8 key product features. Each bullet should "
        "be a single concise sentence grounded in the source documents. Include "
        "the most impactful, differentiating features first."
    ),
    GenerationType.SOCIAL_POST: (
        "Write a single social media post (max 280 characters / 2 short sentences) "
        "that is attention-grabbing and shareable. Focus on one hero feature or "
        "benefit. Include a call-to-action."
    ),
    GenerationType.TAGLINE: (
        "Generate 3 compelling tagline options for this product. Each should be "
        "short (under 10 words), memorable, and reflect the brand tone. Include "
        "a one-line explanation for why each tagline works."
    ),
    GenerationType.SEO_META: (
        "Generate an SEO-optimised meta title (max 60 chars) and meta description "
        "(max 160 chars) for this product. Include primary keywords naturally. "
        "The meta description should be a persuasive teaser that drives click-through."
    ),
    GenerationType.EMAIL_BLAST: (
        "Write a short email marketing blast (subject line + body, 2–3 short paragraphs) "
        "to promote this product. The subject line should be compelling and under 50 "
        "characters. The body should include a clear benefit statement and a call-to-action."
    ),
}

# ── In-memory task store ─────────────────────────────────────────────────────

# Maps task_id → (status, result | error)
_task_store: dict[str, dict[str, Any]] = {}

# Time-to-live for completed/failed task entries (seconds)
_TASK_TTL = 3600  # 1 hour

# ── Background cleanup of expired tasks ──────────────────────────────────────

_cleanup_task: asyncio.Task | None = None
"""Module-level reference to the background cleanup task."""


async def _cleanup_expired_tasks() -> None:
    """Periodically remove completed/failed tasks older than _TASK_TTL."""
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        now = time.time()
        expired = [
            task_id
            for task_id, entry in _task_store.items()
            if entry["status"] in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            and (now - entry.get("created_at", 0)) > _TASK_TTL
        ]
        for task_id in expired:
            del _task_store[task_id]
        if expired:
            logger.debug("Cleaned up %d expired task(s) from store", len(expired))


def _ensure_cleanup_running() -> None:
    """Start the background cleanup task if not already running."""
    global _cleanup_task
    if _cleanup_task is None:
        try:
            loop = asyncio.get_running_loop()
            _cleanup_task = loop.create_task(_cleanup_expired_tasks())
            logger.debug("Background TTL cleanup task started")
        except RuntimeError:
            # No event loop running yet — will be retried on first async call
            pass


# ── GenerationOrchestrator ───────────────────────────────────────────────────


class GenerationOrchestrator:
    """Orchestrates the full content generation pipeline.

    Coordinates context collection, prompt building, LLM invocation,
    post-processing, and output structuring.  Supports both synchronous
    (inline) and asynchronous (background task) execution.

    Usage::

        orchestrator = GenerationOrchestrator()
        result = await orchestrator.generate(db, product_id=42, gen_type=GenerationType.PRODUCT_DESCRIPTION)
    """

    _GENERATION_TIMEOUT_S = 120

    def __init__(self, rules_dir: str | None = None) -> None:
        """Initialise the orchestrator.

        Args:
            rules_dir: Optional path to brand rules directory.
        """
        self._collector = ContextCollector(rules_dir=rules_dir)
        self._prompt_builder = PromptBuilder()
        self._post_processor = PostProcessor()

    # ── Public: generate ─────────────────────────────────────────────────

    async def generate(
        self,
        db: AsyncSession,
        *,
        product_id: int,
        gen_type: GenerationType = GenerationType.PRODUCT_DESCRIPTION,
    ) -> GeneratedResponse:
        """Run the full generation pipeline and return a structured result.

        Args:
            db: Active async database session.
            product_id: The product to generate content for.
            gen_type: The type of content to generate.

        Returns:
            A fully-processed ``GeneratedResponse``.

        Raises:
            asyncio.TimeoutError: If generation exceeds the timeout.
            LLMProviderError: If the LLM call fails.
            ValueError: If no LLM provider is configured.
        """
        t_start = time.monotonic()

        # 1. Collect RAG context
        context = await self._collector.collect(db, product_id)
        logger.info(
            "Context collected for product_id=%d: %d docs, segment=%s",
            product_id,
            len(context.source_documents),
            context.segment_profile.get("tone") or "(none)",
        )

        # 2. Build prompts
        instruction = _GENERATION_INSTRUCTIONS.get(
            gen_type, _GENERATION_INSTRUCTIONS[GenerationType.PRODUCT_DESCRIPTION]
        )
        system_prompt = self._prompt_builder.build_system_prompt(context)
        user_prompt = self._prompt_builder.build_user_prompt(context, instruction)

        # 3. Get LLM provider
        provider = await self.resolve_provider(db)

        # 4. Call LLM with timeout
        llm_response = await self._call_llm_with_timeout(
            provider,
            prompt=user_prompt,
            system_prompt=system_prompt,
        )

        # 5. Post-process
        metadata = GenerationMetadata(
            model=llm_response.model_used,
            tokens=llm_response.tokens_used,
            latency=round(llm_response.latency_ms, 2),
        )

        result = self._post_processor.process(
            raw_response=llm_response.content,
            brand_rules=context.brand_rules,
            source_documents=context.source_documents,
            metadata=metadata,
        )

        # 6. Persist claims for audit trail
        await self._persist_claims(db, product_id, result.claims)

        elapsed_ms = (time.monotonic() - t_start) * 1000
        logger.info(
            "Generation complete for product_id=%d type=%s: %d tokens, %.0fms",
            product_id,
            gen_type.value,
            llm_response.tokens_used,
            elapsed_ms,
        )

        return result

    # ── Public: generate_async (background) ───────────────────────────────

    async def generate_async(
        self,
        db_factory,
        *,
        product_id: int,
        gen_type: GenerationType = GenerationType.PRODUCT_DESCRIPTION,
    ) -> str:
        """Start generation in the background and return a task_id.

        The caller can poll status via ``get_task_status(task_id)``.

        Args:
            db_factory: A callable that returns an ``AsyncSession`` (e.g. ``get_db``).
            product_id: The product to generate content for.
            gen_type: The type of content to generate.

        Returns:
            A unique ``task_id`` string for status polling.
        """
        task_id = str(uuid.uuid4())
        _task_store[task_id] = {"status": TaskStatus.PENDING, "result": None, "error": None, "created_at": time.time()}

        # Ensure the background TTL cleanup coroutine is running
        _ensure_cleanup_running()

        # Schedule background execution
        asyncio.create_task(
            self._run_background(task_id, db_factory, product_id, gen_type)
        )

        logger.info(
            "Async generation task created: task_id=%s product_id=%d type=%s",
            task_id,
            product_id,
            gen_type.value,
        )
        return task_id

    # ── Public: task status ──────────────────────────────────────────────

    @staticmethod
    def get_task_status(task_id: str) -> TaskStatusResponse:
        """Retrieve the current status of an async generation task.

        Args:
            task_id: The task identifier returned by ``generate_async``.

        Returns:
            A ``TaskStatusResponse`` with current status and result/error
            when available.

        Raises:
            KeyError: If the task_id is not found.
        """
        entry = _task_store.get(task_id)
        if entry is None:
            raise KeyError(f"Task not found: {task_id}")

        return TaskStatusResponse(
            task_id=task_id,
            status=entry["status"],
            result=entry["result"],
            error=entry["error"],
        )

    # ── Internal helpers ─────────────────────────────────────────────────

    async def _run_background(
        self,
        task_id: str,
        db_factory,
        product_id: int,
        gen_type: GenerationType,
    ) -> None:
        """Execute the generation pipeline in the background."""
        _task_store[task_id]["status"] = TaskStatus.RUNNING
        try:
            async for session in db_factory():
                try:
                    result = await self.generate(
                        session, product_id=product_id, gen_type=gen_type
                    )
                    _task_store[task_id]["status"] = TaskStatus.COMPLETED
                    _task_store[task_id]["result"] = result
                finally:
                    await session.close()
                break  # Only one session needed
        except asyncio.TimeoutError:
            _task_store[task_id]["status"] = TaskStatus.FAILED
            _task_store[task_id]["error"] = "Generation timed out after 120 seconds."
            logger.error("Task %s timed out", task_id)
        except LLMProviderError as exc:
            _task_store[task_id]["status"] = TaskStatus.FAILED
            _task_store[task_id]["error"] = f"LLM provider error: {exc}"
            logger.error("Task %s failed with LLM error: %s", task_id, exc)
        except Exception as exc:
            _task_store[task_id]["status"] = TaskStatus.FAILED
            _task_store[task_id]["error"] = f"Unexpected error: {exc}"
            logger.exception("Task %s failed unexpectedly", task_id)

    @staticmethod
    async def _persist_claims(
        db: AsyncSession,
        product_id: int,
        claims: list,
    ) -> None:
        """Persist extracted claims to the product_claims table for audit trail.

        Each claim is saved as a ``ProductClaim`` row linked to the product.
        Claims without a source anchor are still persisted (source_doc_id=None).

        Args:
            db: Active database session.
            product_id: The product the claims belong to.
            claims: List of ``ExtractedClaim`` objects from the post-processor.
        """
        if not claims:
            return

        from app.models.product_claim import ClaimStatus, ProductClaim

        count = 0
        for claim in claims:
            pc = ProductClaim(
                product_id=product_id,
                claim_text=claim.text,
                source_doc_id=claim.source_doc_id,
                status=ClaimStatus.PENDING_REVIEW,
            )
            db.add(pc)
            count += 1

        await db.commit()
        logger.info(
            "Persisted %d claims for product_id=%d to audit trail",
            count,
            product_id,
        )

    @staticmethod
    async def resolve_provider(db: AsyncSession):
        """Resolve the active LLM provider from configuration.

        Args:
            db: Active database session.

        Returns:
            A configured ``LLMProvider`` instance.

        Raises:
            ValueError: If no active LLM config is found or API key is missing.
        """
        config = await LLMConfigService.get_active_config(db)
        if config is None:
            raise ValueError(
                "No active LLM provider configured. "
                "A super_admin must set up an LLM provider in Settings."
            )

        api_key = decrypt_api_key(config.api_key_encrypted)
        if not api_key:
            raise ValueError(
                "Failed to decrypt the LLM API key. "
                "The encryption key may have been rotated — re-enter the API key in Settings."
            )

        return get_provider(
            provider_name=config.provider.value,
            api_key=api_key,
            model=config.model_name,
            api_base_url=config.api_base_url,
        )

    async def _call_llm_with_timeout(
        self,
        provider,
        *,
        prompt: str,
        system_prompt: str,
    ) -> LLMResponse:
        """Call the LLM provider with a hard timeout.

        Args:
            provider: Configured LLM provider instance.
            prompt: The user prompt to send.
            system_prompt: The system prompt (persona instructions).

        Returns:
            The raw ``LLMResponse`` from the provider.

        Raises:
            asyncio.TimeoutError: If the call exceeds ``_GENERATION_TIMEOUT_S``.
            LLMProviderError: Propagated from the provider on failure.
        """
        return await asyncio.wait_for(
            provider.generate(prompt, system_prompt=system_prompt),
            timeout=self._GENERATION_TIMEOUT_S,
        )
