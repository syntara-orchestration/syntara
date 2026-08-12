"""Unit tests for service account error handlers."""

import json
from unittest.mock import MagicMock

from fastapi import status

from syntara.service_accounts.error_handlers import (
    sa_credential_expiration_exceeded_handler,
    sa_credential_expiration_in_past_handler,
    sa_credential_limit_handler,
    sa_credential_not_found_handler,
    service_account_error_handler,
    service_account_name_conflict_handler,
    service_account_not_found_handler,
)
from syntara.service_accounts.exceptions import (
    CredentialExpirationExceededError,
    CredentialExpirationInPastError,
    ServiceAccountCredentialLimitError,
    ServiceAccountCredentialNotFoundError,
    ServiceAccountError,
    ServiceAccountNameConflictError,
    ServiceAccountNotFoundError,
)


class TestServiceAccountNotFoundHandler:
    """Tests for 404 error handler."""

    def test_returns_404(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts/123"
        exc = ServiceAccountNotFoundError("Service account 123 not found")
        response = service_account_not_found_handler(request, exc)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_response_contains_detail(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts/123"
        exc = ServiceAccountNotFoundError("Service account 123 not found")
        response = service_account_not_found_handler(request, exc)
        body = json.loads(bytes(response.body))
        assert body["detail"] == "Service account 123 not found"
        assert body["code"] == "SERVICE_ACCOUNT_NOT_FOUND"


class TestServiceAccountNameConflictHandler:
    """Tests for 409 conflict error handler."""

    def test_returns_409(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts"
        exc = ServiceAccountNameConflictError("duplicate")
        response = service_account_name_conflict_handler(request, exc)
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_response_contains_name(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts"
        exc = ServiceAccountNameConflictError("duplicate")
        response = service_account_name_conflict_handler(request, exc)
        body = json.loads(bytes(response.body))
        assert "duplicate" in body["detail"]
        assert body["code"] == "SERVICE_ACCOUNT_NAME_CONFLICT"


class TestServiceAccountErrorHandler:
    """Tests for generic error handler."""

    def test_returns_400(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts"
        exc = ServiceAccountError("something went wrong")
        response = service_account_error_handler(request, exc)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestSACredentialNotFoundHandler:
    """Tests for credential 404 error handler."""

    def test_returns_404(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts/123/credentials/456"
        exc = ServiceAccountCredentialNotFoundError("Credential 456 not found")
        response = sa_credential_not_found_handler(request, exc)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_response_contains_detail(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts/123/credentials/456"
        exc = ServiceAccountCredentialNotFoundError("Credential 456 not found")
        response = sa_credential_not_found_handler(request, exc)
        body = json.loads(bytes(response.body))
        assert body["detail"] == "Credential 456 not found"
        assert body["code"] == "SERVICE_ACCOUNT_CREDENTIAL_NOT_FOUND"


class TestSACredentialLimitHandler:
    """Tests for credential limit 409 error handler."""

    def test_returns_409(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts/123/credentials"
        exc = ServiceAccountCredentialLimitError("sa-id-123", 10)
        response = sa_credential_limit_handler(request, exc)
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_response_contains_detail(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts/123/credentials"
        exc = ServiceAccountCredentialLimitError("sa-id-123", 10)
        response = sa_credential_limit_handler(request, exc)
        body = json.loads(bytes(response.body))
        assert "maximum" in body["detail"]
        assert body["code"] == "SERVICE_ACCOUNT_CREDENTIAL_LIMIT"


class TestSACredentialExpirationExceededHandler:
    """Tests for credential expiration exceeded 400 error handler."""

    def test_returns_400(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts/123/credentials"
        exc = CredentialExpirationExceededError(30)
        response = sa_credential_expiration_exceeded_handler(request, exc)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_response_contains_detail(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts/123/credentials"
        exc = CredentialExpirationExceededError(30)
        response = sa_credential_expiration_exceeded_handler(request, exc)
        body = json.loads(bytes(response.body))
        assert "30 days" in body["detail"]
        assert body["code"] == "CREDENTIAL_EXPIRATION_EXCEEDED"


class TestSACredentialExpirationInPastHandler:
    """Tests for credential expiration in past 400 error handler."""

    def test_returns_400(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts/123/credentials"
        exc = CredentialExpirationInPastError("expires_at must be in the future")
        response = sa_credential_expiration_in_past_handler(request, exc)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_response_contains_detail(self) -> None:
        request = MagicMock()
        request.url = "http://test/api/v1/service_accounts/123/credentials"
        exc = CredentialExpirationInPastError("expires_at must be in the future")
        response = sa_credential_expiration_in_past_handler(request, exc)
        body = json.loads(bytes(response.body))
        assert "future" in body["detail"]
        assert body["code"] == "CREDENTIAL_EXPIRATION_IN_PAST"
