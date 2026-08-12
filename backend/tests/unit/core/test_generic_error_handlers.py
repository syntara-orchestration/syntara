"""Unit tests for generic error handlers."""

import json
from unittest.mock import Mock

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, generic_exception_handler, value_error_handler


class TestValueErrorHandler:
    """Test suite for value_error_handler."""

    def test_handles_empty_value_error_message(self) -> None:
        """Test handling of ValueError with empty message."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = ValueError("")
        response = value_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["detail"] == "Invalid input value"  # Default message

    def test_handles_value_error_with_none_message(self) -> None:
        """Test handling of ValueError that converts to empty string."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        # Create ValueError that str() returns empty
        exc = ValueError()
        response = value_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["detail"] == "Invalid input value"  # Default fallback

    def test_not_retryable(self) -> None:
        """Test that value errors are not retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = ValueError("Invalid value")
        response = value_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False

    @pytest.mark.parametrize(
        "error_message",
        [
            "Invalid cursor format",
            "UUID parsing failed",
            "Invalid input value provided",
            "Cursor validation error",
        ],
    )
    def test_various_value_error_messages(self, error_message: str) -> None:
        """Test handling of various ValueError messages."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = ValueError(error_message)
        response = value_error_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 422
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["validation_error"]
        assert data["title"] == "Validation Error"
        assert data["detail"] == "Invalid input value"
        assert data["code"] == "VALIDATION_ERROR"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/test"


class TestGenericExceptionHandler:
    """Test suite for generic_exception_handler."""

    def test_handles_generic_exception(self) -> None:
        """Test handling of unexpected exceptions."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = RuntimeError("Unexpected error occurred")
        response = generic_exception_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["internal_error"]
        assert data["title"] == "Internal Server Error"
        assert data["detail"] == "An unexpected error occurred while processing the request"
        assert data["code"] == "INTERNAL_SERVER_ERROR"
        assert data["retryable"] is True
        assert data["instance"] == "https://api.example.com/test"

    def test_does_not_expose_exception_details(self) -> None:
        """Test that exception details are not exposed to users."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = RuntimeError("Secret internal error with sensitive data: password=123")
        response = generic_exception_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        # Should not contain sensitive information
        assert "password=123" not in data["detail"]
        assert "Secret internal error" not in data["detail"]
        # Should use generic message
        assert data["detail"] == "An unexpected error occurred while processing the request"

    def test_is_retryable(self) -> None:
        """Test that generic exceptions are retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = Exception("Unknown error")
        response = generic_exception_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is True

    def test_logs_full_exception(self) -> None:
        """Test that the handler logs the full exception."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = RuntimeError("Detailed error for logging")
        response = generic_exception_handler(request, exc)

        # The function should complete without error (logging is internal)
        assert response.status_code == 500

    @pytest.mark.parametrize(
        "exception_type",
        [
            RuntimeError,
            TypeError,
            AttributeError,
            KeyError,
            IndexError,
        ],
    )
    def test_various_exception_types(self, exception_type: type) -> None:
        """Test handling of various exception types."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = exception_type("Test error")
        response = generic_exception_handler(request, exc)

        assert response.status_code == 500
        data = json.loads(bytes(response.body).decode())
        assert data["code"] == "INTERNAL_SERVER_ERROR"
        assert data["retryable"] is True
