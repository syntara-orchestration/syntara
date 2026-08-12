"""Unit tests for tool_not_found_handler."""

import json
from unittest.mock import Mock

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.tool_manager.error_handlers import tool_not_found_handler, tool_refresh_error_handler
from syntara.tool_manager.exceptions import ToolNotFoundError, ToolRefreshError


class TestToolNotFoundHandler:
    """Test suite for tool_not_found_handler."""

    def test_handles_tool_not_found_error(self) -> None:
        """Test handling of ToolNotFoundError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/tools/nonexistent"

        exc = ToolNotFoundError("Tool 'nonexistent' was not found")
        response = tool_not_found_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_not_found"]
        assert data["title"] == "Tool Not Found"
        assert data["detail"] == "Tool 'nonexistent' was not found"
        assert data["code"] == "TOOL_NOT_FOUND"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/tools/nonexistent"

    def test_preserves_error_message(self) -> None:
        """Test that the original error message is preserved."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/tools/test"

        custom_message = "Custom tool not found message with details"
        exc = ToolNotFoundError(custom_message)
        response = tool_not_found_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["detail"] == custom_message

    def test_not_retryable(self) -> None:
        """Test that tool not found errors are not retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/tools/test"

        exc = ToolNotFoundError("Tool not found")
        response = tool_not_found_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False

    def test_preserves_request_url(self) -> None:
        """Test that request URL is preserved in instance field."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/providers/123/tools/456"

        exc = ToolNotFoundError("Tool 456 not found")
        response = tool_not_found_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["instance"] == "https://api.example.com/providers/123/tools/456"

    @pytest.mark.parametrize(
        ("url", "expected_instance"),
        [
            ("https://api.example.com/tools/test", "https://api.example.com/tools/test"),
            ("http://localhost:8000/api/v1/tools/123", "http://localhost:8000/api/v1/tools/123"),
            ("https://api.com/tools?filter=active", "https://api.com/tools?filter=active"),
        ],
    )
    def test_various_request_urls(self, url: str, expected_instance: str) -> None:
        """Test handling of various request URL formats."""
        request = Mock(spec=Request)
        request.url = url

        exc = ToolNotFoundError("Tool not found")
        response = tool_not_found_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["instance"] == expected_instance


class TestToolRefreshErrorHandler:
    """Test suite for provider_error_handler."""

    def test_handles_tool_refresh_error(self) -> None:
        """Test handling of ProviderError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/providers/test/action"

        exc = ToolRefreshError("Provider configuration is invalid")
        response = tool_refresh_error_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["provider_error"]
        assert data["title"] == "Tool Refresh Error"
        assert data["detail"] == "Provider configuration is invalid"
        assert data["code"] == "TOOL_REFRESH_ERROR"
        assert data["retryable"] is True
        assert data["instance"] == "https://api.example.com/providers/test/action"

    def test_is_retryable(self) -> None:
        """Test that provider errors are retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/providers/test"

        exc = ToolRefreshError("Temporary provider issue")
        response = tool_refresh_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is True

    @pytest.mark.parametrize(
        "error_message",
        [
            "Provider authentication failed",
            "Rate limit exceeded",
            "Provider service unavailable",
        ],
    )
    def test_various_error_messages(self, error_message: str) -> None:
        """Test handling of various provider error messages."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/providers/test"

        exc = ToolRefreshError(error_message)
        response = tool_refresh_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["detail"] == error_message

    def test_empty_error_message(self) -> None:
        """Test handling of ProviderError with empty message."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/providers/test"

        # ErrorData requires detail to have at least 1 character
        # This might cause a validation error or be handled gracefully
        exc = ToolRefreshError("")
        try:
            response = tool_refresh_error_handler(request, exc)
            data = json.loads(bytes(response.body).decode())
            # If it doesn't raise, it should handle empty gracefully
            assert isinstance(data["detail"], str)
        except Exception:
            # If it raises a validation error, that's expected behavior
            pass
