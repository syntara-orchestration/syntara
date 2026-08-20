"""Domain exceptions for credential management."""

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import SyntaraError


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_error_handler")
class CredentialError(SyntaraError):
    """Base exception for all credential management errors."""


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_not_found_handler")
class CredentialNotFoundError(CredentialError):
    """Exception raised when a credential is not found."""


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_name_conflict_handler")
class CredentialNameConflictError(CredentialError):
    """Exception raised when a credential name already exists."""

    def __init__(self, name: str) -> None:
        """Initialize exception with credential name."""
        self.name = name
        super().__init__(f"Credential with name '{name}' already exists in this project")


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_validation_error_handler")
class CredentialValidationError(CredentialError):
    """Exception raised for credential input validation errors."""


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_decryption_error_handler")
class CredentialDecryptionError(CredentialError):
    """Exception raised when credential decryption fails."""


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_disabled_error_handler")
class CredentialDisabledError(CredentialError):
    """Exception raised when a disabled credential is used in an operation."""

    def __init__(self, name: str) -> None:
        """Initialize with credential name."""
        self.name = name
        super().__init__(f"Credential '{name}' is disabled. Re-enable it to continue.")


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_in_use_error_handler")
class CredentialInUseError(CredentialError):
    """Exception raised when deleting a credential still used as an integration's management credential.

    See AAP-87778: previously the delete silently nulled the integration's
    management_credential_id, leaving validation_status stale (e.g. still
    "available") with no indication the integration could no longer
    authenticate. Blocking the delete forces the caller to detach the
    credential from all referencing integrations first.
    """

    def __init__(self, name: str, integration_names: list[str], total_count: int) -> None:
        """Initialize with credential name and a sample of referencing integration names."""
        self.name = name
        self.integration_names = integration_names
        self.total_count = total_count

        shown = ", ".join(f"'{n}'" for n in integration_names)
        remaining = total_count - len(integration_names)
        suffix = f" and {remaining} more" if remaining > 0 else ""
        plural = "s" if total_count != 1 else ""
        super().__init__(
            f"Cannot delete credential '{name}': still in use by {total_count} "
            f"integration{plural} ({shown}{suffix}). Remove the credential from "
            "these integrations before deleting it."
        )
