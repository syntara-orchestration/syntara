# Generated with AI assistance: Claude Code (Anthropic)
"""Domain exceptions for service account management."""

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import SyntaraError


@fastapi_exception(handler="syntara.service_accounts.error_handlers.service_account_error_handler")
class ServiceAccountError(SyntaraError):
    """Base exception for all service account errors."""


@fastapi_exception(handler="syntara.service_accounts.error_handlers.service_account_not_found_handler")
class ServiceAccountNotFoundError(ServiceAccountError):
    """Exception raised when a service account is not found."""


@fastapi_exception(handler="syntara.service_accounts.error_handlers.service_account_name_conflict_handler")
class ServiceAccountNameConflictError(ServiceAccountError):
    """Exception raised when a service account name already exists in the project."""

    def __init__(self, name: str) -> None:
        """Initialize exception with service account name."""
        self.name = name
        super().__init__(f"Service account with name '{name}' already exists in this project")


@fastapi_exception(handler="syntara.service_accounts.error_handlers.sa_credential_not_found_handler")
class ServiceAccountCredentialNotFoundError(ServiceAccountError):
    """Exception raised when a service account credential is not found."""


@fastapi_exception(handler="syntara.service_accounts.error_handlers.sa_credential_limit_handler")
class ServiceAccountCredentialLimitError(ServiceAccountError):
    """Exception raised when a service account has reached its credential limit."""

    def __init__(self, service_account_id: str, limit: int) -> None:
        """Initialize exception with service account ID and limit."""
        self.service_account_id = service_account_id
        self.limit = limit
        super().__init__(f"Service account {service_account_id} has reached the maximum of {limit} credentials")


@fastapi_exception(handler="syntara.service_accounts.error_handlers.sa_credential_expiration_exceeded_handler")
class CredentialExpirationExceededError(ServiceAccountError):
    """Exception raised when a requested expires_at exceeds the configured maximum lifetime."""

    def __init__(self, max_lifetime_days: int) -> None:
        """Initialize exception with the configured maximum lifetime."""
        self.max_lifetime_days = max_lifetime_days
        super().__init__(f"Requested expiration exceeds the maximum credential lifetime of {max_lifetime_days} days")


@fastapi_exception(handler="syntara.service_accounts.error_handlers.sa_credential_expiration_in_past_handler")
class CredentialExpirationInPastError(ServiceAccountError):
    """Exception raised when a requested expires_at is in the past."""
