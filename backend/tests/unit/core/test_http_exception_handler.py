"""Unit tests for http_exception_handler."""

import json
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, http_exception_handler


class TestHttpExceptionHandler:
    """Test suite for http_exception_handler."""

    def test_handles_http_exception(self) -> None:
        """Test handling of standard HTTPException."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

        response = http_exception_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_not_found"]
        assert data["title"] == "Not Found"
        assert data["detail"] == "Resource not found"
        assert data["code"] == "HTTP_404"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/test"

    def test_handles_http_exception_with_non_string_detail(self) -> None:
        """Test handling HTTPException with non-string detail."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "Invalid data", "field": "name"})

        response = http_exception_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert "Invalid data" in data["detail"] or "error" in data["detail"]
        assert data["code"] == "HTTP_400"

    @pytest.mark.parametrize(
        ("status_code", "expected_problem_type", "expected_title"),
        [
            (400, "validation_error", "Bad Request"),
            (401, "unauthorized", "Unauthorized"),
            (403, "forbidden", "Forbidden"),
            (404, "resource_not_found", "Not Found"),
            (405, "method_not_allowed", "Method Not Allowed"),
            (409, "name_conflict", "Conflict"),
            (422, "validation_error", "Unprocessable Entity"),
            (500, "internal_error", "Internal Server Error"),
            (503, "service_unavailable", "Service Unavailable"),
        ],
    )
    def test_status_code_mapping(self, status_code: int, expected_problem_type: str, expected_title: str) -> None:
        """Test correct mapping of status codes to problem types and titles."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = HTTPException(status_code=status_code, detail="Test error")
        response = http_exception_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES[expected_problem_type]
        assert data["title"] == expected_title
        assert data["code"] == f"HTTP_{status_code}"

    def test_unmapped_status_code_defaults_to_internal_error(self) -> None:
        """Test that unmapped status codes default to internal error."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = HTTPException(status_code=418, detail="I'm a teapot")  # Not in mapping
        response = http_exception_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["internal_error"]
        assert data["title"] == "Error"
        assert data["code"] == "HTTP_418"

    @pytest.mark.parametrize(
        ("status_code", "expected_retryable"),
        [
            (500, True),  # Internal Server Error - retryable
            (502, True),  # Bad Gateway - retryable
            (503, True),  # Service Unavailable - retryable
            (504, True),  # Gateway Timeout - retryable
            (429, True),  # Too Many Requests - retryable
            (400, False),  # Bad Request - not retryable
            (401, False),  # Unauthorized - not retryable
            (403, False),  # Forbidden - not retryable
            (404, False),  # Not Found - not retryable
            (405, False),  # Method Not Allowed - not retryable
            (409, False),  # Conflict - not retryable
            (422, False),  # Unprocessable Entity - not retryable
            (501, False),  # Not Implemented - not retryable (5xx but not in retryable list)
        ],
    )
    def test_retryable_for_server_errors(self, status_code: int, *, expected_retryable: bool) -> None:
        """Test retryable status determination for different HTTPException status codes."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = HTTPException(status_code=status_code, detail="Test error")
        response = http_exception_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is expected_retryable

    def test_not_retryable_for_client_errors(self) -> None:
        """Test that client errors (4xx) are not marked as retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = HTTPException(status_code=400, detail="Bad request")
        response = http_exception_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False

    def test_preserves_request_url_in_instance(self) -> None:
        """Test that request URL is preserved in instance field."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/users/123?page=1"

        exc = HTTPException(status_code=404, detail="User not found")
        response = http_exception_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["instance"] == "https://api.example.com/users/123?page=1"

    def test_none_detail_handling(self) -> None:
        """Test handling of HTTPException with None detail."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = HTTPException(status_code=404)  # detail defaults to None
        response = http_exception_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert isinstance(data["detail"], str)  # Should be converted to string
