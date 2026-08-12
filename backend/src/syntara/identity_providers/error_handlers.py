"""RFC 9457 compliant error handlers for Identity Providers domain."""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from syntara.identity_providers.exceptions import (
        AAPAuthenticationError,
        AAPConnectionError,
        AAPSetupError,
        IdentityProviderError,
        IdentityProviderNameConflictError,
        IdentityProviderNotFoundError,
    )

logger = structlog.stdlib.get_logger(__name__)


def identity_provider_not_found_handler(request: Request, exc: "IdentityProviderNotFoundError") -> JSONResponse:
    """Handle IdentityProviderNotFoundError with RFC 9457 format."""
    logger.error("Identity provider not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Identity Provider Not Found",
        detail=exc.message,
        code="IDENTITY_PROVIDER_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def identity_provider_name_conflict_handler(request: Request, exc: "IdentityProviderNameConflictError") -> JSONResponse:
    """Handle IdentityProviderNameConflictError with RFC 9457 format."""
    logger.error("Identity provider name conflict", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["name_conflict"],
        title="Identity Provider Name Conflict",
        detail=exc.message,
        code="IDENTITY_PROVIDER_NAME_CONFLICT",
        retryable=False,
        instance=str(request.url),
    )


def identity_provider_error_handler(request: Request, exc: "IdentityProviderError") -> JSONResponse:
    """Handle generic IdentityProviderError with RFC 9457 format."""
    logger.error("Identity provider error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        problem_type=PROBLEM_TYPES["provider_error"],
        title="Identity Provider Error",
        detail=exc.message,
        code="IDENTITY_PROVIDER_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def aap_connection_error_handler(request: Request, exc: "AAPConnectionError") -> JSONResponse:
    """Handle AAP connection errors with RFC 9457 format."""
    logger.error("AAP connection error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_502_BAD_GATEWAY,
        problem_type=PROBLEM_TYPES["provider_error"],
        title="AAP Connection Error",
        detail=exc.message,
        code="AAP_CONNECTION_ERROR",
        retryable=True,
        instance=str(request.url),
    )


def aap_authentication_error_handler(request: Request, exc: "AAPAuthenticationError") -> JSONResponse:
    """Handle AAP authentication errors with RFC 9457 format."""
    logger.error("AAP authentication error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_502_BAD_GATEWAY,
        problem_type=PROBLEM_TYPES["provider_error"],
        title="AAP Authentication Error",
        detail=exc.message,
        code="AAP_AUTHENTICATION_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def aap_setup_error_handler(request: Request, exc: "AAPSetupError") -> JSONResponse:
    """Handle AAP setup errors with RFC 9457 format."""
    logger.error("AAP setup error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_502_BAD_GATEWAY,
        problem_type=PROBLEM_TYPES["provider_error"],
        title="AAP Setup Error",
        detail=exc.message,
        code="AAP_SETUP_ERROR",
        retryable=False,
        instance=str(request.url),
    )
