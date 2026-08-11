"""Unit tests for settings error handlers."""

import json
from unittest.mock import Mock, patch

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.settings.error_handlers import (
    optimistic_lock_error_handler,
    setting_not_found_handler,
    setting_type_error_handler,
    setting_validation_error_handler,
)
from syntara.settings.exceptions import (
    OptimisticLockError,
    SettingNotFoundError,
    SettingTypeError,
    SettingValidationError,
)


def _call_handler(
    *,
    key: str = "test.setting.key",
    detail: str = "value must be positive",
    url: str = "https://api.example.com/api/v1/settings/test.setting.key",
) -> JSONResponse:
    """Invoke setting_validation_error_handler with a mock request."""
    request = Mock(spec=Request)
    request.url = url
    exc = SettingValidationError(key=key, detail=detail)
    return setting_validation_error_handler(request, exc)


class TestSettingValidationErrorHandler:
    """Test suite for setting_validation_error_handler."""

    def test_returns_422_status(self) -> None:
        """Handler returns HTTP 422 Unprocessable Entity."""
        response = _call_handler()
        assert response.status_code == 422

    def test_returns_problem_json_media_type(self) -> None:
        """Response content-type is application/problem+json."""
        response = _call_handler()
        assert response.media_type == "application/problem+json"

    def test_response_body_has_rfc9457_structure(self) -> None:
        """Response body contains all RFC 9457 required fields."""
        response = _call_handler()
        data = json.loads(bytes(response.body).decode())

        assert isinstance(response, JSONResponse)
        assert data["type"] == PROBLEM_TYPES["validation_error"]
        assert data["title"] == "Setting Validation Error"
        assert data["detail"] == "value must be positive"
        assert data["code"] == "SETTING_VALIDATION_ERROR"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/api/v1/settings/test.setting.key"

    def test_detail_from_exception(self) -> None:
        """The detail field is taken from the exception's detail attribute."""
        response = _call_handler(detail="must be between 0 and 1")
        data = json.loads(bytes(response.body).decode())
        assert data["detail"] == "must be between 0 and 1"

    def test_uses_validation_error_problem_type(self) -> None:
        """Handler uses the validation_error problem type URI."""
        response = _call_handler()
        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["validation_error"]

    def test_not_retryable(self) -> None:
        """Validation errors are not retryable."""
        response = _call_handler()
        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False

    def test_preserves_request_url(self) -> None:
        """The instance field matches the request URL."""
        response = _call_handler(url="http://localhost:8000/api/v1/settings/ai.temperature")
        data = json.loads(bytes(response.body).decode())
        assert data["instance"] == "http://localhost:8000/api/v1/settings/ai.temperature"

    def test_logs_error_with_key_and_detail(self) -> None:
        """Handler logs the setting key and detail message."""
        with patch("syntara.settings.error_handlers.logger") as mock_logger:
            _call_handler(key="ai.model_name", detail="unknown model")
            mock_logger.warning.assert_called_once_with(
                "Setting validation error",
                key="ai.model_name",
                detail="unknown model",
            )


# ---------------------------------------------------------------------------
# SettingNotFoundError handler
# ---------------------------------------------------------------------------


class TestSettingNotFoundHandler:
    """Test suite for setting_not_found_handler."""

    def test_returns_404_status(self) -> None:
        """Handler returns HTTP 404 Not Found."""
        request = Mock(spec=Request)
        request.url = "http://test/api/v1/settings/missing.key"
        exc = SettingNotFoundError("missing.key")
        response = setting_not_found_handler(request, exc)
        assert response.status_code == 404

    def test_response_body_has_rfc9457_structure(self) -> None:
        """Response body contains all RFC 9457 required fields."""
        request = Mock(spec=Request)
        request.url = "http://test/api/v1/settings/missing.key"
        exc = SettingNotFoundError("missing.key")
        response = setting_not_found_handler(request, exc)
        data = json.loads(bytes(response.body).decode())

        assert data["type"] == PROBLEM_TYPES["resource_not_found"]
        assert data["title"] == "Setting Not Found"
        assert "missing.key" in data["detail"]
        assert data["code"] == "SETTING_NOT_FOUND"
        assert data["retryable"] is False


# ---------------------------------------------------------------------------
# OptimisticLockError handler
# ---------------------------------------------------------------------------


class TestOptimisticLockErrorHandler:
    """Test suite for optimistic_lock_error_handler."""

    def test_returns_409_status(self) -> None:
        """Handler returns HTTP 409 Conflict."""
        request = Mock(spec=Request)
        request.url = "http://test/api/v1/settings/test.key"
        exc = OptimisticLockError("test.key", current_version=5, submitted_version=3)
        response = optimistic_lock_error_handler(request, exc)
        assert response.status_code == 409

    def test_response_body_has_rfc9457_structure(self) -> None:
        """Response body contains all RFC 9457 required fields."""
        request = Mock(spec=Request)
        request.url = "http://test/api/v1/settings/test.key"
        exc = OptimisticLockError("test.key", current_version=5, submitted_version=3)
        response = optimistic_lock_error_handler(request, exc)
        data = json.loads(bytes(response.body).decode())

        assert data["type"] == PROBLEM_TYPES["resource_conflict"]
        assert data["title"] == "Setting Version Conflict"
        assert "current=5" in data["detail"]
        assert "submitted=3" in data["detail"]
        assert data["code"] == "SETTING_VERSION_CONFLICT"
        assert data["retryable"] is True


# ---------------------------------------------------------------------------
# SettingTypeError handler
# ---------------------------------------------------------------------------


class TestSettingTypeErrorHandler:
    """Test suite for setting_type_error_handler."""

    def test_returns_422_status(self) -> None:
        """Handler returns HTTP 422 Unprocessable Entity."""
        request = Mock(spec=Request)
        request.url = "http://test/api/v1/settings/test.key"
        exc = SettingTypeError("test.key", expected="int", actual="str")
        response = setting_type_error_handler(request, exc)
        assert response.status_code == 422

    def test_response_body_has_rfc9457_structure(self) -> None:
        """Response body contains all RFC 9457 required fields."""
        request = Mock(spec=Request)
        request.url = "http://test/api/v1/settings/test.key"
        exc = SettingTypeError("test.key", expected="int", actual="str")
        response = setting_type_error_handler(request, exc)
        data = json.loads(bytes(response.body).decode())

        assert data["type"] == PROBLEM_TYPES["validation_error"]
        assert data["title"] == "Setting Type Error"
        assert data["code"] == "SETTING_TYPE_ERROR"
        assert data["retryable"] is False
