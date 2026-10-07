"""Unit tests for shared health-check HTTP error classification."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import httpx
import pytest

from syntara.integrations.adapters.protocol import (
    HealthCheckErrorType,
    _response_body_suggests_expired_token,
    classify_http_error,
)


def _http_status_error(status: int, body: str = "") -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.com/health")
    response = httpx.Response(status, request=request, text=body)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


def test_classify_empty_errors() -> None:
    error_type, message = classify_http_error([])
    assert error_type == HealthCheckErrorType.CONNECTION_ERROR
    assert message == "Request failed: unknown"


def test_classify_non_http_error() -> None:
    error_type, message = classify_http_error([RuntimeError("boom")])
    assert error_type == HealthCheckErrorType.CONNECTION_ERROR
    assert "RuntimeError" in message


def test_classify_401_auth_failure() -> None:
    error_type, message = classify_http_error([_http_status_error(401, "unauthorized")])
    assert error_type == HealthCheckErrorType.AUTH_FAILURE
    assert "Authentication failed: HTTP 401" in message


@pytest.mark.parametrize(
    "body",
    [
        "token has expired",
        "token is expired",
        "jwt expired",
        "Credential Expired",
    ],
)
def test_classify_401_token_expired(body: str) -> None:
    error_type, message = classify_http_error([_http_status_error(401, body)])
    assert error_type == HealthCheckErrorType.TOKEN_EXPIRED
    assert "Token expired: HTTP 401" in message


def test_classify_403_authorization_failure() -> None:
    error_type, message = classify_http_error([_http_status_error(403)])
    assert error_type == HealthCheckErrorType.AUTHORIZATION_FAILURE
    assert "Authorization failed: HTTP 403" in message


def test_classify_429_rate_limit() -> None:
    error_type, message = classify_http_error([_http_status_error(429)])
    assert error_type == HealthCheckErrorType.RATE_LIMIT
    assert "Rate limit exceeded: HTTP 429" in message


def test_classify_405_method_not_allowed() -> None:
    error_type, message = classify_http_error([_http_status_error(405)])
    assert error_type == HealthCheckErrorType.CONNECTION_ERROR
    assert "Method not allowed: HTTP 405" in message


def test_classify_404_not_found() -> None:
    error_type, message = classify_http_error([_http_status_error(404)])
    assert error_type == HealthCheckErrorType.CONNECTION_ERROR
    assert "Endpoint not found: HTTP 404" in message


def test_classify_other_http_status() -> None:
    error_type, message = classify_http_error([_http_status_error(500)])
    assert error_type == HealthCheckErrorType.CONNECTION_ERROR
    assert message == "HTTP error: 500"


def test_classify_skips_non_http_then_classifies_http() -> None:
    error_type, message = classify_http_error([ValueError("nope"), _http_status_error(403)])
    assert error_type == HealthCheckErrorType.AUTHORIZATION_FAILURE
    assert "403" in message


def test_response_body_suggests_expired_token_handles_read_errors() -> None:
    response = MagicMock(spec=httpx.Response)
    type(response).text = PropertyMock(side_effect=RuntimeError("closed"))
    assert _response_body_suggests_expired_token(response) is False
