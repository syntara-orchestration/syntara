"""Exception classes for approvals component.

This module contains custom exceptions used by approval services and endpoints,
following the project's exception handling patterns.
"""

from uuid import UUID

from syntara.approvals.models import ApprovalRequestStatus
from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import SyntaraError


class ApprovalError(SyntaraError):
    """Base exception for all approval errors."""


@fastapi_exception(handler="syntara.approvals.error_handlers.approval_not_found_handler")
class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval request is not found."""

    def __init__(self, approval_id: UUID) -> None:
        """Initialize exception with approval ID."""
        self.approval_id = approval_id
        super().__init__(f"Approval request {approval_id} not found")


@fastapi_exception(handler="syntara.approvals.error_handlers.approval_already_decided_handler")
class ApprovalAlreadyDecidedError(ApprovalError):
    """Raised when attempting to decide an already-decided approval."""

    def __init__(self, approval_id: UUID, current_status: ApprovalRequestStatus) -> None:
        """Initialize exception with approval ID and current status."""
        self.approval_id = approval_id
        self.current_status = current_status
        super().__init__(f"Approval request {approval_id} is already decided with status '{current_status}'")


@fastapi_exception(handler="syntara.approvals.error_handlers.approval_already_requested_handler")
class ApprovalAlreadyRequestedError(ApprovalError):
    """Raised when attempting to create an approval that already exists for the execution and node."""

    def __init__(
        self,
        execution_id: UUID,
        approval_node_id: str,
        loop_iteration_path: list[int] | None = None,
    ) -> None:
        """Initialize exception with execution ID, canvas node ID, and loop path."""
        self.execution_id = execution_id
        self.approval_node_id = approval_node_id
        self.loop_iteration_path = [*loop_iteration_path] if loop_iteration_path is not None else []
        super().__init__(
            "Approval request already exists for execution "
            f"{execution_id}, approval node '{approval_node_id}', "
            f"loop_iteration_path={self.loop_iteration_path}"
        )


@fastapi_exception(handler="syntara.approvals.error_handlers.approval_not_authorized_handler")
class ApprovalNotAuthorizedError(ApprovalError):
    """Raised when a user attempts to decide an approval they are not authorized for."""

    def __init__(self, approval_id: UUID, user_id: UUID) -> None:
        """Initialize exception with approval ID and user ID."""
        self.approval_id = approval_id
        self.user_id = user_id
        super().__init__(f"User {user_id} is not authorized to decide approval request {approval_id}")
