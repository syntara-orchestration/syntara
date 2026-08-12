"""Domain exceptions for credential management."""

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import NexusError


@fastapi_exception(handler="syntara.credentials.error_handlers.credential_error_handler")
class CredentialError(NexusError):
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
