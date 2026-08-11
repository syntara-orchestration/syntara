"""RFC 9457 compliant error handlers for AAP proxy domain.

Maps AAP-specific exceptions to Problem Details responses.
Generic user-facing messages; detailed context goes to server logs only.
"""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from syntara.aap.exceptions import (
        AAPAuthenticationError,
        AAPConnectionError,
        AAPNotConfiguredError,
        AAPUpstreamError,
    )

logger = structlog.stdlib.get_logger(__name__)


def aap_not_configured_handler(request: Request, exc: "AAPNotConfiguredError") -> JSONResponse:
    """Handle AAPNotConfiguredError — AAP Controller not configured."""
    logger.error("AAP Controller not configured", detail=exc.message, exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        problem_type=PROBLEM_TYPES["service_unavailable"],
        title="AAP Controller Not Configured",
        detail="AAP Controller integration is not configured. Contact your administrator.",
        code="AAP_NOT_CONFIGURED",
        retryable=False,
        instance=str(request.url),
    )


def aap_connection_error_handler(request: Request, exc: "AAPConnectionError") -> JSONResponse:
    """Handle AAPConnectionError — cannot reach AAP Controller."""
    logger.error("AAP Controller connection error", detail=exc.message, exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_502_BAD_GATEWAY,
        problem_type=PROBLEM_TYPES["provider_error"],
        title="AAP Connection Error",
        detail="Unable to connect to AAP Controller. Please try again later.",
        code="AAP_CONNECTION_ERROR",
        retryable=True,
        instance=str(request.url),
    )


def aap_authentication_error_handler(request: Request, exc: "AAPAuthenticationError") -> JSONResponse:
    """Handle AAPAuthenticationError — AAP returned 401/403."""
    logger.error("AAP Controller authentication failed", detail=exc.message, exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_502_BAD_GATEWAY,
        problem_type=PROBLEM_TYPES["provider_error"],
        title="AAP Authentication Failed",
        detail="AAP Controller authentication failed. Contact your administrator.",
        code="AAP_AUTHENTICATION_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def aap_upstream_error_handler(request: Request, exc: "AAPUpstreamError") -> JSONResponse:
    """Handle AAPUpstreamError — AAP returned an unexpected error."""
    logger.error("AAP Controller upstream error", detail=exc.message, exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_502_BAD_GATEWAY,
        problem_type=PROBLEM_TYPES["provider_error"],
        title="AAP Upstream Error",
        detail="AAP Controller returned an unexpected error. Please try again later.",
        code="AAP_UPSTREAM_ERROR",
        retryable=True,
        instance=str(request.url),
    )
