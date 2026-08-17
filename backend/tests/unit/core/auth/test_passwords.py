"""Unit tests for password hashing utilities."""

from syntara.auth.passwords import hash_password, verify_password


class TestHashPassword:
    """Tests for hash_password."""

    def test_returns_argon2id_hash(self) -> None:
        """Hash should produce an argon2id encoded string."""
        hashed = hash_password("my-secret")
        assert hashed.startswith("$argon2id$")

    def test_different_calls_produce_different_hashes(self) -> None:
        """Each call should use a unique salt, producing distinct hashes."""
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        assert h1 != h2


class TestVerifyPassword:
    """Tests for verify_password."""

    def test_correct_password_returns_true(self) -> None:
        """Verification succeeds for the correct plaintext."""
        hashed = hash_password("correct")
        assert verify_password("correct", hashed) is True

    def test_wrong_password_returns_false(self) -> None:
        """Verification fails for an incorrect plaintext."""
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_empty_password_can_round_trip(self) -> None:
        """Empty string is a valid password for hashing/verification."""
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False
