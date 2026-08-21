"""Tests for credential domain exceptions."""

from syntara.credentials.exceptions import (
    CredentialDecryptionError,
    CredentialError,
    CredentialInUseError,
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

    def test_in_use_error_stores_details_and_lists_names(self) -> None:
        exc = CredentialInUseError("my-cred", ["Integration A", "Integration B"], 2)
        assert isinstance(exc, CredentialError)
        assert exc.name == "my-cred"
        assert exc.integration_names == ["Integration A", "Integration B"]
        assert exc.total_count == 2
        assert "my-cred" in exc.message
        assert "Integration A" in exc.message
        assert "Integration B" in exc.message
        assert "2 integrations" in exc.message

    def test_in_use_error_singular_count(self) -> None:
        exc = CredentialInUseError("my-cred", ["Integration A"], 1)
        assert "1 integration " in exc.message
        assert "integrations" not in exc.message.split("(")[0]

    def test_in_use_error_truncates_and_shows_remaining_count(self) -> None:
        exc = CredentialInUseError("my-cred", ["A", "B", "C"], 5)
        assert "and 2 more" in exc.message

    def test_in_use_error_falls_back_to_generic_wording_when_names_empty(self) -> None:
        """Double-race edge case: total_count > 0 but no names could be resolved.

        Must not render an empty or malformed parenthetical like "()" or
        "( and 1 more)".
        """
        exc = CredentialInUseError("my-cred", [], 1)
        assert exc.message == (
            "Cannot delete credential 'my-cred': still in use by 1 integration. "
            "Remove the credential from these integrations before deleting it."
        )
        assert "(" not in exc.message
        assert ")" not in exc.message
