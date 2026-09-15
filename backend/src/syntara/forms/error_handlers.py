"""RFC 9457 compliant error handlers for Forms domain.

This module provides error handling for form-specific exceptions.
"""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from syntara.forms.exceptions import (
        FormPromptAlreadyRequestedError,
        FormPromptAlreadyRespondedError,
        FormPromptCancelledError,
        FormPromptExpiredError,
        FormPromptNotFoundError,
    )

logger = structlog.stdlib.get_logger(__name__)


def form_prompt_not_found_handler(request: Request, exc: "FormPromptNotFoundError") -> JSONResponse:
    """Handle FormPromptNotFoundError with RFC 9457 format."""
    logger.error("Form prompt not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Form Prompt Not Found",
        detail="The requested form prompt was not found",
        code="FORM_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def form_prompt_already_responded_handler(request: Request, exc: "FormPromptAlreadyRespondedError") -> JSONResponse:
    """Handle FormPromptAlreadyRespondedError with RFC 9457 format."""
    logger.error("Form prompt already responded", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Form Prompt Already Responded",
        detail="The form prompt has already been responded to and cannot be modified",
        code="FORM_ALREADY_RESPONDED",
        retryable=False,
        instance=str(request.url),
    )


def form_prompt_expired_handler(request: Request, exc: "FormPromptExpiredError") -> JSONResponse:
    """Handle FormPromptExpiredError with RFC 9457 format."""
    logger.error("Form prompt expired", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Form Prompt Expired",
        detail="The form prompt has expired and can no longer be responded to",
        code="FORM_EXPIRED",
        retryable=False,
        instance=str(request.url),
    )


def form_prompt_cancelled_handler(request: Request, exc: "FormPromptCancelledError") -> JSONResponse:
    """Handle FormPromptCancelledError with RFC 9457 format."""
    logger.error("Form prompt cancelled", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Form Prompt Cancelled",
        detail="The form prompt has been cancelled and can no longer be responded to",
        code="FORM_CANCELLED",
        retryable=False,
        instance=str(request.url),
    )


def form_prompt_already_requested_handler(request: Request, exc: "FormPromptAlreadyRequestedError") -> JSONResponse:
    """Handle FormPromptAlreadyRequestedError with RFC 9457 format."""
    logger.error("Form prompt already requested", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Form Prompt Already Requested",
        detail=(
            "A form prompt already exists for this execution and prompt node "
            f"'{exc.prompt_node_id}' with loop_iteration_path {list(exc.loop_iteration_path)}"
        ),
        code="FORM_ALREADY_REQUESTED",
        retryable=False,
        instance=str(request.url),
    )
