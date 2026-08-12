"""Unit tests for validation error handlers."""

import json
from unittest.mock import Mock, patch

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError as PydanticValidationError

from syntara.core.error_handlers import PROBLEM_TYPES, validation_error_handler


class TestValidationErrorHandler:
    """Test suite for validation_error_handler."""

    def test_handles_pydantic_validation_error(self) -> None:
        """Test handling of Pydantic ValidationError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/validate"

        # Create a mock Pydantic ValidationError
        exc = Mock(spec=PydanticValidationError)
        exc.errors.return_value = [
            {"loc": ("field1",), "msg": "Field is required"},
            {"loc": ("field2", "nested"), "msg": "Invalid value"},
            {"loc": (), "msg": "Root level error"},
        ]

        with patch("syntara.core.error_handlers.logger.error"):
            response = validation_error_handler(request, exc)

        assert response.status_code == 422
        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["validation_error"]
        assert data["title"] == "Request Validation Error"
        assert data["code"] == "REQUEST_VALIDATION_ERROR"
        assert data["retryable"] is False

        # Check that error details are formatted nicely
        detail = data["detail"]
        assert "field1: Field is required" in detail
        assert "field2 -> nested: Invalid value" in detail
        assert "root: Root level error" in detail

    def test_handles_request_validation_error(self) -> None:
        """Test handling of FastAPI RequestValidationError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/validate"

        # Create a mock RequestValidationError
        exc = Mock(spec=RequestValidationError)
        exc.errors.return_value = [
            {"loc": ("body", "name"), "msg": "String too short"},
            {"loc": ("query", "page"), "msg": "Not a valid integer"},
        ]

        with patch("syntara.core.error_handlers.logger.error"):
            response = validation_error_handler(request, exc)

        assert response.status_code == 422
        data = json.loads(bytes(response.body).decode())
        assert "name: String too short" in data["detail"]
        assert "query -> page: Not a valid integer" in data["detail"]

    def test_empty_error_list(self) -> None:
        """Test handling of ValidationError with empty error list."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/validate"

        exc = Mock(spec=PydanticValidationError)
        exc.errors.return_value = []

        with patch("syntara.core.error_handlers.logger.error"):
            response = validation_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert "Validation failed:" in data["detail"]

    def test_error_with_empty_location(self) -> None:
        """Test handling of validation error with empty location."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/validate"

        exc = Mock(spec=PydanticValidationError)
        exc.errors.return_value = [{"loc": (), "msg": "Root validation error"}]

        with patch("syntara.core.error_handlers.logger.error"):
            response = validation_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert "root: Root validation error" in data["detail"]

    def test_complex_nested_location(self) -> None:
        """Test handling of deeply nested field locations."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/validate"

        exc = Mock(spec=PydanticValidationError)
        exc.errors.return_value = [{"loc": ("body", "user", "profile", "settings", "theme"), "msg": "Invalid theme"}]

        with patch("syntara.core.error_handlers.logger.error"):
            response = validation_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        # "body" is stripped from the path as noise
        assert "user -> profile -> settings -> theme: Invalid theme" in data["detail"]

    def test_many_errors_truncated_not_meta_error(self) -> None:
        """Test that many validation errors produce a truncated detail, not a meta-validation error.

        Regression test for AAP-79930: when concatenated error messages exceeded 2000 chars,
        ErrorData construction failed and users saw "detail: String should have at most 2000
        characters" instead of the actual validation errors.
        """
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows"

        exc = Mock(spec=PydanticValidationError)
        exc.errors.return_value = [
            {"loc": (f"nodes_{i}", "parameters", "code"), "msg": f"Invalid parameter value for node {i}"}
            for i in range(100)
        ]

        with patch("syntara.core.error_handlers.logger.error"):
            response = validation_error_handler(request, exc)

        assert response.status_code == 422
        data = json.loads(bytes(response.body).decode())
        assert len(data["detail"]) <= 2000
        assert data["detail"].startswith("Validation failed: ")
        assert data["detail"].endswith("...")
        assert "String should have at most 2000 characters" not in data["detail"]

    @pytest.mark.parametrize(
        ("error_data", "expected_field"),
        [
            ([{"loc": ("name",), "msg": "Required"}], "name: Required"),
            ([{"loc": ("a", "b", "c"), "msg": "Invalid"}], "a -> b -> c: Invalid"),
            ([{"loc": (), "msg": "Root error"}], "root: Root error"),
            ([{"loc": (0, "field"), "msg": "List item error"}], "0 -> field: List item error"),
        ],
    )
    def test_various_location_formats(self, error_data: list[dict[str, str]], expected_field: str) -> None:
        """Test handling of various location formats."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/validate"

        exc = Mock(spec=PydanticValidationError)
        exc.errors.return_value = error_data

        with patch("syntara.core.error_handlers.logger.error"):
            response = validation_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert expected_field in data["detail"]
