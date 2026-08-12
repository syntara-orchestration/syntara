"""Unit tests for authentication error handlers."""

import json
from typing import Any
from unittest.mock import Mock

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.auth.error_handlers import (
    authentication_required_handler,
    invalid_token_handler,
    refresh_token_revoked_handler,
    token_expired_handler,
)
from syntara.auth.exceptions import (
    AuthenticationRequiredError,
    InvalidTokenError,
    RefreshTokenRevokedError,
    TokenExpiredError,
)


def _mock_request() -> Mock:
    request = Mock(spec=Request)
    request.url = "https://api.example.com/test"
    request.method = "GET"
    return request


def _parse_body(response: JSONResponse) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(bytes(response.body).decode())
    return result


class TestAuthenticationRequiredHandler:
    """Tests for authentication_required_handler."""

    def test_returns_401(self) -> None:
        response = authentication_required_handler(_mock_request(), AuthenticationRequiredError())
        assert response.status_code == 401

    def test_rfc9457_body(self) -> None:
        response = authentication_required_handler(_mock_request(), AuthenticationRequiredError())
        data = _parse_body(response)
        assert data["code"] == "AUTHENTICATION_REQUIRED"
        assert data["title"] == "Unauthorized"
        assert data["retryable"] is False

    def test_uses_custom_message(self) -> None:
        exc = AuthenticationRequiredError("Custom message")
        response = authentication_required_handler(_mock_request(), exc)
        data = _parse_body(response)
        assert data["detail"] == "Custom message"


class TestTokenExpiredHandler:
    """Tests for token_expired_handler."""

    def test_returns_401(self) -> None:
        response = token_expired_handler(_mock_request(), TokenExpiredError())
        assert response.status_code == 401

    def test_rfc9457_body(self) -> None:
        response = token_expired_handler(_mock_request(), TokenExpiredError())
        data = _parse_body(response)
        assert data["code"] == "TOKEN_EXPIRED"
        assert data["title"] == "Token Expired"
        assert data["retryable"] is False


class TestInvalidTokenHandler:
    """Tests for invalid_token_handler."""

    def test_returns_401(self) -> None:
        response = invalid_token_handler(_mock_request(), InvalidTokenError())
        assert response.status_code == 401

    def test_rfc9457_body(self) -> None:
        response = invalid_token_handler(_mock_request(), InvalidTokenError())
        data = _parse_body(response)
        assert data["code"] == "INVALID_TOKEN"
        assert data["title"] == "Unauthorized"


class TestRefreshTokenRevokedHandler:
    """Tests for refresh_token_revoked_handler."""

    def test_returns_401(self) -> None:
        response = refresh_token_revoked_handler(_mock_request(), RefreshTokenRevokedError())
        assert response.status_code == 401

    def test_rfc9457_body(self) -> None:
        response = refresh_token_revoked_handler(_mock_request(), RefreshTokenRevokedError())
        data = _parse_body(response)
        assert data["code"] == "REFRESH_TOKEN_REVOKED"
        assert data["title"] == "Unauthorized"
