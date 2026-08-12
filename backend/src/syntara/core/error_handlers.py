"""RFC 9457 compliant error handlers for FastAPI - Core Domain.

This module provides centralized error handling utilities and framework-level
error handlers that are shared across all domains.
"""

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError

logger = structlog.stdlib.get_logger(__name__)

_INSTANCE_MAX_LEN = 2048
_DETAIL_MAX_LEN = 2000  # must match ErrorData.detail max_length

INTERNAL_SERVER_ERROR: str = "Internal Server Error"
REQUEST_VALIDATION_ERROR: str = "Request Validation Error"

# Problem type URIs for common error scenarios
PROBLEM_TYPES = {
    "unauthorized": "https://api.example.com/errors/unauthorized",
    "forbidden": "https://api.example.com/errors/forbidden",
    "token_expired": "https://api.example.com/errors/token-expired",
    "resource_ownership": "https://api.example.com/errors/resource-ownership",
    "resource_not_found": "https://api.example.com/errors/resource-not-found",
    "name_conflict": "https://api.example.com/errors/name-conflict",
    "resource_conflict": "https://api.example.com/errors/resource-conflict",
    "method_not_allowed": "https://api.example.com/errors/method-not-allowed",
    "validation_error": "https://api.example.com/errors/validation-error",
    "integrity_constraint": "https://api.example.com/errors/integrity-constraint",
    "service_unavailable": "https://api.example.com/errors/service-unavailable",
    "resource_not_published": "https://api.example.com/errors/resource-not-published",
    "payload_too_large": "https://api.example.com/errors/payload-too-large",
    "provider_error": "https://api.example.com/errors/provider-error",
    "integration_error": "https://api.example.com/errors/integration-error",
    "internal_error": "https://api.example.com/errors/internal-error",
    "publish_validation": "https://api.example.com/errors/publish-validation",
    "rate_limited": "https://api.example.com/errors/rate-limited",
}


_ERROR_RESPONSE_EXAMPLES: dict[int, dict[str, object]] = {
    400: {
        "type": "https://api.example.com/errors/bad-request",
        "title": "Bad Request",
        "detail": "The request was malformed or contained invalid parameters",
        "code": "BAD_REQUEST",
        "retryable": False,
    },
    401: {
        "type": "https://api.example.com/errors/unauthorized",
        "title": "Unauthorized",
        "detail": "Authentication is required to access this resource",
        "code": "UNAUTHORIZED",
        "retryable": False,
    },
    403: {
        "type": "https://api.example.com/errors/forbidden",
        "title": "Forbidden",
        "detail": "You do not have permission to access this resource",
        "code": "FORBIDDEN",
        "retryable": False,
    },
    404: {
        "type": "https://api.example.com/errors/not-found",
        "title": "Resource Not Found",
        "detail": "No resource exists with the provided identifier",
        "code": "NOT_FOUND",
        "retryable": False,
        "instance": "/api/v1/workflows",
    },
    409: {
        "type": "https://api.example.com/errors/conflict",
        "title": "Conflict",
        "detail": "The request conflicts with the current state of the resource",
        "code": "CONFLICT",
        "retryable": False,
    },
    422: {
        "type": "https://api.example.com/errors/validation-error",
        "title": "Validation Error",
        "detail": "Field 'name' must be between 1 and 255 characters",
        "code": "VALIDATION_ERROR",
        "retryable": False,
        "instance": "/api/v1/workflows",
    },
    429: {
        "type": "https://api.example.com/errors/rate-limited",
        "title": "Too Many Requests",
        "detail": "Rate limit exceeded. Try again in 60 seconds.",
        "code": "RATE_LIMITED",
        "retryable": True,
    },
    500: {
        "type": "https://api.example.com/errors/internal-error",
        "title": "Internal Server Error",
        "detail": "An unexpected error occurred",
        "code": "INTERNAL_ERROR",
        "retryable": True,
    },
}


def problem_details_response_map() -> dict[int | str, dict[str, Any]]:
    """App-level error responses so FastAPI includes ErrorData in the generated OpenAPI schema.

    Uses ``model`` for automatic schema registration in ``components/schemas``
    and ``content`` with ``application/json`` to attach RFC 9457 examples.
    The media type is later renamed to ``application/problem+json`` by
    :func:`apply_rfc9457_media_types`.
    """
    from syntara.core.models.error import ErrorData  # noqa: PLC0415

    error_schema = {"$ref": "#/components/schemas/ErrorData"}
    descriptions: dict[int, str] = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Validation Error",
        429: "Too Many Requests",
        500: "Internal Server Error",
    }

    return {
        code: {
            "model": ErrorData,
            "description": desc,
            "content": {
                "application/json": {
                    "schema": error_schema,
                    "example": _ERROR_RESPONSE_EXAMPLES[code],
                },
            },
        }
        for code, desc in descriptions.items()
    }


def apply_rfc9457_media_types(spec: dict[str, Any]) -> None:
    """Rename ``application/json`` → ``application/problem+json`` for error responses.

    FastAPI always generates ``application/json`` as the media type.  RFC 9457
    requires ``application/problem+json`` for error responses.  Call this after
    ``app.openapi()`` to fix the generated spec.
    """
    error_codes = frozenset(str(c) for c in _ERROR_RESPONSE_EXAMPLES)
    for path_item in spec.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            for code, response in operation.get("responses", {}).items():
                if str(code) not in error_codes or not isinstance(response, dict):
                    continue
                content = response.get("content", {})
                if "application/json" in content:
                    content["application/problem+json"] = content.pop("application/json")


if TYPE_CHECKING:
    from syntara.core.exceptions import SafeValueError


def create_problem_details_response(
    status_code: int,
    problem_type: str,
    title: str,
    detail: str,
    code: str,
    *,
    retryable: bool = False,
    instance: str | None = None,
) -> JSONResponse:
    """Create RFC 9457 compliant error response.

    Args:
        status_code: HTTP status code
        problem_type: URI identifying the problem type
        title: Short summary of the problem
        detail: Detailed explanation of the problem
        code: Machine-readable error code
        retryable: Whether the error is retryable
        instance: URI identifying the specific occurrence

    Returns:
        JSONResponse with RFC 9457 Problem Details format

    """
    from syntara.core.models.error import ErrorData  # noqa: PLC0415

    # Truncate instance URI to fit ErrorData max_length (OIDC callbacks can have very long query strings)
    if instance and len(instance) > _INSTANCE_MAX_LEN:
        instance = instance[:_INSTANCE_MAX_LEN]

    # Truncate detail to fit ErrorData max_length (concatenated validation errors can exceed it)
    if len(detail) > _DETAIL_MAX_LEN:
        detail = detail[: _DETAIL_MAX_LEN - 3] + "..."

    error_data = ErrorData(
        type=problem_type,
        title=title,
        detail=detail,
        code=code,
        retryable=retryable,
        instance=instance,
    )

    logger.debug("Created ErrorData", error_data=error_data.to_dict())

    return JSONResponse(
        status_code=status_code,
        content=error_data.to_dict(),
        media_type="application/problem+json",
    )


def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTPException with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: HTTP exception

    Returns:
        RFC 9457 compliant error response

    """
    from syntara.core.utils.retry import is_retryable_error  # noqa: PLC0415 — circular dep

    # Extract detail from HTTPException
    detail_content = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

    # Map status codes to problem types and titles
    status_mapping = {
        400: ("validation_error", "Bad Request"),
        401: ("unauthorized", "Unauthorized"),
        403: ("forbidden", "Forbidden"),
        404: ("resource_not_found", "Not Found"),
        405: ("method_not_allowed", "Method Not Allowed"),
        409: ("name_conflict", "Conflict"),
        422: ("validation_error", "Unprocessable Entity"),
        500: ("internal_error", "Internal Server Error"),
        503: ("service_unavailable", "Service Unavailable"),
    }

    problem_key, title = status_mapping.get(exc.status_code, ("internal_error", "Error"))

    logger.error("HTTPException", problem_key=problem_key, title=title, exc_info=exc)
    return create_problem_details_response(
        status_code=exc.status_code,
        problem_type=PROBLEM_TYPES[problem_key],
        title=title,
        detail=detail_content,
        code=f"HTTP_{exc.status_code}",
        retryable=is_retryable_error(exc),
        instance=str(request.url),
    )


def validation_error_handler(request: Request, exc: PydanticValidationError | RequestValidationError) -> JSONResponse:
    """Handle Pydantic ValidationError with RFC 9457 format."""
    logger.error("Validation error", exc_info=exc)

    # Format Pydantic validation errors for user display.
    # Strip internal path prefixes (body, configuration, provider type discriminator)
    # and the "Value error, " prefix that Pydantic adds to field_validator messages.
    loc_noise = {"body", "configuration", "oidc", "ldap", "saml"}
    error_details = []
    for error in exc.errors():
        if error["loc"]:
            parts = [str(x) for x in error["loc"] if str(x) not in loc_noise]
            field = " -> ".join(parts) if parts else "root"
        else:
            field = "root"
        msg = str(error["msg"])
        msg = msg.removeprefix("Value error, ")
        error_details.append(f"{field}: {msg}")

    detail = "Validation failed: " + "; ".join(error_details)

    return create_problem_details_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        problem_type=PROBLEM_TYPES["validation_error"],
        title=REQUEST_VALIDATION_ERROR,
        detail=detail,
        code="REQUEST_VALIDATION_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Handle SQLAlchemy IntegrityError with RFC 9457 format.

    Returns 409 for name conflicts (handled by ProviderNameConflictError handler)
    and 400 for other constraint violations.
    """
    # Log the full error for debugging but don't expose it to users
    logger.error("Database integrity constraint violation", exc_info=exc)

    # Check if this is likely a name conflict by examining the exception type and message
    # without exposing the actual message content
    error_str = str(exc).lower()
    is_name_conflict = "unique" in error_str and "name" in error_str

    if is_name_conflict:
        # This should not normally happen as name conflicts should be caught by
        # ProviderNameConflictError handler, but handle it as 409 for consistency
        return create_problem_details_response(
            status_code=status.HTTP_409_CONFLICT,
            problem_type=PROBLEM_TYPES["name_conflict"],
            title="Name Conflict",
            detail="A resource with this name already exists",
            code="INTEGRITY_NAME_CONFLICT",
            retryable=False,
            instance=str(request.url),
        )

    # Non-name-conflict constraint violations return 400 Bad Request
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        problem_type=PROBLEM_TYPES["integrity_constraint"],
        title="Integrity Constraint Violation",
        detail="A database constraint was violated - please check your input data",
        code="INTEGRITY_CONSTRAINT_VIOLATION",
        retryable=False,
        instance=str(request.url),
    )


def safe_value_error_handler(request: Request, exc: "SafeValueError") -> JSONResponse:
    """Handle SafeValueError with RFC 9457 format.

    SafeValueError is designed to contain user-safe messages that can be
    directly exposed in API responses without security concerns.
    """
    logger.error("Safe value error", exc_info=exc)

    detail = str(exc) if str(exc) else "Invalid input value"

    return create_problem_details_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Validation Error",
        detail=detail,
        code="VALIDATION_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle generic ValueError with RFC 9457 format.

    Generic ValueError instances may contain internal implementation details,
    so we return a safe generic message to prevent information leakage.

    Note: SafeValueError instances are handled by safe_value_error_handler
    via the @fastapi_exception decorator registration system.
    """
    logger.error("Value error", exc_info=exc)

    # Use generic message to prevent exposing internal details
    detail = "Invalid input value"

    return create_problem_details_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Validation Error",
        detail=detail,
        code="VALIDATION_ERROR",
        retryable=False,
        instance=str(request.url),
    )


def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with RFC 9457 format.

    This is the catch-all handler for any unhandled exceptions.
    It logs the full exception details for debugging while returning
    a generic error to the client for security.
    """
    logger.error("Unhandled exception in API request", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        problem_type=PROBLEM_TYPES["internal_error"],
        title=INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred while processing the request",
        code="INTERNAL_SERVER_ERROR",
        retryable=True,
        instance=str(request.url),
    )
