"""Unit tests for integration error handlers."""

import json
from unittest.mock import Mock
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.integrations.error_handlers import (
    integration_credential_not_found_handler,
    integration_credential_required_handler,
    integration_error_handler,
    integration_name_conflict_handler,
    integration_not_found_handler,
)
from syntara.integrations.exceptions import (
    IntegrationCredentialNotFoundError,
    IntegrationCredentialRequiredError,
    IntegrationError,
    IntegrationNameConflictError,
    IntegrationNotFoundError,
)

_INTEGRATION_ID = "00000000-0000-0000-0000-000000000001"


class TestIntegrationNotFoundHandler:
    """Tests for integration_not_found_handler."""

    def test_returns_404_with_rfc9457_format(self) -> None:
        request = Mock(spec=Request)
        request.url = f"https://api.example.com/integrations/{_INTEGRATION_ID}"

        exc = IntegrationNotFoundError(UUID(_INTEGRATION_ID))
        response = integration_not_found_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_not_found"]
        assert data["title"] == "Integration Not Found"
        assert data["detail"] == f"Integration {_INTEGRATION_ID} not found"
        assert data["code"] == "INTEGRATION_NOT_FOUND"
        assert data["retryable"] is False
        assert data["instance"] == f"https://api.example.com/integrations/{_INTEGRATION_ID}"


class TestIntegrationNameConflictHandler:
    """Tests for integration_name_conflict_handler."""

    def test_returns_409_with_rfc9457_format(self) -> None:
        request = Mock(spec=Request)
        request.url = "https://api.example.com/integrations"

        exc = IntegrationNameConflictError("duplicate")
        response = integration_name_conflict_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 409
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["name_conflict"]
        assert data["title"] == "Integration Name Conflict"
        assert data["detail"] == "Integration with name 'duplicate' already exists"
        assert data["code"] == "INTEGRATION_NAME_CONFLICT"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/integrations"


class TestIntegrationCredentialRequiredHandler:
    """Tests for integration_credential_required_handler."""

    def test_returns_422_with_rfc9457_format(self) -> None:
        request = Mock(spec=Request)
        request.url = f"https://api.example.com/integrations/{_INTEGRATION_ID}/validate"

        exc = IntegrationCredentialRequiredError("llm_provider")
        response = integration_credential_required_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 422
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["validation_error"]
        assert data["title"] == "Credential Required"
        assert data["code"] == "INTEGRATION_CREDENTIAL_REQUIRED"
        assert data["retryable"] is False
        assert "llm_provider" in data["detail"]


class TestIntegrationCredentialNotFoundHandler:
    """Tests for integration_credential_not_found_handler."""

    def test_returns_404_with_rfc9457_format(self) -> None:
        request = Mock(spec=Request)
        request.url = "https://api.example.com/integrations"

        credential_id = UUID(_INTEGRATION_ID)
        exc = IntegrationCredentialNotFoundError(credential_id)
        response = integration_credential_not_found_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_not_found"]
        assert data["title"] == "Credential Not Found"
        assert data["code"] == "INTEGRATION_CREDENTIAL_NOT_FOUND"
        assert data["retryable"] is False
        assert _INTEGRATION_ID in data["detail"]


class TestIntegrationErrorHandler:
    """Tests for integration_error_handler."""

    def test_returns_400_with_rfc9457_format(self) -> None:
        request = Mock(spec=Request)
        request.url = "https://api.example.com/integrations"

        exc = IntegrationError("Something went wrong")
        response = integration_error_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["integration_error"]
        assert data["title"] == "Integration Error"
        assert data["detail"] == "Something went wrong"
        assert data["code"] == "INTEGRATION_ERROR"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/integrations"
