"""Domain exceptions for the integrations domain."""

from uuid import UUID

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import NexusError


@fastapi_exception(handler="syntara.integrations.error_handlers.integration_error_handler")
class IntegrationError(NexusError):
    """Base exception for all integration errors."""


@fastapi_exception(handler="syntara.integrations.error_handlers.integration_not_found_handler")
class IntegrationNotFoundError(IntegrationError):
    """Exception raised when an integration is not found."""

    def __init__(self, integration_id: UUID) -> None:
        """Initialize exception with integration ID."""
        self.integration_id = integration_id
        super().__init__(f"Integration {integration_id} not found")


@fastapi_exception(handler="syntara.integrations.error_handlers.integration_name_conflict_handler")
class IntegrationNameConflictError(IntegrationError):
    """Exception raised when an integration name already exists."""

    def __init__(self, name: str) -> None:
        """Initialize exception with integration name."""
        self.name = name
        super().__init__(f"Integration with name '{name}' already exists")


@fastapi_exception(handler="syntara.integrations.error_handlers.integration_credential_required_handler")
class IntegrationCredentialRequiredError(IntegrationError):
    """Exception raised when credential is required but missing for an integration type."""

    def __init__(self, integration_type: str) -> None:
        """Initialize exception with integration type."""
        self.integration_type = integration_type
        super().__init__(
            f"{integration_type} integrations require a management credential for discovery and validation"
        )


@fastapi_exception(handler="syntara.integrations.error_handlers.integration_credential_not_found_handler")
class IntegrationCredentialNotFoundError(IntegrationError):
    """Exception raised when a credential ID does not exist in the database."""

    def __init__(self, credential_id: UUID) -> None:
        """Initialize exception with credential ID."""
        self.credential_id = credential_id
        super().__init__(f"Credential {credential_id} not found")


@fastapi_exception(handler="syntara.integrations.error_handlers.integration_credential_type_mismatch_handler")
class IntegrationCredentialTypeMismatchError(IntegrationError):
    """Exception raised when a credential's type is incompatible with the integration type."""

    def __init__(self, integration_type: str, credential_type_name: str, allowed: frozenset[str]) -> None:
        """Initialize exception with the mismatched types."""
        self.integration_type = integration_type
        self.credential_type_name = credential_type_name
        self.allowed = allowed
        allowed_str = ", ".join(sorted(allowed))
        super().__init__(
            f"Credential type '{credential_type_name}' is not valid for "
            f"integration type '{integration_type}'. Allowed types: {allowed_str}"
        )


@fastapi_exception(handler="syntara.integrations.error_handlers.integration_error_handler")
class AdapterNotRegisteredError(IntegrationError):
    """Exception raised when no health check adapter is registered for an integration type."""

    def __init__(self, integration_type: str) -> None:
        """Initialize exception with integration type."""
        self.integration_type = integration_type
        super().__init__(f"No health check adapter registered for integration type '{integration_type}'")


@fastapi_exception(handler="syntara.integrations.error_handlers.llm_model_not_found_handler")
class LLMModelNotFoundError(IntegrationError):
    """Exception raised when an LLM model is not found."""

    def __init__(self, model_id: UUID) -> None:
        """Initialize exception with model ID."""
        self.model_id = model_id
        super().__init__(f"LLM model {model_id} not found")


@fastapi_exception(handler="syntara.integrations.error_handlers.integration_type_mismatch_handler")
class IntegrationTypeMismatchError(IntegrationError):
    """Raised when an endpoint is called on an integration of the wrong type."""

    def __init__(self, integration_id: UUID, expected_type: str, actual_type: str) -> None:
        """Initialize exception with integration ID and types."""
        self.integration_id = integration_id
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(f"Integration {integration_id} is type {actual_type} — this endpoint requires {expected_type}")


@fastapi_exception(handler="syntara.integrations.error_handlers.integration_scope_error_handler")
class IntegrationScopeError(IntegrationError):
    """Exception raised when an operation violates integration scope rules."""

    def __init__(self, integration_id: UUID, message: str) -> None:
        """Initialize exception with integration ID and message."""
        self.integration_id = integration_id
        super().__init__(message)


@fastapi_exception(handler="syntara.integrations.error_handlers.integration_refresh_not_supported_handler")
class IntegrationRefreshNotSupportedError(IntegrationError):
    """Raised when refresh is not supported for this integration type."""

    def __init__(self, integration_id: UUID, integration_type: str) -> None:
        """Initialize exception with integration ID and type."""
        self.integration_id = integration_id
        self.integration_type = integration_type
        super().__init__(
            f"Resource refresh is not supported for integration {integration_id} (type: {integration_type})."
        )
