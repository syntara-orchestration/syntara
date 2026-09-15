"""Exception classes for forms component.

This module contains custom exceptions used by form services and endpoints,
following the project's exception handling patterns.
"""

from datetime import datetime
from uuid import UUID

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import SyntaraError
from syntara.forms.models import FormPromptStatus


class FormError(SyntaraError):
    """Base exception for all form errors."""


@fastapi_exception(handler="syntara.forms.error_handlers.form_prompt_not_found_handler")
class FormPromptNotFoundError(FormError):
    """Raised when a form prompt is not found."""

    def __init__(self, form_prompt_id: UUID) -> None:
        """Initialize exception with form prompt ID."""
        self.form_prompt_id = form_prompt_id
        super().__init__(f"Form prompt {form_prompt_id} not found")


@fastapi_exception(handler="syntara.forms.error_handlers.form_prompt_already_responded_handler")
class FormPromptAlreadyRespondedError(FormError):
    """Raised when attempting to respond to an already-responded form prompt."""

    def __init__(self, form_prompt_id: UUID, current_status: FormPromptStatus) -> None:
        """Initialize exception with form prompt ID and current status."""
        self.form_prompt_id = form_prompt_id
        self.current_status = current_status
        super().__init__(f"Form prompt {form_prompt_id} has already been responded to with status '{current_status}'")


@fastapi_exception(handler="syntara.forms.error_handlers.form_prompt_expired_handler")
class FormPromptExpiredError(FormError):
    """Raised when attempting to respond to an expired form prompt."""

    def __init__(self, form_prompt_id: UUID, timeout_at: datetime | None = None) -> None:
        """Initialize exception with form prompt ID and timeout."""
        self.form_prompt_id = form_prompt_id
        self.timeout_at = timeout_at
        message = f"Form prompt {form_prompt_id} has expired"
        if timeout_at:
            message += f" at {timeout_at}"
        super().__init__(message)


@fastapi_exception(handler="syntara.forms.error_handlers.form_prompt_cancelled_handler")
class FormPromptCancelledError(FormError):
    """Raised when attempting to respond to a cancelled form prompt."""

    def __init__(self, form_prompt_id: UUID) -> None:
        """Initialize exception with form prompt ID."""
        self.form_prompt_id = form_prompt_id
        super().__init__(f"Form prompt {form_prompt_id} has been cancelled")


@fastapi_exception(handler="syntara.forms.error_handlers.form_prompt_already_requested_handler")
class FormPromptAlreadyRequestedError(FormError):
    """Raised when attempting to create a form prompt that already exists for the execution and node."""

    def __init__(
        self,
        execution_id: UUID,
        prompt_node_id: str,
        loop_iteration_path: list[int] | None = None,
    ) -> None:
        """Initialize exception with execution ID, canvas node ID, and loop path."""
        self.execution_id = execution_id
        self.prompt_node_id = prompt_node_id
        self.loop_iteration_path = [*loop_iteration_path] if loop_iteration_path is not None else []
        super().__init__(
            "Form prompt already exists for execution "
            f"{execution_id}, prompt node '{prompt_node_id}', "
            f"loop_iteration_path={self.loop_iteration_path}"
        )
