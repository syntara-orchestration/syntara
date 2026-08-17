"""Domain exceptions for identity provider management."""

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import SyntaraError


@fastapi_exception(handler="syntara.identity_providers.error_handlers.identity_provider_error_handler")
class IdentityProviderError(SyntaraError):
    """Base exception for all identity provider errors."""


@fastapi_exception(handler="syntara.identity_providers.error_handlers.identity_provider_not_found_handler")
class IdentityProviderNotFoundError(IdentityProviderError):
    """Exception raised when an identity provider is not found."""


@fastapi_exception(handler="syntara.identity_providers.error_handlers.identity_provider_name_conflict_handler")
class IdentityProviderNameConflictError(IdentityProviderError):
    """Exception raised when an identity provider name already exists."""

    def __init__(self, name: str) -> None:
        """Initialize exception with provider name."""
        self.name = name
        super().__init__(f"Identity provider with name '{name}' already exists")


@fastapi_exception(handler="syntara.identity_providers.error_handlers.aap_connection_error_handler")
class AAPConnectionError(IdentityProviderError):
    """Cannot connect to AAP during OIDC setup."""


@fastapi_exception(handler="syntara.identity_providers.error_handlers.aap_authentication_error_handler")
class AAPAuthenticationError(IdentityProviderError):
    """AAP returned 401/403 during OIDC setup."""


@fastapi_exception(handler="syntara.identity_providers.error_handlers.aap_setup_error_handler")
class AAPSetupError(IdentityProviderError):
    """AAP returned an error while creating the OAuth2 application."""
