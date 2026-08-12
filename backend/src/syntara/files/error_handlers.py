"""RFC 9457 compliant error handlers for Files domain.

This module provides error handling for file processing and validation exceptions.
"""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from syntara.files.exceptions import (
        FileContentNotFoundError,
        FileError,
        FileIntegrityError,
        FileStorageUnavailableError,
        FileValidationError,
    )

logger = structlog.stdlib.get_logger(__name__)


def file_validation_error_handler(request: Request, exc: "FileValidationError") -> JSONResponse:
    """Handle file ValidationError with RFC 9457 format."""
    logger.error("File validation error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="File Validation Error",
        detail=exc.message,
        code="FILE_VALIDATION_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def file_not_found_error_handler(request: Request, exc: "FileContentNotFoundError") -> JSONResponse:
    """Handle FileNotFoundError with RFC 9457 format (404)."""
    logger.warning("File not found in storage", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="File Not Found",
        detail="The requested file could not be found",
        code="FILE_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def file_integrity_error_handler(request: Request, exc: "FileIntegrityError") -> JSONResponse:
    """Handle FileIntegrityError with RFC 9457 format (500)."""
    logger.error("File integrity verification failed", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        problem_type=PROBLEM_TYPES["internal_error"],
        title="File Integrity Error",
        detail="File integrity verification failed",
        code="FILE_INTEGRITY_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def file_storage_unavailable_handler(request: Request, exc: "FileStorageUnavailableError") -> JSONResponse:
    """Handle FileStorageUnavailableError with RFC 9457 format (503)."""
    logger.warning("File storage not configured", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        problem_type=PROBLEM_TYPES["service_unavailable"],
        title="File Storage Unavailable",
        detail="File storage is not configured. Contact an administrator.",
        code="FILE_STORAGE_UNAVAILABLE",
        retryable=False,
        instance=str(request.url),
    )


def file_error_handler(request: Request, exc: "FileError") -> JSONResponse:
    """Handle generic FileError with RFC 9457 format (502)."""
    logger.error("File storage error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_502_BAD_GATEWAY,
        problem_type=PROBLEM_TYPES["service_unavailable"],
        title="File Storage Error",
        detail="File storage backend unavailable",
        code="FILE_STORAGE_ERROR",
        retryable=True,
        instance=str(request.url),
    )
