"""
JWT token creation and verification service.

Provides JWTService with async methods for creating and verifying
access and refresh tokens. Tokens are signed with HS256 using the
SECRET_KEY from application config. Expiry times are configurable
with sensible defaults (30 min access, 7 day refresh).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidSignatureError,
    InvalidTokenError,
)

from app.config import settings

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_ACCESS_TOKEN_EXPIRY_MINUTES: int = 30
"""Default lifetime for access tokens in minutes."""

DEFAULT_REFRESH_TOKEN_EXPIRY_DAYS: int = 7
"""Default lifetime for refresh tokens in days."""

TOKEN_ALGORITHM: str = "HS256"
"""JWT signing algorithm — HMAC-SHA256."""


# ── Domain Exceptions ──────────────────────────────────────────────────────


class TokenError(Exception):
    """Base exception for all token-related errors."""


class TokenExpiredError(TokenError):
    """Raised when a token has passed its expiry time."""


class TokenInvalidError(TokenError):
    """Raised when a token has an invalid signature or is malformed."""


# ── JWTService ─────────────────────────────────────────────────────────────


class JWTService:
    """Async service for JWT token creation and verification.

    All methods are async for consistency with the rest of the service
    layer, even though the underlying PyJWT operations are synchronous.

    Access tokens carry ``user_id``, ``email``, and ``role`` claims.
    Refresh tokens carry ``user_id`` and ``token_version`` for
    invalidation support.

    Usage::

        service = JWTService()
        access_token = await service.create_access_token(
            user_id=42, email="user@example.com", role="editor"
        )
        payload = await service.verify_token(access_token)
    """

    def __init__(
        self,
        *,
        secret_key: str | None = None,
        access_token_expiry_minutes: int = DEFAULT_ACCESS_TOKEN_EXPIRY_MINUTES,
        refresh_token_expiry_days: int = DEFAULT_REFRESH_TOKEN_EXPIRY_DAYS,
    ) -> None:
        """Initialise the JWT service with configurable parameters.

        Args:
            secret_key: HMAC secret for signing. Defaults to settings.SECRET_KEY.
            access_token_expiry_minutes: Access token lifetime in minutes.
            refresh_token_expiry_days: Refresh token lifetime in days.
        """
        self._secret_key: str = secret_key or settings.SECRET_KEY
        self._access_expiry: int = access_token_expiry_minutes
        self._refresh_expiry: int = refresh_token_expiry_days

    # ── Token Creation ──────────────────────────────────────────────────

    async def create_access_token(
        self,
        user_id: int,
        email: str,
        role: str,
        *,
        extra_claims: dict | None = None,
    ) -> str:
        """Create a signed JWT access token.

        The token payload includes ``user_id``, ``email``, and ``role``
        claims along with standard ``iat``, ``exp``, ``sub``, and ``type``.

        Args:
            user_id: The authenticated user's primary key.
            email: The user's email address.
            role: The user's role string (e.g. ``"editor"``).
            extra_claims: Optional additional claims to merge into the payload.

        Returns:
            An encoded JWT string suitable for use as a Bearer token.
        """
        now = datetime.now(timezone.utc)
        payload: dict = {
            "sub": str(user_id),
            "user_id": user_id,
            "email": email,
            "role": role,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=self._access_expiry),
        }
        if extra_claims:
            payload.update(extra_claims)

        token: str = jwt.encode(payload, self._secret_key, algorithm=TOKEN_ALGORITHM)
        logger.debug("Created access token for user_id=%d", user_id)
        return token

    async def create_refresh_token(
        self,
        user_id: int,
        token_version: int = 0,
    ) -> str:
        """Create a signed JWT refresh token.

        Refresh tokens have a longer lifetime (default 7 days) and carry
        a ``token_version`` claim to support server-side invalidation.

        Args:
            user_id: The authenticated user's primary key.
            token_version: An integer version that can be incremented to
                           invalidate all previously issued refresh tokens
                           for this user.

        Returns:
            An encoded JWT refresh token string.
        """
        now = datetime.now(timezone.utc)
        payload: dict = {
            "sub": str(user_id),
            "user_id": user_id,
            "type": "refresh",
            "token_version": token_version,
            "iat": now,
            "exp": now + timedelta(days=self._refresh_expiry),
        }

        token: str = jwt.encode(payload, self._secret_key, algorithm=TOKEN_ALGORITHM)
        logger.debug("Created refresh token for user_id=%d (version=%d)", user_id, token_version)
        return token

    # ── Token Verification ───────────────────────────────────────────────

    async def decode_token(self, token: str) -> dict:
        """Decode and validate a JWT, returning the full payload dictionary.

        Validates the cryptographic signature and checks that the token
        has not expired. Does **not** enforce audience, issuer, or other
        optional checks.

        Args:
            token: The encoded JWT string to decode and validate.

        Returns:
            The decoded claims dictionary (e.g. ``{"user_id": 42, ...}``).

        Raises:
            TokenExpiredError: If the token's ``exp`` claim is in the past.
            TokenInvalidError: If the signature is invalid, the token is
                               malformed, or any other structural error occurs.
        """
        try:
            payload: dict = jwt.decode(
                token,
                self._secret_key,
                algorithms=[TOKEN_ALGORITHM],
                options={"verify_exp": True},
            )
            return payload
        except ExpiredSignatureError:
            raise TokenExpiredError("Token has expired.")
        except InvalidSignatureError:
            raise TokenInvalidError("Token signature is invalid.")
        except DecodeError:
            raise TokenInvalidError("Token is malformed and cannot be decoded.")
        except InvalidTokenError as exc:
            raise TokenInvalidError(f"Token is invalid: {exc}")

    async def verify_token(self, token: str) -> dict:
        """Verify a token and return its decoded payload.

        Convenience alias for :meth:`decode_token` with identical
        validation and error semantics.

        Args:
            token: The encoded JWT string to verify.

        Returns:
            The decoded claims dictionary.

        Raises:
            TokenExpiredError: If the token has expired.
            TokenInvalidError: If the token is invalid or malformed.
        """
        return await self.decode_token(token)
