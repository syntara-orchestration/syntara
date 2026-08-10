"""Unit tests for webhook trigger error handlers."""

import json
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.workflows.error_handlers import (
    payload_too_large_handler,
    trigger_validation_handler,
    webhook_auth_required_handler,
    webhook_sa_not_authorized_handler,
    webhook_trigger_not_found_handler,
    webhook_trigger_path_conflict_handler,
)
from syntara.workflows.exceptions import (
    PayloadTooLargeError,
    TriggerValidationError,
    WebhookAuthenticationRequiredError,
    WebhookServiceAccountNotAuthorizedError,
    WebhookTriggerNotFoundError,
    WebhookTriggerPathConflictError,
)


class TestWebhookTriggerNotFoundHandler:
    """Test suite for webhook_trigger_not_found_handler."""

    def test_returns_404_with_problem_json(self) -> None:
        """Test that handler returns 404 with RFC 9457 format."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/webhooks/my-hook"

        exc = WebhookTriggerNotFoundError("my-hook", "webhook_trigger")
        response = webhook_trigger_not_found_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_not_found"]
        assert data["title"] == "Webhook Trigger Not Found"
        assert data["detail"] == "No webhook trigger is configured for the requested path"
        assert data["code"] == "WEBHOOK_TRIGGER_NOT_FOUND"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/webhooks/my-hook"

    def test_does_not_expose_webhook_path_in_detail(self) -> None:
        """Test that the webhook path is not leaked into the detail message."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/webhooks/secret-path"

        exc = WebhookTriggerNotFoundError("secret-path", "webhook_trigger")
        response = webhook_trigger_not_found_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert "secret-path" not in data["detail"]

    def test_not_retryable(self) -> None:
        """Test that webhook trigger not found errors are not retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/webhooks/test"

        exc = WebhookTriggerNotFoundError("test", "webhook_trigger")
        response = webhook_trigger_not_found_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False


class TestWebhookTriggerPathConflictHandler:
    """Test suite for webhook_trigger_path_conflict_handler."""

    def test_returns_409_with_problem_json(self) -> None:
        """Test that handler returns 409 for path conflicts."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows"

        exc = WebhookTriggerPathConflictError("github-events")
        response = webhook_trigger_path_conflict_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 409
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["name_conflict"]
        assert data["title"] == "Webhook Path Conflict"
        assert data["detail"] == "The requested webhook path is already in use by another trigger"
        assert data["code"] == "WEBHOOK_TRIGGER_PATH_CONFLICT"
        assert data["retryable"] is False

    def test_does_not_expose_conflicting_path(self) -> None:
        """Test that the conflicting path is not leaked into the detail message."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows"

        exc = WebhookTriggerPathConflictError("my-secret-path")
        response = webhook_trigger_path_conflict_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert "my-secret-path" not in data["detail"]

    def test_not_retryable(self) -> None:
        """Test that path conflict errors are not retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows"

        exc = WebhookTriggerPathConflictError("test")
        response = webhook_trigger_path_conflict_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False


class TestTriggerValidationHandler:
    """Test suite for trigger_validation_handler."""

    def test_returns_422_with_problem_json(self) -> None:
        """Test that handler returns 422 for validation errors."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/webhooks/my-hook"

        exc = TriggerValidationError("'required_field' is a required property")
        response = trigger_validation_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 422
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["validation_error"]
        assert data["title"] == "Trigger Payload Validation Failed"
        assert data["code"] == "TRIGGER_VALIDATION_ERROR"
        assert data["retryable"] is False

    def test_includes_exception_message_in_detail(self) -> None:
        """Test that the validation error message is passed through to detail."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/webhooks/test"

        msg = "Webhook payload validation failed: 'name' is a required property"
        exc = TriggerValidationError(msg)
        response = trigger_validation_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["detail"] == msg

    def test_not_retryable(self) -> None:
        """Test that validation errors are not retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/webhooks/test"

        exc = TriggerValidationError("bad payload")
        response = trigger_validation_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False


class TestPayloadTooLargeHandler:
    """Test suite for payload_too_large_handler."""

    def test_returns_413_with_problem_details(self) -> None:
        request = Mock(spec=Request)
        request.url = "https://api.example.com/webhooks/test"

        exc = PayloadTooLargeError("Payload exceeds 1MB limit")
        response = payload_too_large_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 413
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["payload_too_large"]
        assert data["title"] == "Payload Too Large"
        assert data["code"] == "PAYLOAD_TOO_LARGE"
        assert data["detail"] == "Payload exceeds 1MB limit"
        assert data["retryable"] is False


class TestWebhookAuthRequiredHandler:
    """Test suite for webhook_auth_required_handler."""

    def test_returns_401_with_problem_json(self) -> None:
        """Test that handler returns 401 with RFC 9457 format."""
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/v1/webhooks/my-hook"
        request.url.__str__ = Mock(return_value="https://api.example.com/webhooks/my-hook")
        request.path_params = {"webhook_path": "my-hook"}

        exc = WebhookAuthenticationRequiredError()

        with patch("syntara.workflows.error_handlers.AuditEventDispatcher"):
            response = webhook_auth_required_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 401
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["unauthorized"]
        assert data["code"] == "WEBHOOK_AUTH_REQUIRED"
        assert data["retryable"] is False

    def test_dispatches_audit_failure_event(self) -> None:
        """Test that an audit failure event is dispatched."""
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/v1/webhooks/eda/my-eda-hook"
        request.url.__str__ = Mock(return_value="https://api.example.com/webhooks/eda/my-eda-hook")
        request.path_params = {"webhook_path": "my-eda-hook"}

        exc = WebhookAuthenticationRequiredError()

        with patch("syntara.workflows.error_handlers.AuditEventDispatcher") as mock_dispatcher:
            webhook_auth_required_handler(request, exc)

        mock_dispatcher.dispatch.assert_called_once()
        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.webhook_path == "my-eda-hook"
        assert event.trigger_type == "eda_trigger"
        assert event.failure_reason == "missing_or_invalid_token"


class TestWebhookSaNotAuthorizedHandler:
    """Test suite for webhook_sa_not_authorized_handler."""

    def test_returns_403_with_problem_json(self) -> None:
        """Test that handler returns 403 with RFC 9457 format."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/webhooks/my-hook"

        sa_id = uuid4()
        exc = WebhookServiceAccountNotAuthorizedError("my-hook", "webhook_trigger", service_account_id=sa_id)

        with patch("syntara.workflows.error_handlers.AuditEventDispatcher"):
            response = webhook_sa_not_authorized_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 403
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["forbidden"]
        assert data["code"] == "WEBHOOK_SA_NOT_AUTHORIZED"
        assert data["retryable"] is False

    def test_dispatches_audit_failure_event_with_sa_id(self) -> None:
        """Test that an audit failure event includes the service account ID."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/webhooks/my-hook"

        sa_id = uuid4()
        exc = WebhookServiceAccountNotAuthorizedError("my-hook", "webhook_trigger", service_account_id=sa_id)

        with patch("syntara.workflows.error_handlers.AuditEventDispatcher") as mock_dispatcher:
            webhook_sa_not_authorized_handler(request, exc)

        mock_dispatcher.dispatch.assert_called_once()
        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.webhook_path == "my-hook"
        assert event.trigger_type == "webhook_trigger"
        assert event.failure_reason == "sa_not_authorized"
        assert event.service_account_id == sa_id
