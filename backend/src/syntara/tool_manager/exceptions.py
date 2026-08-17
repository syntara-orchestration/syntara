"""Domain exceptions for tool management."""

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import SyntaraError


# Domain Exceptions
@fastapi_exception(handler="syntara.tool_manager.error_handlers.tool_manager_error_handler")
class ToolManagerError(SyntaraError):
    """Base exception for all tool management errors."""


@fastapi_exception(handler="syntara.tool_manager.error_handlers.tool_refresh_error_handler")
class ToolRefreshError(ToolManagerError):
    """Exception raised for provider-related errors."""


@fastapi_exception(handler="syntara.tool_manager.error_handlers.tool_not_found_handler")
class ToolNotFoundError(ToolManagerError):
    """Exception raised when a tool is not found."""


@fastapi_exception(handler="syntara.tool_manager.error_handlers.tool_bulk_update_validation_error_handler")
class ToolBulkUpdateValidationError(ToolManagerError):
    """Exception raised for validation errors."""


@fastapi_exception(handler="syntara.tool_manager.error_handlers.tool_provider_not_found_handler")
class ProviderNotFoundError(ToolManagerError):
    """Exception raised when a provider is not found."""


@fastapi_exception(handler="syntara.tool_manager.error_handlers.tool_provider_name_conflict_handler")
class ProviderNameConflictError(ToolManagerError):
    """Exception raised when a provider name already exists."""

    def __init__(self, name: str) -> None:
        """Initialize exception with provider name."""
        self.name = name
        super().__init__(f"Provider with name '{name}' already exists")
