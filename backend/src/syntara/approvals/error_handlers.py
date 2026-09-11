"""RFC 9457 compliant error handlers for Approvals domain.

This module provides error handling for approval-specific exceptions.
"""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from syntara.approvals.exceptions import (
        ApprovalAlreadyDecidedError,
        ApprovalAlreadyRequestedError,
        ApprovalNotAuthorizedError,
        ApprovalNotFoundError,
    )

logger = structlog.stdlib.get_logger(__name__)


def approval_not_found_handler(request: Request, exc: "ApprovalNotFoundError") -> JSONResponse:
    """Handle ApprovalNotFoundError with RFC 9457 format."""
    logger.error("Approval not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Approval Not Found",
        detail="The requested approval was not found",
        code="APPROVAL_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def approval_already_decided_handler(request: Request, exc: "ApprovalAlreadyDecidedError") -> JSONResponse:
    """Handle ApprovalAlreadyDecidedError with RFC 9457 format."""
    logger.error("Approval already decided", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Approval Already Decided",
        detail="The approval request has already been decided and cannot be modified",
        code="APPROVAL_ALREADY_DECIDED",
        retryable=False,
        instance=str(request.url),
    )


def approval_already_requested_handler(request: Request, exc: "ApprovalAlreadyRequestedError") -> JSONResponse:
    """Handle ApprovalAlreadyRequestedError with RFC 9457 format."""
    logger.error("Approval already requested", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Approval Already Requested",
        detail=(
            "An approval request already exists for this execution and approval node "
            f"'{exc.approval_node_id}' with loop_iteration_path {list(exc.loop_iteration_path)}"
        ),
        code="APPROVAL_ALREADY_REQUESTED",
        retryable=False,
        instance=str(request.url),
    )


def approval_not_authorized_handler(request: Request, exc: "ApprovalNotAuthorizedError") -> JSONResponse:
    """Handle ApprovalNotAuthorizedError with RFC 9457 format."""
    logger.error("Approval authorization failed", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_403_FORBIDDEN,
        problem_type=PROBLEM_TYPES["forbidden"],
        title="Not Authorized",
        detail="You are not authorized to decide this approval request",
        code="APPROVAL_NOT_AUTHORIZED",
        retryable=False,
        instance=str(request.url),
    )
