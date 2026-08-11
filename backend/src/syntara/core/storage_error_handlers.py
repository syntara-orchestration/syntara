"""RFC 9457 compliant error handlers for StorageBackend errors.

Handles database/backend connectivity failures and missing secret data.
"""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from syntara.core.storage_exceptions import (
        StorageBackendError,
        StorageBackendNotFoundError,
        StorageBackendUnavailableError,
    )

logger = structlog.stdlib.get_logger(__name__)


def storage_backend_unavailable_handler(request: Request, exc: "StorageBackendUnavailableError") -> JSONResponse:
    """Handle StorageBackendUnavailableError with RFC 9457 format (503)."""
    logger.error("Storage backend unavailable", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        problem_type=PROBLEM_TYPES["service_unavailable"],
        title="Storage Backend Unavailable",
        detail="The secret storage backend is temporarily unavailable. Please retry later.",
        code="STORAGE_BACKEND_UNAVAILABLE",
        retryable=True,
        instance=str(request.url),
    )


def storage_backend_not_found_handler(request: Request, exc: "StorageBackendNotFoundError") -> JSONResponse:
    """Handle StorageBackendNotFoundError with RFC 9457 format (404)."""
    logger.warning("Secret data not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Secret Data Not Found",
        detail="The requested secret data could not be found in the storage backend.",
        code="STORAGE_SECRET_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def storage_backend_error_handler(request: Request, exc: "StorageBackendError") -> JSONResponse:
    """Handle generic StorageBackendError with RFC 9457 format (500)."""
    logger.error("Storage backend error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        problem_type=PROBLEM_TYPES["internal_error"],
        title="Storage Backend Error",
        detail="An error occurred while accessing the secret storage backend.",
        code="STORAGE_BACKEND_ERROR",
        retryable=False,
        instance=str(request.url),
    )
