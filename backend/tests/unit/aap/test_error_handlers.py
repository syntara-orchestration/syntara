"""Tests for AAP error handlers — RFC 9457 Problem Details mapping."""

import json
from typing import Any
from unittest.mock import MagicMock

from starlette.responses import JSONResponse

from syntara.aap.error_handlers import (
    aap_authentication_error_handler,
    aap_connection_error_handler,
    aap_not_configured_handler,
    aap_upstream_error_handler,
)
from syntara.aap.exceptions import (
    AAPAuthenticationError,
    AAPConnectionError,
    AAPNotConfiguredError,
    AAPUpstreamError,
)


def _mock_request(url: str = "https://example.com/api/v1/aap/organizations") -> MagicMock:
    request = MagicMock()
    request.url = url
    return request


def _parse_body(response: JSONResponse) -> dict[str, Any]:
    """Parse the JSON response body with proper typing."""
    result: dict[str, Any] = json.loads(bytes(response.body))
    return result


class TestAAPNotConfiguredHandler:
    """Tests for aap_not_configured_handler."""

    def test_returns_503(self) -> None:
        exc = AAPNotConfiguredError("AAP not configured")
        response = aap_not_configured_handler(_mock_request(), exc)
        assert response.status_code == 503

    def test_response_body_has_problem_details(self) -> None:
        exc = AAPNotConfiguredError("AAP not configured")
        response = aap_not_configured_handler(_mock_request(), exc)
        body = _parse_body(response)
        assert body["code"] == "AAP_NOT_CONFIGURED"
        assert body["retryable"] is False


class TestAAPConnectionErrorHandler:
    """Tests for aap_connection_error_handler."""

    def test_returns_502(self) -> None:
        exc = AAPConnectionError("Connection failed")
        response = aap_connection_error_handler(_mock_request(), exc)
        assert response.status_code == 502

    def test_response_body_has_problem_details(self) -> None:
        exc = AAPConnectionError("Connection failed")
        response = aap_connection_error_handler(_mock_request(), exc)
        body = _parse_body(response)
        assert body["code"] == "AAP_CONNECTION_ERROR"
        assert body["retryable"] is True


class TestAAPAuthenticationErrorHandler:
    """Tests for aap_authentication_error_handler."""

    def test_returns_502(self) -> None:
        exc = AAPAuthenticationError("Auth failed")
        response = aap_authentication_error_handler(_mock_request(), exc)
        assert response.status_code == 502

    def test_not_retryable(self) -> None:
        exc = AAPAuthenticationError("Auth failed")
        response = aap_authentication_error_handler(_mock_request(), exc)
        body = _parse_body(response)
        assert body["code"] == "AAP_AUTHENTICATION_ERROR"
        assert body["retryable"] is False


class TestAAPUpstreamErrorHandler:
    """Tests for aap_upstream_error_handler."""

    def test_returns_502(self) -> None:
        exc = AAPUpstreamError("Upstream error")
        response = aap_upstream_error_handler(_mock_request(), exc)
        assert response.status_code == 502

    def test_retryable(self) -> None:
        exc = AAPUpstreamError("Upstream error")
        response = aap_upstream_error_handler(_mock_request(), exc)
        body = _parse_body(response)
        assert body["code"] == "AAP_UPSTREAM_ERROR"
        assert body["retryable"] is True
