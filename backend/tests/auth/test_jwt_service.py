"""
Unit tests for the JWT token creation and verification service.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth.jwt_service import (
    JWTService,
    TokenError,
    TokenExpiredError,
    TokenInvalidError,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def service() -> JWTService:
    """Return a JWTService with a known test secret."""
    return JWTService(
        secret_key="test-secret-key-with-minimum-32-chars!!",
        access_token_expiry_minutes=30,
        refresh_token_expiry_days=7,
    )


@pytest.fixture
def token_payload() -> dict:
    """Canonical user data for access token creation."""
    return {
        "user_id": 42,
        "email": "user@example.com",
        "role": "editor",
    }


# ── Access Token Creation ──────────────────────────────────────────────────


class TestCreateAccessToken:
    """Tests for create_access_token."""

    async def test_returns_string(self, service: JWTService) -> None:
        """create_access_token should return a string JWT."""
        token = await service.create_access_token(
            user_id=1, email="a@b.com", role="viewer"
        )
        assert isinstance(token, str)
        assert token.count(".") == 2  # standard JWT has 3 segments

    async def test_includes_required_claims(
        self, service: JWTService, token_payload: dict
    ) -> None:
        """Decoded token should contain user_id, email, role, and type claims."""
        token = await service.create_access_token(**token_payload)
        decoded = jwt.decode(
            token,
            "test-secret-key-with-minimum-32-chars!!",
            algorithms=["HS256"],
        )
        assert decoded["user_id"] == token_payload["user_id"]
        assert decoded["email"] == token_payload["email"]
        assert decoded["role"] == token_payload["role"]
        assert decoded["type"] == "access"

    async def test_includes_sub_claim(
        self, service: JWTService, token_payload: dict
    ) -> None:
        """The ``sub`` claim should be the string representation of user_id."""
        token = await service.create_access_token(**token_payload)
        decoded = jwt.decode(
            token,
            "test-secret-key-with-minimum-32-chars!!",
            algorithms=["HS256"],
        )
        assert decoded["sub"] == str(token_payload["user_id"])

    async def test_includes_expiry_claims(
        self, service: JWTService, token_payload: dict
    ) -> None:
        """Token should have both ``iat`` (issued-at) and ``exp`` (expiry) claims."""
        token = await service.create_access_token(**token_payload)
        decoded = jwt.decode(
            token,
            "test-secret-key-with-minimum-32-chars!!",
            algorithms=["HS256"],
        )
        assert "iat" in decoded
        assert "exp" in decoded
        # ``exp`` should be approximately 30 minutes after ``iat``
        iat = datetime.fromtimestamp(decoded["iat"], tz=timezone.utc)
        exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        assert exp - iat == timedelta(minutes=30)

    async def test_extra_claims_are_merged(self, service: JWTService) -> None:
        """Extra claims passed via keyword should appear in the decoded payload."""
        token = await service.create_access_token(
            user_id=1, email="a@b.com", role="viewer",
            extra_claims={"custom": "value", "scope": "admin"},
        )
        decoded = jwt.decode(
            token,
            "test-secret-key-with-minimum-32-chars!!",
            algorithms=["HS256"],
        )
        assert decoded["custom"] == "value"
        assert decoded["scope"] == "admin"


# ── Refresh Token Creation ─────────────────────────────────────────────────


class TestCreateRefreshToken:
    """Tests for create_refresh_token."""

    async def test_returns_string(self, service: JWTService) -> None:
        """create_refresh_token should return a string JWT."""
        token = await service.create_refresh_token(user_id=42)
        assert isinstance(token, str)
        assert token.count(".") == 2

    async def test_includes_required_claims(self, service: JWTService) -> None:
        """Decoded refresh token should have user_id, type, and token_version."""
        token = await service.create_refresh_token(user_id=42, token_version=3)
        decoded = jwt.decode(
            token,
            "test-secret-key-with-minimum-32-chars!!",
            algorithms=["HS256"],
        )
        assert decoded["user_id"] == 42
        assert decoded["type"] == "refresh"
        assert decoded["token_version"] == 3

    async def test_default_token_version_is_zero(self, service: JWTService) -> None:
        """If not specified, token_version should default to 0."""
        token = await service.create_refresh_token(user_id=42)
        decoded = jwt.decode(
            token,
            "test-secret-key-with-minimum-32-chars!!",
            algorithms=["HS256"],
        )
        assert decoded["token_version"] == 0

    async def test_longer_expiry_than_access(self, service: JWTService) -> None:
        """Refresh token should expire in 7 days, not 30 minutes."""
        token = await service.create_refresh_token(user_id=42)
        decoded = jwt.decode(
            token,
            "test-secret-key-with-minimum-32-chars!!",
            algorithms=["HS256"],
        )
        iat = datetime.fromtimestamp(decoded["iat"], tz=timezone.utc)
        exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        assert exp - iat == timedelta(days=7)


# ── Token Verification (Happy Path) ────────────────────────────────────────


class TestVerifyTokenHappy:
    """Happy-path tests for verify_token and decode_token."""

    async def test_verify_token_returns_payload(
        self, service: JWTService, token_payload: dict
    ) -> None:
        """verify_token should return the decoded payload for a valid token."""
        token = await service.create_access_token(**token_payload)
        payload = await service.verify_token(token)
        assert payload["user_id"] == token_payload["user_id"]
        assert payload["email"] == token_payload["email"]
        assert payload["role"] == token_payload["role"]

    async def test_decode_token_returns_same_as_verify(
        self, service: JWTService, token_payload: dict
    ) -> None:
        """decode_token and verify_token should return identical results."""
        token = await service.create_access_token(**token_payload)
        via_verify = await service.verify_token(token)
        via_decode = await service.decode_token(token)
        assert via_verify == via_decode

    async def test_verify_refresh_token(self, service: JWTService) -> None:
        """verify_token should also work on refresh tokens."""
        token = await service.create_refresh_token(user_id=42, token_version=1)
        payload = await service.verify_token(token)
        assert payload["user_id"] == 42
        assert payload["type"] == "refresh"
        assert payload["token_version"] == 1


# ── Token Verification (Expiry) ────────────────────────────────────────────


class TestVerifyTokenExpired:
    """Tests for expired token rejection."""

    async def test_expired_access_token_raises(self) -> None:
        """A token past its expiry should raise TokenExpiredError."""
        # Create a service with a tiny expiry and immediately-expired token
        svc = JWTService(
            secret_key="test-secret-key-with-minimum-32-chars!!",
            access_token_expiry_minutes=0,  # zero-minute lifetime
        )
        token = await svc.create_access_token(user_id=1, email="a@b.com", role="viewer")
        # The token was just created with a zero-minute expiry — it should
        # already be expired (within clock-skew tolerance). Force a tiny delay.
        time.sleep(0.01)  # ensure we are past the expiry boundary

        with pytest.raises(TokenExpiredError, match="expired"):
            await svc.verify_token(token)

    async def test_expired_refresh_token_raises(self) -> None:
        """An expired refresh token should also raise TokenExpiredError."""
        svc = JWTService(
            secret_key="test-secret-key-with-minimum-32-chars!!",
            refresh_token_expiry_days=0,  # zero-day lifetime
        )
        token = await svc.create_refresh_token(user_id=1)
        time.sleep(0.01)

        with pytest.raises(TokenExpiredError, match="expired"):
            await svc.verify_token(token)

    async def test_expired_token_is_base_token_error(self) -> None:
        """TokenExpiredError should be a subclass of TokenError."""
        svc = JWTService(
            secret_key="test-secret-key-with-minimum-32-chars!!",
            access_token_expiry_minutes=0,
        )
        token = await svc.create_access_token(user_id=1, email="a@b.com", role="viewer")
        time.sleep(0.01)

        with pytest.raises(TokenError):
            await svc.verify_token(token)

    async def test_valid_token_does_not_raise(
        self, service: JWTService, token_payload: dict
    ) -> None:
        """A freshly-created token with normal expiry should verify cleanly."""
        token = await service.create_access_token(**token_payload)
        payload = await service.verify_token(token)
        assert payload["user_id"] == token_payload["user_id"]


# ── Token Verification (Tampered / Invalid) ───────────────────────────────


class TestVerifyTokenTampered:
    """Tests for tampered and malformed token rejection."""

    _SECRET = "test-secret-key-with-minimum-32-chars!!"

    async def test_tampered_payload_raises(self, service: JWTService) -> None:
        """Modifying the payload after signing should raise TokenInvalidError."""
        token = await service.create_access_token(
            user_id=1, email="a@b.com", role="viewer"
        )
        # Tamper: decode the payload, modify it, re-encode, keep original signature
        header, payload, sig = token.split(".")

        payload_bytes = base64.urlsafe_b64decode(payload + "==")
        payload_dict = json.loads(payload_bytes)
        payload_dict["user_id"] = 999
        payload_dict["role"] = "super_admin"

        new_payload = (
            base64.urlsafe_b64encode(json.dumps(payload_dict).encode())
            .rstrip(b"=")
            .decode()
        )
        tampered_token = f"{header}.{new_payload}.{sig}"

        with pytest.raises(TokenInvalidError, match="signature"):
            await service.verify_token(tampered_token)

    async def test_tampered_signature_raises(self, service: JWTService) -> None:
        """Flipping a bit in the signature should raise TokenInvalidError."""
        token = await service.create_access_token(
            user_id=1, email="a@b.com", role="viewer"
        )
        # Flip the last character of the signature
        segments = token.split(".")
        sig = list(segments[2])
        sig[-1] = "A" if sig[-1] != "A" else "B"
        segments[2] = "".join(sig)
        tampered_token = ".".join(segments)

        with pytest.raises(TokenInvalidError, match="signature"):
            await service.verify_token(tampered_token)

    async def test_garbled_token_raises(self, service: JWTService) -> None:
        """A completely random string should raise TokenInvalidError."""
        with pytest.raises(TokenInvalidError, match="malformed"):
            await service.verify_token("not-a-valid-jwt-at-all")

    async def test_empty_token_raises(self, service: JWTService) -> None:
        """An empty string should raise TokenInvalidError."""
        with pytest.raises(TokenInvalidError, match="malformed"):
            await service.verify_token("")

    async def test_different_secret_raises(self, token_payload: dict) -> None:
        """A token signed with one secret should be rejected by another."""
        svc_a = JWTService(
            secret_key="aaaa-secret-key-with-minimum-32-chars!!",
        )
        svc_b = JWTService(
            secret_key="bbbb-secret-key-with-minimum-32-chars!!",
        )
        token = await svc_a.create_access_token(**token_payload)

        with pytest.raises(TokenInvalidError, match="signature"):
            await svc_b.verify_token(token)

    async def test_truncated_token_raises(self, service: JWTService) -> None:
        """A token with only one segment (no signature) should raise TokenInvalidError."""
        truncated = jwt.encode(
            {"user_id": 1, "email": "a@b.com", "role": "viewer"},
            self._SECRET,
            algorithm="HS256",
        ).split(".")[0]

        with pytest.raises(TokenInvalidError, match="malformed"):
            await service.verify_token(truncated)

    async def test_tampered_token_is_base_token_error(
        self, service: JWTService
    ) -> None:
        """TokenInvalidError should be a subclass of TokenError."""
        with pytest.raises(TokenError):
            await service.verify_token("not-a-jwt")


# ── Configurability ────────────────────────────────────────────────────────


class TestConfigurability:
    """Tests that constructor parameters are respected."""

    async def test_custom_access_expiry(self) -> None:
        """Service should honour access_token_expiry_minutes."""
        svc = JWTService(
            secret_key="test-secret-key-with-minimum-32-chars!!",
            access_token_expiry_minutes=5,
        )
        token = await svc.create_access_token(user_id=1, email="a@b.com", role="viewer")
        decoded = jwt.decode(
            token,
            "test-secret-key-with-minimum-32-chars!!",
            algorithms=["HS256"],
        )
        iat = datetime.fromtimestamp(decoded["iat"], tz=timezone.utc)
        exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        assert exp - iat == timedelta(minutes=5)

    async def test_custom_refresh_expiry(self) -> None:
        """Service should honour refresh_token_expiry_days."""
        svc = JWTService(
            secret_key="test-secret-key-with-minimum-32-chars!!",
            refresh_token_expiry_days=14,
        )
        token = await svc.create_refresh_token(user_id=42)
        decoded = jwt.decode(
            token,
            "test-secret-key-with-minimum-32-chars!!",
            algorithms=["HS256"],
        )
        iat = datetime.fromtimestamp(decoded["iat"], tz=timezone.utc)
        exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        assert exp - iat == timedelta(days=14)

    async def test_custom_secret_is_used(self) -> None:
        """The constructor's secret_key should take precedence over settings."""
        custom = "custom-secret-that-is-at-least-32-chars!"
        svc = JWTService(secret_key=custom)
        token = await svc.create_access_token(user_id=1, email="a@b.com", role="viewer")
        # Should be decodable with the custom secret
        decoded = jwt.decode(token, custom, algorithms=["HS256"])
        assert decoded["user_id"] == 1
