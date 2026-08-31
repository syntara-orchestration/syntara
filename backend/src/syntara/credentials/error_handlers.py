"""RFC 9457 compliant error handlers for Credential Management domain.

This module provides error handling for credential-specific exceptions.
Generic user-facing messages; detailed context goes to server logs only.
"""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from syntara.credentials.exceptions import (
        CredentialDecryptionError,
        CredentialDisabledError,
        CredentialError,
        CredentialInUseError,
        CredentialNameConflictError,
        CredentialNotFoundError,
        CredentialValidationError,
        ProjectCredentialInUseError,
    )

logger = structlog.stdlib.get_logger(__name__)


def credential_not_found_handler(request: Request, exc: "CredentialNotFoundError") -> JSONResponse:
    """Handle CredentialNotFoundError with RFC 9457 format."""
    logger.error("Credential not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Credential Not Found",
        detail=exc.message,
        code="CREDENTIAL_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def credential_name_conflict_handler(request: Request, exc: "CredentialNameConflictError") -> JSONResponse:
    """Handle CredentialNameConflictError with RFC 9457 format."""
    logger.error("Credential name conflict", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["name_conflict"],
        title="Credential Name Conflict",
        detail=exc.message,
        code="CREDENTIAL_NAME_CONFLICT",
        retryable=False,
        instance=str(request.url),
    )


def credential_validation_error_handler(request: Request, exc: "CredentialValidationError") -> JSONResponse:
    """Handle CredentialValidationError with RFC 9457 format."""
    logger.error("Credential validation error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Credential Validation Error",
        detail=exc.message,
        code="CREDENTIAL_VALIDATION_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def credential_decryption_error_handler(request: Request, exc: "CredentialDecryptionError") -> JSONResponse:
    """Handle CredentialDecryptionError with RFC 9457 format.

    Security: Returns a generic message to avoid leaking encryption details
    (wrong key, tampered data, corrupted ciphertext). Full error is logged server-side.
    """
    logger.error("Credential decryption error", error_detail=exc.message, exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        problem_type=PROBLEM_TYPES["internal_error"],
        title="Credential Decryption Error",
        detail="An error occurred while processing credential data",
        code="CREDENTIAL_DECRYPTION_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def credential_disabled_error_handler(request: Request, exc: "CredentialDisabledError") -> JSONResponse:
    """Handle CredentialDisabledError with RFC 9457 format."""
    logger.warning("Credential disabled", credential_name=exc.name)
    return create_problem_details_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Credential Disabled",
        detail=exc.message,
        code="CREDENTIAL_DISABLED",
        retryable=False,
        instance=str(request.url),
    )


def credential_in_use_error_handler(request: Request, exc: "CredentialInUseError") -> JSONResponse:
    """Handle CredentialInUseError with RFC 9457 format."""
    logger.warning(
        "Blocked credential delete: still referenced by integrations",
        credential_name=exc.name,
        affected_integration_count=exc.total_count,
    )
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Credential In Use",
        detail=exc.message,
        code="CREDENTIAL_IN_USE",
        retryable=False,
        instance=str(request.url),
    )


def project_credential_in_use_error_handler(request: Request, exc: "ProjectCredentialInUseError") -> JSONResponse:
    """Handle ProjectCredentialInUseError with RFC 9457 format."""
    logger.warning(
        "Blocked project delete: credentials still referenced by integrations",
        project_name=exc.project_name,
        affected_integration_count=exc.total_integration_count,
    )
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Project Credentials In Use",
        detail=exc.message,
        code="PROJECT_CREDENTIALS_IN_USE",
        retryable=False,
        instance=str(request.url),
    )


def credential_error_handler(request: Request, exc: "CredentialError") -> JSONResponse:
    """Handle generic CredentialError with RFC 9457 format."""
    logger.error("Credential error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        problem_type=PROBLEM_TYPES["internal_error"],
        title="Credential Error",
        detail=exc.message,
        code="CREDENTIAL_ERROR",
        retryable=False,
        instance=str(request.url),
    )
