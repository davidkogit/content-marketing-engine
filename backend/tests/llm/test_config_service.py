"""
Unit tests for LLMConfigService — encryption/decryption, CRUD, and validation.

Uses a real Fernet key derived from a test secret and a mocked async
database session for repository operations.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.config_service import (
    LLMConfigService,
    _derive_fernet_key,
    _get_fernet,
    decrypt_api_key,
    encrypt_api_key,
)
from app.models.llm_config import LLMConfig, LLMProvider


# ── Fixtures ────────────────────────────────────────────────────────────────

# Use a deterministic Fernet key for testing so encryption/decryption
# is consistent across test runs.
_TEST_SECRET = "a-test-secret-key-that-is-at-least-32-chars!!"


@pytest.fixture(autouse=True)
def _patch_fernet_key() -> None:
    """Override the Fernet key derivation to use a known test secret.

    This avoids dependency on real environment variables during tests.
    """
    with patch.dict(os.environ, {"SECRET_KEY": _TEST_SECRET}, clear=True):
        # Force re-initialisation of the Fernet module singleton.
        import app.llm.config_service as cs_module

        cs_module._fernet = None
        yield
        cs_module._fernet = None


@pytest.fixture
def mock_db() -> AsyncMock:
    """Return a mock AsyncSession for database operations."""
    return AsyncMock(spec=AsyncSession)


# ── Fernet Key Derivation ──────────────────────────────────────────────────


class TestFernetKeyDerivation:
    """Tests for _derive_fernet_key and _get_fernet."""

    def test_derives_key_from_secret_key(self) -> None:
        """A Fernet key should be derivable from SECRET_KEY."""
        with patch.dict(os.environ, {"SECRET_KEY": _TEST_SECRET}, clear=True):
            import app.llm.config_service as cs_module

            cs_module._fernet = None
            key = cs_module._derive_fernet_key()
            # Should be a valid Fernet key (32 bytes, base64 encoded).
            fernet = Fernet(key)
            assert isinstance(fernet, Fernet)

    def test_uses_encryption_key_when_set(self) -> None:
        """If ENCRYPTION_KEY is set, it should be used directly."""
        valid_key = Fernet.generate_key()
        with patch.dict(
            os.environ,
            {"ENCRYPTION_KEY": valid_key.decode(), "SECRET_KEY": _TEST_SECRET},
            clear=True,
        ):
            import app.llm.config_service as cs_module

            cs_module._fernet = None
            key = cs_module._derive_fernet_key()
            assert key == valid_key

    def test_raises_when_no_key_env_vars(self) -> None:
        """If neither ENCRYPTION_KEY nor SECRET_KEY is set, should raise."""
        with patch.dict(os.environ, {}, clear=True):
            import app.llm.config_service as cs_module

            cs_module._fernet = None
            with pytest.raises(RuntimeError, match="ENCRYPTION_KEY or SECRET_KEY"):
                cs_module._derive_fernet_key()

    def test_raises_on_invalid_encryption_key(self) -> None:
        """An invalid ENCRYPTION_KEY should raise a clear RuntimeError."""
        with patch.dict(os.environ, {"ENCRYPTION_KEY": "not-a-valid-fernet-key!!"}, clear=True):
            import app.llm.config_service as cs_module

            cs_module._fernet = None
            with pytest.raises(RuntimeError, match="not a valid Fernet key"):
                cs_module._derive_fernet_key()

    def test_get_fernet_returns_fernet_instance(self) -> None:
        """_get_fernet should return a configured Fernet instance."""
        with patch.dict(os.environ, {"SECRET_KEY": _TEST_SECRET}, clear=True):
            import app.llm.config_service as cs_module

            cs_module._fernet = None
            fernet = cs_module._get_fernet()
            assert isinstance(fernet, Fernet)

    def test_get_fernet_is_singleton(self) -> None:
        """Repeated calls to _get_fernet return the same instance."""
        with patch.dict(os.environ, {"SECRET_KEY": _TEST_SECRET}, clear=True):
            import app.llm.config_service as cs_module

            cs_module._fernet = None
            f1 = cs_module._get_fernet()
            f2 = cs_module._get_fernet()
            assert f1 is f2


# ── Encryption / Decryption ────────────────────────────────────────────────


class TestEncryptDecrypt:
    """Tests for encrypt_api_key and decrypt_api_key."""

    def test_roundtrip(self) -> None:
        """Encrypting then decrypting should return the original string."""
        original = "sk-proj-1234567890abcdef"
        encrypted = encrypt_api_key(original)
        assert encrypted != original
        assert len(encrypted) > 0

        decrypted = decrypt_api_key(encrypted)
        assert decrypted == original

    def test_encrypted_value_is_string(self) -> None:
        """encrypt_api_key should return a string, not bytes."""
        result = encrypt_api_key("my-api-key")
        assert isinstance(result, str)

    def test_decrypt_invalid_token_returns_none(self) -> None:
        """Decrypting garbage should return None, not raise."""
        result = decrypt_api_key("not-a-valid-fernet-token")
        assert result is None

    def test_decrypt_empty_string_returns_none(self) -> None:
        """Decrypting an empty string should return None."""
        result = decrypt_api_key("")
        assert result is None

    def test_different_keys_produce_different_tokens(self) -> None:
        """Encrypting the same plaintext twice may produce different tokens (timestamp)."""
        t1 = encrypt_api_key("secret")
        t2 = encrypt_api_key("secret")
        # Both should decrypt to the same value (but tokens may differ due to timestamp).
        assert decrypt_api_key(t1) == "secret"
        assert decrypt_api_key(t2) == "secret"


# ── LLMConfigService: Validation ───────────────────────────────────────────


class TestConfigServiceValidation:
    """Tests for provider validation."""

    def test_validate_provider_accepts_valid_names(self) -> None:
        """validate_provider should return True for openai and anthropic."""
        assert LLMConfigService.validate_provider("openai") is True
        assert LLMConfigService.validate_provider("anthropic") is True

    def test_validate_provider_case_insensitive(self) -> None:
        """Validation should be case-insensitive."""
        assert LLMConfigService.validate_provider("OPENAI") is True
        assert LLMConfigService.validate_provider("Anthropic") is True
        assert LLMConfigService.validate_provider(" openai ") is True

    def test_validate_provider_rejects_invalid(self) -> None:
        """Unsupported providers should return False."""
        assert LLMConfigService.validate_provider("cohere") is False
        assert LLMConfigService.validate_provider("") is False
        assert LLMConfigService.validate_provider("llama") is False


# ── LLMConfigService: set_config ───────────────────────────────────────────


class TestConfigServiceSetConfig:
    """Tests for LLMConfigService.set_config()."""

    async def test_set_config_encrypts_api_key(self, mock_db: AsyncMock) -> None:
        """set_config should store an encrypted API key, not the plaintext."""
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        config = await LLMConfigService.set_config(
            mock_db,
            provider="openai",
            api_key="sk-live-secret-key",
            model="gpt-4o",
        )

        # The stored value should not be the plaintext key.
        assert config.api_key_encrypted != "sk-live-secret-key"
        # It should be decryptable.
        decrypted = decrypt_api_key(config.api_key_encrypted)
        assert decrypted == "sk-live-secret-key"

    async def test_set_config_marks_active(self, mock_db: AsyncMock) -> None:
        """By default, the new config should be marked as active."""
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        config = await LLMConfigService.set_config(
            mock_db,
            provider="anthropic",
            api_key="sk-ant-key",
            model="claude-3-opus",
        )
        assert config.is_active is True

    async def test_set_config_deactivates_others(self, mock_db: AsyncMock) -> None:
        """Existing active configs should be deactivated when adding new ones."""
        # Simulate one existing active config.
        existing = MagicMock(spec=LLMConfig)
        existing.is_active = True
        mock_db.execute.return_value.scalars.return_value.all.return_value = [existing]

        config = await LLMConfigService.set_config(
            mock_db,
            provider="openai",
            api_key="new-key",
            model="gpt-4o-mini",
        )
        # The existing config should have been deactivated.
        assert existing.is_active is False

    async def test_set_config_invalid_provider_raises(self, mock_db: AsyncMock) -> None:
        """An unsupported provider name should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid provider"):
            await LLMConfigService.set_config(
                mock_db,
                provider="invalid-provider",
                api_key="key",
                model="model",
            )


# ── LLMConfigService: get_active_config ────────────────────────────────────


class TestConfigServiceGetActive:
    """Tests for LLMConfigService.get_active_config()."""

    async def test_returns_none_when_no_active(self, mock_db: AsyncMock) -> None:
        """If no active config exists, get_active_config should return None."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        result = await LLMConfigService.get_active_config(mock_db)
        assert result is None

    async def test_returns_active_config(self, mock_db: AsyncMock) -> None:
        """If an active config exists, it should be returned."""
        config = LLMConfig(
            id=1,
            provider=LLMProvider.OPENAI,
            api_key_encrypted=encrypt_api_key("sk-test"),
            model_name="gpt-4o",
            is_active=True,
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = config

        result = await LLMConfigService.get_active_config(mock_db)
        assert result is config
        assert result.provider == LLMProvider.OPENAI
        assert result.is_active is True


# ── LLMConfigService: get_config_by_id ─────────────────────────────────────


class TestConfigServiceGetById:
    """Tests for LLMConfigService.get_config_by_id()."""

    async def test_returns_config_when_found(self, mock_db: AsyncMock) -> None:
        """Should return the config matching the given ID."""
        config = LLMConfig(id=42, provider=LLMProvider.ANTHROPIC, api_key_encrypted="enc", model_name="claude", is_active=False)
        mock_db.execute.return_value.scalar_one_or_none.return_value = config

        result = await LLMConfigService.get_config_by_id(mock_db, 42)
        assert result is config
        assert result.id == 42

    async def test_returns_none_when_not_found(self, mock_db: AsyncMock) -> None:
        """Should return None for nonexistent IDs."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        result = await LLMConfigService.get_config_by_id(mock_db, 999)
        assert result is None


# ── LLMConfigService: deactivate_config ────────────────────────────────────


class TestConfigServiceDeactivate:
    """Tests for LLMConfigService.deactivate_config()."""

    async def test_deactivates_existing_config(self, mock_db: AsyncMock) -> None:
        """Should set is_active to False on the matching config."""
        config = LLMConfig(id=1, provider=LLMProvider.OPENAI, api_key_encrypted="enc", model_name="gpt-4o", is_active=True)
        mock_db.execute.return_value.scalar_one_or_none.return_value = config

        result = await LLMConfigService.deactivate_config(mock_db, 1)
        assert result is True
        assert config.is_active is False

    async def test_returns_false_when_not_found(self, mock_db: AsyncMock) -> None:
        """Should return False if no config matches the ID."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        result = await LLMConfigService.deactivate_config(mock_db, 999)
        assert result is False


# ── Encryption Integration Test ─────────────────────────────────────────────


class TestEncryptionIntegration:
    """Integration-style test: encrypt → store → retrieve → decrypt."""

    async def test_full_encryption_cycle(self, mock_db: AsyncMock) -> None:
        """Simulate the full lifecycle of storing and retrieving an encrypted key."""
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        # 1. Set a config (encrypts API key).
        config = await LLMConfigService.set_config(
            mock_db,
            provider="openai",
            api_key="sk-original-plaintext",
            model="gpt-4o",
        )

        # 2. The stored value is encrypted.
        assert config.api_key_encrypted != "sk-original-plaintext"

        # 3. Getting the config back and decrypting returns the plaintext.
        mock_db.execute.return_value.scalar_one_or_none.return_value = config
        retrieved = await LLMConfigService.get_active_config(mock_db)
        assert retrieved is not None
        decrypted = decrypt_api_key(retrieved.api_key_encrypted)
        assert decrypted == "sk-original-plaintext"
