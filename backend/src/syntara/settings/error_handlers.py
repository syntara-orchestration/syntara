"""RFC 9457 compliant error handlers for the settings domain."""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from syntara.settings.exceptions import (
        OptimisticLockError,
        SettingNotFoundError,
        SettingTypeError,
        SettingValidationError,
    )

logger = structlog.stdlib.get_logger(__name__)


def setting_validation_error_handler(request: Request, exc: "SettingValidationError") -> JSONResponse:
    """Handle SettingValidationError with RFC 9457 format."""
    logger.warning("Setting validation error", key=exc.key, detail=exc.detail)
    return create_problem_details_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Setting Validation Error",
        detail=exc.detail,
        code="SETTING_VALIDATION_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def setting_type_error_handler(request: Request, exc: "SettingTypeError") -> JSONResponse:
    """Handle SettingTypeError with RFC 9457 format."""
    logger.warning("Setting type error", key=exc.key, expected=exc.expected, actual=exc.actual)
    return create_problem_details_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Setting Type Error",
        detail=str(exc),
        code="SETTING_TYPE_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def setting_not_found_handler(request: Request, exc: "SettingNotFoundError") -> JSONResponse:
    """Handle SettingNotFoundError with RFC 9457 format."""
    logger.warning("Setting not found", key=exc.key)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Setting Not Found",
        detail=str(exc),
        code="SETTING_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def optimistic_lock_error_handler(request: Request, exc: "OptimisticLockError") -> JSONResponse:
    """Handle OptimisticLockError with RFC 9457 format."""
    logger.warning(
        "Setting version conflict",
        key=exc.key,
        current_version=exc.current_version,
        submitted_version=exc.submitted_version,
    )
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Setting Version Conflict",
        detail=str(exc),
        code="SETTING_VERSION_CONFLICT",
        retryable=True,
        instance=str(request.url),
    )
