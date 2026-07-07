"""
LLM configuration service with Fernet-based API key encryption.

Provides read/write access to the ``llm_config`` database table with
automatic encryption of API keys before storage and decryption on read.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_config import LLMConfig, LLMProvider

logger = logging.getLogger(__name__)

# ── Key Derivation ──────────────────────────────────────────────────────────
# Fernet requires a 32-byte, URL-safe-base64-encoded key.
# We derive this from the ENCRYPTION_KEY or SECRET_KEY env var.


def _derive_fernet_key() -> bytes:
    """Derive a Fernet-compatible 32-byte key from environment variables.

    Precedence:
    1. ``ENCRYPTION_KEY`` env var (must already be a valid Fernet key).
    2. ``SECRET_KEY`` env var → SHA-256 hash → base64url-encoded.

    Returns:
        A 32-byte URL-safe base64-encoded key suitable for ``Fernet()``.

    Raises:
        RuntimeError: If neither env var is set.
    """
    encryption_key = os.getenv("ENCRYPTION_KEY")
    if encryption_key:
        # Validate that the provided key is usable by Fernet.
        try:
            Fernet(encryption_key.encode())
            return encryption_key.encode()
        except Exception as exc:
            raise RuntimeError(
                "ENCRYPTION_KEY is set but is not a valid Fernet key. "
                "Generate one with: python -c "
                "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            ) from exc

    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "Either ENCRYPTION_KEY or SECRET_KEY must be set to encrypt LLM API keys."
        )

    # Derive a deterministic 32-byte key from the SECRET_KEY.
    digest: bytes = hashlib.sha256(secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


# ── Fernet instance (lazy initialised) ──────────────────────────────────────

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Return the module-level Fernet instance, initialising on first call."""
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_derive_fernet_key())
    return _fernet


# ── Encryption helpers ─────────────────────────────────────────────────────


def encrypt_api_key(plain_text: str) -> str:
    """Encrypt an API key for storage.

    Args:
        plain_text: The raw API key string.

    Returns:
        A Fernet-encrypted token as a string.
    """
    fernet = _get_fernet()
    token: bytes = fernet.encrypt(plain_text.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_api_key(encrypted: str) -> str | None:
    """Decrypt a stored API key.

    Args:
        encrypted: The Fernet-encrypted token.

    Returns:
        The decrypted API key, or ``None`` if the token is invalid
        or the encryption key has been rotated.
    """
    fernet = _get_fernet()
    try:
        plain: bytes = fernet.decrypt(encrypted.encode("utf-8"))
        return plain.decode("utf-8")
    except InvalidToken:
        logger.error("Failed to decrypt API key — token may be invalid or key rotated.")
        return None


# ── LLM Config Service ─────────────────────────────────────────────────────


class LLMConfigService:
    """Service for managing persisted LLM provider configurations.

    Encrypts API keys automatically before storing them in the database
    and decrypts on retrieval.
    """

    # ── Read ────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_active_config(db: AsyncSession) -> LLMConfig | None:
        """Retrieve the currently active LLM configuration.

        Args:
            db: An active async database session.

        Returns:
            The active ``LLMConfig`` row, or ``None`` if none is marked active.
        """
        result = await db.execute(
            select(LLMConfig).where(LLMConfig.is_active.is_(True)).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_config_by_id(db: AsyncSession, config_id: int) -> LLMConfig | None:
        """Retrieve a specific configuration by primary key."""
        result = await db.execute(select(LLMConfig).where(LLMConfig.id == config_id))
        return result.scalar_one_or_none()

    # ── Write ───────────────────────────────────────────────────────────────

    @staticmethod
    async def set_config(
        db: AsyncSession,
        *,
        provider: str,
        api_key: str,
        model: str,
        make_active: bool = True,
    ) -> LLMConfig:
        """Persist a new LLM configuration, encrypting the API key first.

        Args:
            db: An active async database session.
            provider: ``openai`` or ``anthropic`` (must be a valid LLMProvider member).
            api_key: The raw (plain-text) API key to encrypt and store.
            model: Model identifier (e.g. ``gpt-4o``).
            make_active: If ``True``, deactivate all other configs and mark
                         this one as the active configuration.

        Returns:
            The newly created (and flushed) ``LLMConfig`` row.

        Raises:
            ValueError: If ``provider`` is not a supported ``LLMProvider``.
        """
        llm_provider = LLMConfigService._validate_provider_enum(provider)

        if make_active:
            await LLMConfigService._deactivate_all(db)

        encrypted = encrypt_api_key(api_key)

        config = LLMConfig(
            provider=llm_provider,
            api_key_encrypted=encrypted,
            model_name=model,
            is_active=make_active,
        )
        db.add(config)
        await db.flush()
        await db.refresh(config)

        logger.info(
            "LLM config saved: provider=%s model=%s active=%s",
            provider,
            model,
            make_active,
        )
        return config

    @staticmethod
    async def deactivate_config(db: AsyncSession, config_id: int) -> bool:
        """Set a configuration to inactive.

        Returns ``True`` if a row was updated, ``False`` if no row matched.
        """
        config = await LLMConfigService.get_config_by_id(db, config_id)
        if config is None:
            return False
        config.is_active = False
        await db.flush()
        return True

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def validate_provider(provider_name: str) -> bool:
        """Check whether a provider name string is valid."""
        return _is_valid_provider(provider_name)

    @staticmethod
    def _validate_provider_enum(provider_name: str) -> LLMProvider:
        """Convert a provider name to its enum variant, raising on invalid."""
        try:
            return LLMProvider(provider_name.lower().strip())
        except ValueError as exc:
            allowed = ", ".join(p.value for p in LLMProvider)
            raise ValueError(
                f"Invalid provider {provider_name!r}. Choose from: {allowed}"
            ) from exc

    @staticmethod
    async def _deactivate_all(db: AsyncSession) -> None:
        """Set ``is_active = False`` for every row in the llm_config table."""
        configs = await db.execute(select(LLMConfig).where(LLMConfig.is_active.is_(True)))
        for config in configs.scalars().all():
            config.is_active = False
        await db.flush()


def _is_valid_provider(provider_name: str) -> bool:
    """Check whether a string corresponds to a valid LLMProvider enum value."""
    try:
        LLMProvider(provider_name.lower().strip())
        return True
    except ValueError:
        return False
