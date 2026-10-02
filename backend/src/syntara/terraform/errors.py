"""TFE error contract (SDP R10.2)."""

from __future__ import annotations

from enum import StrEnum
from http import HTTPStatus
from typing import Any


class TFEErrorCode(StrEnum):
    """Stable, machine-readable TFE step error codes."""

    CONFIG_MISSING = "CONFIG_MISSING"
    AUTH_FAILED = "AUTH_FAILED"
    NOT_FOUND = "NOT_FOUND"
    STATE_CONFLICT = "STATE_CONFLICT"
    VALIDATION = "VALIDATION"
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
    HTTPStatus.UNAUTHORIZED: TFEErrorCode.AUTH_FAILED,
    HTTPStatus.FORBIDDEN: TFEErrorCode.AUTH_FAILED,
    HTTPStatus.NOT_FOUND: TFEErrorCode.NOT_FOUND,
    HTTPStatus.CONFLICT: TFEErrorCode.STATE_CONFLICT,
    HTTPStatus.UNPROCESSABLE_ENTITY: TFEErrorCode.VALIDATION,
    HTTPStatus.TOO_MANY_REQUESTS: TFEErrorCode.RATE_LIMITED,
}


def map_http_status_to_error(
    status_code: int,
    message: str,
    *,
    mutating: bool = False,
) -> TFEError:
    """Map an HTTP status from TFE to the SDP error contract."""
    code = _STATUS_TO_CODE.get(status_code)
    if code is None and status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        code = TFEErrorCode.TRANSIENT
    if code is None:
        code = TFEErrorCode.VALIDATION
    retryable = code in {TFEErrorCode.RATE_LIMITED, TFEErrorCode.TRANSIENT} and not mutating
    return TFEError(message, error_code=code, http_status=status_code, retryable=retryable)
