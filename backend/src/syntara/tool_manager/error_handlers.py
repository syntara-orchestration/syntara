"""RFC 9457 compliant error handlers for Tool Manager domain.

This module provides error handling for tool and provider-specific exceptions.
"""

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from syntara.tool_manager.exceptions import (
        ProviderNameConflictError,
        ProviderNotFoundError,
        ToolBulkUpdateValidationError,
        ToolManagerError,
        ToolNotFoundError,
        ToolRefreshError,
    )

logger = structlog.stdlib.get_logger(__name__)


def tool_not_found_handler(request: Request, exc: "ToolNotFoundError") -> JSONResponse:
    """Handle ToolNotFoundError with RFC 9457 format."""
    logger.error("Tool not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Tool Not Found",
        detail=exc.message,
        code="TOOL_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def tool_provider_not_found_handler(request: Request, exc: "ProviderNotFoundError") -> JSONResponse:
    """Handle ProviderNotFoundError with RFC 9457 format."""
    logger.error("Provider not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Provider Not Found",
        detail=exc.message,
        code="PROVIDER_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def tool_provider_name_conflict_handler(request: Request, exc: "ProviderNameConflictError") -> JSONResponse:
    """Handle ProviderNameConflictError with RFC 9457 format."""
    logger.error("Provider name conflict", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["name_conflict"],
        title="Provider Name Conflict",
        detail=exc.message,
        code="PROVIDER_NAME_CONFLICT",
        retryable=False,
        instance=str(request.url),
    )


def tool_refresh_error_handler(request: Request, exc: "ToolRefreshError") -> JSONResponse:
    """Handle ProviderError with RFC 9457 format."""
    logger.error("Tool refresh error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        problem_type=PROBLEM_TYPES["provider_error"],
        title="Tool Refresh Error",
        detail=exc.message,
        code="TOOL_REFRESH_ERROR",
        retryable=True,
        instance=str(request.url),
    )


def tool_bulk_update_validation_error_handler(request: Request, exc: "ToolBulkUpdateValidationError") -> JSONResponse:
    """Handle tool ValidationError with RFC 9457 format."""
    logger.error("Tool validation error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Tool Bulk Update Validation Error",
        detail=exc.message,
        code="TOOL_BULK_UPDATE_VALIDATION_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def tool_manager_error_handler(request: Request, exc: "ToolManagerError") -> JSONResponse:
    """Handle generic ToolManagerError with RFC 9457 format."""
    logger.error("Tool manager error", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        problem_type=PROBLEM_TYPES["provider_error"],
        title="Tool Manager Error",
        detail=exc.message,
        code="TOOL_MANAGER_ERROR",
        retryable=False,
        instance=str(request.url),
    )
