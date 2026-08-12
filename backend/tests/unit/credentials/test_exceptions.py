"""Tests for credential domain exceptions."""

from syntara.credentials.exceptions import (
    CredentialDecryptionError,
    CredentialError,
    CredentialNameConflictError,
    CredentialNotFoundError,
    CredentialValidationError,
)


class TestCredentialExceptions:
    """Verify exception hierarchy and messages."""

    def test_base_error(self) -> None:
        exc = CredentialError("something went wrong")
        assert exc.message == "something went wrong"
        assert isinstance(exc, Exception)

    def test_not_found_error(self) -> None:
        exc = CredentialNotFoundError("credential not found")
        assert isinstance(exc, CredentialError)
        assert exc.message == "credential not found"

    def test_name_conflict_stores_name(self) -> None:
        exc = CredentialNameConflictError("my-cred")
        assert exc.name == "my-cred"
        assert "my-cred" in exc.message
        assert isinstance(exc, CredentialError)

    def test_validation_error(self) -> None:
        exc = CredentialValidationError("invalid input")
        assert isinstance(exc, CredentialError)
        assert exc.message == "invalid input"

    def test_decryption_error(self) -> None:
        exc = CredentialDecryptionError("decryption failed")
        assert isinstance(exc, CredentialError)
        assert exc.message == "decryption failed"
