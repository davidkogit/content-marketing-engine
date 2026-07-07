"""
Unit tests for the password hashing utility module.
"""

import pytest

from app.auth.hashing import hash_password, verify_password


class TestHashPassword:
    """Tests for the hash_password function."""

    def test_hash_password_returns_string(self) -> None:
        """Hashing should return a string, not bytes."""
        result = hash_password("mysecret", rounds=4)
        assert isinstance(result, str)

    def test_hash_password_contains_bcrypt_prefix(self) -> None:
        """The result should start with $2b$ (bcrypt prefix)."""
        result = hash_password("mysecret", rounds=4)
        assert result.startswith("$2b$")

    def test_hash_password_is_different_each_call(self) -> None:
        """Each call produces a different hash due to unique salt."""
        h1 = hash_password("same-password", rounds=4)
        h2 = hash_password("same-password", rounds=4)
        assert h1 != h2

    def test_hash_password_raises_on_empty(self) -> None:
        """Empty passwords should be rejected immediately."""
        with pytest.raises(ValueError, match="must not be empty"):
            hash_password("", rounds=4)

    def test_hash_password_accepts_unicode(self) -> None:
        """Unicode passwords (e.g. with emoji) should hash correctly."""
        result = hash_password("café☕🔑", rounds=4)
        assert result.startswith("$2b$")


class TestVerifyPassword:
    """Tests for the verify_password function."""

    def test_verify_password_returns_true_for_match(self) -> None:
        """A correct password should verify successfully."""
        hashed = hash_password("secure123", rounds=4)
        assert verify_password("secure123", hashed) is True

    def test_verify_password_returns_false_for_mismatch(self) -> None:
        """An incorrect password should return False."""
        hashed = hash_password("secure123", rounds=4)
        assert verify_password("wrongpass", hashed) is False

    def test_verify_password_case_sensitive(self) -> None:
        """Password comparison is case-sensitive."""
        hashed = hash_password("CaseTest", rounds=4)
        assert verify_password("casetest", hashed) is False
        assert verify_password("CaseTest", hashed) is True

    def test_verify_password_with_empty_attempt(self) -> None:
        """An empty attempt should not match any real hash."""
        hashed = hash_password("secure123", rounds=4)
        assert verify_password("", hashed) is False


class TestRoundTrip:
    """End-to-end hash → verify integration tests."""

    @pytest.mark.parametrize(
        "password",
        [
            "simple",
            "with spaces and symbols !@#$%",
            "unicode ñ and emoji 🚀",
            "",  # empty should be caught by hash_password
        ],
    )
    def test_round_trip_hash_then_verify(self, password: str) -> None:
        """Hash and verify should work for a variety of inputs."""
        if not password:
            with pytest.raises(ValueError):
                hash_password(password, rounds=4)
        else:
            hashed = hash_password(password, rounds=4)
            assert verify_password(password, hashed) is True

