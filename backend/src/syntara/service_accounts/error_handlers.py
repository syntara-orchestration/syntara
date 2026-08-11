# Generated with AI assistance: Claude Code (Anthropic)
"""RFC 9457 compliant error handlers for service account domain."""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from syntara.service_accounts.exceptions import (
        CredentialExpirationExceededError,
        CredentialExpirationInPastError,
        ServiceAccountCredentialLimitError,
        ServiceAccountCredentialNotFoundError,
        ServiceAccountError,
        ServiceAccountNameConflictError,
        ServiceAccountNotFoundError,
    )

logger = structlog.stdlib.get_logger(__name__)


def service_account_not_found_handler(request: Request, exc: "ServiceAccountNotFoundError") -> JSONResponse:
    """Handle ServiceAccountNotFoundError with RFC 9457 format."""
    logger.error("Service account not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Service Account Not Found",
        detail=exc.message,
        code="SERVICE_ACCOUNT_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def service_account_name_conflict_handler(request: Request, exc: "ServiceAccountNameConflictError") -> JSONResponse:
    """Handle ServiceAccountNameConflictError with RFC 9457 format."""
    logger.error("Service account name conflict", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["name_conflict"],
        title="Service Account Name Conflict",
        detail=exc.message,
        code="SERVICE_ACCOUNT_NAME_CONFLICT",
        retryable=False,
        instance=str(request.url),
    )


def service_account_error_handler(request: Request, exc: "ServiceAccountError") -> JSONResponse:
    """Handle generic ServiceAccountError with RFC 9457 format."""
    logger.error("Service account error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Service Account Error",
        detail=exc.message,
        code="SERVICE_ACCOUNT_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def sa_credential_not_found_handler(request: Request, exc: "ServiceAccountCredentialNotFoundError") -> JSONResponse:
    """Handle ServiceAccountCredentialNotFoundError with RFC 9457 format."""
    logger.error("Service account credential not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Service Account Credential Not Found",
        detail=exc.message,
        code="SERVICE_ACCOUNT_CREDENTIAL_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def sa_credential_limit_handler(request: Request, exc: "ServiceAccountCredentialLimitError") -> JSONResponse:
    """Handle ServiceAccountCredentialLimitError with RFC 9457 format."""
    logger.error("Service account credential limit reached", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Service Account Credential Limit Reached",
        detail=exc.message,
        code="SERVICE_ACCOUNT_CREDENTIAL_LIMIT",
        retryable=False,
        instance=str(request.url),
    )


def sa_credential_expiration_exceeded_handler(
    request: Request, exc: "CredentialExpirationExceededError"
) -> JSONResponse:
    """Handle CredentialExpirationExceededError with RFC 9457 format."""
    logger.error("Credential expiration exceeds maximum lifetime", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Credential Expiration Exceeded",
        detail=exc.message,
        code="CREDENTIAL_EXPIRATION_EXCEEDED",
        retryable=False,
        instance=str(request.url),
    )


def sa_credential_expiration_in_past_handler(request: Request, exc: "CredentialExpirationInPastError") -> JSONResponse:
    """Handle CredentialExpirationInPastError with RFC 9457 format."""
    logger.error("Credential expiration is in the past", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Credential Expiration In Past",
        detail=exc.message,
        code="CREDENTIAL_EXPIRATION_IN_PAST",
        retryable=False,
        instance=str(request.url),
    )
