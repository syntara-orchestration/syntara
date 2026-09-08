"""Tests for credential domain exceptions."""

from syntara.credentials.exceptions import (
    CredentialDecryptionError,
    CredentialError,
    CredentialInUseError,
    CredentialNameConflictError,
    CredentialNotFoundError,
    CredentialValidationError,
    ProjectCredentialInUseError,
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


class TestProjectCredentialInUseError:
    """Verify ProjectCredentialInUseError message formatting."""

    def test_message_includes_project_integration_and_credential_names(self) -> None:
        exc = ProjectCredentialInUseError("my-project", ["cred-a", "cred-b"], ["int-x", "int-y"], 2)
        assert isinstance(exc, CredentialError)
        assert "my-project" in exc.message
        assert "int-x" in exc.message
        assert "int-y" in exc.message
        assert "cred-a" in exc.message
        assert "cred-b" in exc.message
        assert "2 integrations" in exc.message

    def test_singular_integration_count(self) -> None:
        exc = ProjectCredentialInUseError("proj", ["cred"], ["int"], 1)
        assert "1 integration " in exc.message
        assert "integrations" not in exc.message.split("(")[0]

    def test_truncation_of_long_lists(self) -> None:
        exc = ProjectCredentialInUseError(
            "proj",
            [f"cred-{i}" for i in range(8)],
            [f"int-{i}" for i in range(3)],
            10,
        )
        assert "and 7 more" in exc.message
        assert "cred-4" in exc.message
        assert "cred-5" not in exc.message
