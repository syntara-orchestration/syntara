"""TFE error contract (SDP R10.2).

HTTP responses from TFE are mapped to stable error codes: authentication (401),
authorization (403), remote rejection (4xx including 400/422 and unmapped client
errors), not-found/conflict/rate-limit, and transient (5xx). Local invalid input
uses ``VALIDATION`` without going through ``map_http_status_to_error``.
"""

from __future__ import annotations

import re
from enum import StrEnum
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Collection

_REDACTED = "[REDACTED]"
_MIN_SECRET_LENGTH = 4

_BEARER_PATTERN = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_AUTHORIZATION_HEADER_PATTERN = re.compile(r"Authorization:\s*\S+", re.IGNORECASE)


def redact_sensitive_content(text: str, secrets: Collection[str] | None = None) -> str:
    """Replace known secrets and auth header patterns in error text."""
    if not text:
        return text
    result = text
    if secrets:
        for value in sorted(
            (s for s in secrets if s and len(s) >= _MIN_SECRET_LENGTH),
            key=len,
            reverse=True,
        ):
            if value in result:
                result = result.replace(value, _REDACTED)
    result = _BEARER_PATTERN.sub(f"Bearer {_REDACTED}", result)
    return _AUTHORIZATION_HEADER_PATTERN.sub(f"Authorization: {_REDACTED}", result)


class TFEErrorCode(StrEnum):
    """Stable, machine-readable TFE step error codes."""

    CONFIG_MISSING = "CONFIG_MISSING"
    AUTH_FAILED = "AUTH_FAILED"
    AUTHZ_FAILED = "AUTHZ_FAILED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"  # noqa: S105
    UNREACHABLE = "UNREACHABLE"
    NOT_FOUND = "NOT_FOUND"
    STATE_CONFLICT = "STATE_CONFLICT"
    VALIDATION = "VALIDATION"
    TFE_REJECTED = "TFE_REJECTED"
    RATE_LIMITED = "RATE_LIMITED"
    TRANSIENT = "TRANSIENT"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


class TFEError(Exception):
    """Structured error raised by the TFE client and activities."""

    def __init__(
        self,
        message: str,
        *,
        error_code: TFEErrorCode,
        http_status: int | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a structured TFE error."""
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.http_status = http_status
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize for activity failure payloads."""
        return {
            "errorCode": self.error_code.value,
            "message": self.message,
            "httpStatus": self.http_status,
            "retryable": self.retryable,
            **self.details,
        }


_STATUS_TO_CODE: dict[int, TFEErrorCode] = {
    HTTPStatus.BAD_REQUEST: TFEErrorCode.TFE_REJECTED,
    HTTPStatus.UNAUTHORIZED: TFEErrorCode.AUTH_FAILED,
    HTTPStatus.FORBIDDEN: TFEErrorCode.AUTHZ_FAILED,
    HTTPStatus.NOT_FOUND: TFEErrorCode.NOT_FOUND,
    HTTPStatus.CONFLICT: TFEErrorCode.STATE_CONFLICT,
    HTTPStatus.UNPROCESSABLE_ENTITY: TFEErrorCode.TFE_REJECTED,
    HTTPStatus.TOO_MANY_REQUESTS: TFEErrorCode.RATE_LIMITED,
}

_EXPIRED_TOKEN_MARKERS = (
    "expired",
    "token has expired",
    "token is expired",
    "jwt expired",
    "credential expired",
)


def _looks_like_expired_token(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _EXPIRED_TOKEN_MARKERS)


def map_http_status_to_error(
    status_code: int,
    message: str,
    *,
    mutating: bool = False,
) -> TFEError:
    """Map an HTTP status from TFE to the SDP error contract."""
    if status_code == HTTPStatus.UNAUTHORIZED and _looks_like_expired_token(message):
        return TFEError(
            message,
            error_code=TFEErrorCode.TOKEN_EXPIRED,
            http_status=status_code,
            retryable=False,
        )

    code = _STATUS_TO_CODE.get(status_code)
    if code is None and status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        code = TFEErrorCode.TRANSIENT
    if code is None:
        code = TFEErrorCode.TFE_REJECTED

    if code == TFEErrorCode.AUTH_FAILED:
        message = message or "Authentication failed: invalid or missing TFE token"
    elif code == TFEErrorCode.AUTHZ_FAILED:
        message = message or "Authorization failed: token lacks permission for this TFE operation"

    retryable = code in {TFEErrorCode.RATE_LIMITED, TFEErrorCode.TRANSIENT} and not mutating
    return TFEError(message, error_code=code, http_status=status_code, retryable=retryable)
