"""Base exceptions for the Nexus application.

This module contains the root exception hierarchy for all internal exceptions
within the Nexus system. Exception boundaries stop at the FastAPI routers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from syntara.core.exception_registry import fastapi_exception

if TYPE_CHECKING:
    from uuid import UUID


class NexusError(Exception):
    """Base exception for all Nexus internal errors.

    This is the root of the exception hierarchy for all domain-specific
    exceptions within the Nexus system. It provides a common interface
    and ensures all internal exceptions accept a message parameter.
    """

    def __init__(self, message: str) -> None:
        """Initialize NexusError.

        Args:
            message: Error message describing the failure

        """
        self.message = message
        super().__init__(message)


class RetryableError(NexusError):
    """Marker base class for exceptions that should trigger retry logic.

    Mix into domain exceptions via multiple inheritance so retry_with_backoff
    retries them automatically. Named as a behavioral trait rather than the
    {Resource}{Condition}Error convention used by domain exceptions.
    """


@fastapi_exception(handler="syntara.core.error_handlers.safe_value_error_handler")
class SafeValueError(ValueError, NexusError):
    """ValueError subclass for user-safe validation error messages.

    Use this instead of ValueError when the error message is safe to expose
    to end users and doesn't contain internal implementation details.

    This extends both ValueError (for isinstance checks) and NexusError
    (for consistent exception handling).

    Examples:
        # Safe - user validation messages
        raise SafeValueError("Invalid cursor format")
        raise SafeValueError("Field name must be a non-empty string")

        # NOT safe - contains implementation details
        raise ValueError(f"Database connection failed: {db_error}")
        raise ValueError(f"Provider creation failed: {internal_error}")

    """

    def __init__(self, message: str) -> None:
        """Initialize SafeValueError.

        Args:
            message: User-safe error message that can be exposed in API responses

        """
        super().__init__(message)


def assert_project_id_unchanged(current: UUID | None, requested: UUID | None) -> None:
    """Raise SafeValueError if a PATCH attempts to change project_id."""
    if requested is not None and requested != current:
        msg = "project_id is immutable after creation"
        raise SafeValueError(msg)
