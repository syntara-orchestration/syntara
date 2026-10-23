"""RFC 9457 compliant error handlers for the event streams domain.

Generic user-facing messages; detailed context goes to server logs only.
"""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from syntara.eventstreams.exceptions import EventStreamError, EventSubscriptionInUseError

logger = structlog.stdlib.get_logger(__name__)


def event_subscription_not_found_handler(request: Request, exc: "EventStreamError") -> JSONResponse:
    """Do not disclose whether a subscription exists in another workflow."""
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Event Subscription Not Found",
        detail=exc.message,
        code="EVENT_SUBSCRIPTION_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def event_subscription_in_use_error_handler(request: Request, exc: "EventSubscriptionInUseError") -> JSONResponse:
    """Handle EventSubscriptionInUseError with RFC 9457 format."""
    logger.warning(
        "Blocked delete: resource still bound by event subscriptions",
        resource_kind=exc.resource_kind,
        resource_name=exc.resource_name,
        affected_subscription_count=exc.total_count,
    )
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Event Subscription In Use",
        detail=exc.message,
        code="EVENT_SUBSCRIPTION_IN_USE",
        retryable=False,
        instance=str(request.url),
    )


def event_stream_error_handler(request: Request, exc: "EventStreamError") -> JSONResponse:
    """Handle generic EventStreamError with RFC 9457 format."""
    logger.error("Event stream error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        problem_type=PROBLEM_TYPES["internal_error"],
        title="Event Stream Error",
        detail="An internal error occurred while processing the event subscription.",
        code="EVENT_STREAM_ERROR",
        retryable=False,
        instance=str(request.url),
    )
