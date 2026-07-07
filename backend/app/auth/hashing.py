"""
Password hashing utilities using bcrypt.

Provides pure, stateless hash_password and verify_password functions
that are safe to call from any context. All input/output is string-based
so callers never deal with raw bytes.
"""

import bcrypt

# ── Constants ──────────────────────────────────────────────────────────────
# 12 rounds is the bcrypt default and provides a good balance of security
# and performance for production use. Use lower values only in CI/tests.
_DEFAULT_ROUNDS: int = 12


# ── Public API ──────────────────────────────────────────────────────────────


def hash_password(plain_password: str, *, rounds: int = _DEFAULT_ROUNDS) -> str:
    """Hash a plain-text password with bcrypt.

    Automatically handles str↔bytes encoding so callers work purely
    with Python strings.

    Args:
        plain_password: The plain-text password to hash (must not be empty).
        rounds: Number of bcrypt salt rounds. 12 is recommended for production,
                lower values (e.g. 4) may be used in tests for speed.

    Returns:
        The bcrypt-hashed password as a string.

    Raises:
        ValueError: If the plain_password is fewer than 8 characters.
    """
    if len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    password_bytes: bytes = plain_password.encode("utf-8")
    salt: bytes = bcrypt.gensalt(rounds=rounds)
    hashed_bytes: bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a stored bcrypt hash.

    Performs constant-time comparison — safe against timing attacks.

    Args:
        plain_password: The plain-text password attempt.
        hashed_password: The stored bcrypt hash string to compare against.

    Returns:
        True if the password matches the hash, False otherwise.
    """
    password_bytes: bytes = plain_password.encode("utf-8")
    hashed_bytes: bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)

