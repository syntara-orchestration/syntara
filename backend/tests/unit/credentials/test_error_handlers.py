"""Tests for credential RFC 9457 error handlers."""

import json
from unittest.mock import Mock

from fastapi import Request

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.credentials.error_handlers import (
    credential_decryption_error_handler,
    credential_error_handler,
    credential_name_conflict_handler,
    credential_not_found_handler,
    credential_validation_error_handler,
)
from syntara.credentials.exceptions import (
    CredentialDecryptionError,
    CredentialError,
    CredentialNameConflictError,
    CredentialNotFoundError,
    CredentialValidationError,
)


def _mock_request() -> Mock:
    request = Mock(spec=Request)
    request.url = "https://api.example.com/api/v1/credentials/test-id"
    return request


class TestCredentialNotFoundHandler:
    """Tests for 404 handler."""

    def test_returns_404(self) -> None:
        request = _mock_request()
        exc = CredentialNotFoundError("not found")
        response = credential_not_found_handler(request, exc)
        assert response.status_code == 404
        body = json.loads(bytes(response.body))
        assert body["code"] == "CREDENTIAL_NOT_FOUND"
        assert body["type"] == PROBLEM_TYPES["resource_not_found"]


class TestCredentialNameConflictHandler:
    """Tests for 409 handler."""

    def test_returns_409(self) -> None:
        request = _mock_request()
        exc = CredentialNameConflictError("duplicate-name")
        response = credential_name_conflict_handler(request, exc)
        assert response.status_code == 409
        body = json.loads(bytes(response.body))
        assert body["code"] == "CREDENTIAL_NAME_CONFLICT"


class TestCredentialValidationHandler:
    """Tests for 422 handler."""

    def test_returns_422(self) -> None:
        request = _mock_request()
        exc = CredentialValidationError("invalid field")
        response = credential_validation_error_handler(request, exc)
        assert response.status_code == 422
        body = json.loads(bytes(response.body))
        assert body["code"] == "CREDENTIAL_VALIDATION_ERROR"


class TestCredentialDecryptionHandler:
    """Tests for 500 handler — generic message for security."""

    def test_returns_500_with_generic_message(self) -> None:
        request = _mock_request()
        exc = CredentialDecryptionError("wrong key details here")
        response = credential_decryption_error_handler(request, exc)
        assert response.status_code == 500
        body = json.loads(bytes(response.body))
        assert body["code"] == "CREDENTIAL_DECRYPTION_ERROR"
        assert "wrong key" not in body["detail"]
        assert body["detail"] == "An error occurred while processing credential data"


class TestCredentialErrorHandler:
    """Tests for generic 400 handler."""

    def test_returns_400(self) -> None:
        request = _mock_request()
        exc = CredentialError("generic error")
        response = credential_error_handler(request, exc)
        assert response.status_code == 400
        body = json.loads(bytes(response.body))
        assert body["code"] == "CREDENTIAL_ERROR"
