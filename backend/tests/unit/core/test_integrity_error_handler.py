"""Unit tests for integrity_error_handler."""

import json
from unittest.mock import Mock

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from syntara.core.error_handlers import PROBLEM_TYPES, integrity_error_handler


class MockIntegrityError(IntegrityError):
    """Mock IntegrityError that allows setting custom string representation."""

    def __init__(self, error_message: str) -> None:
        """Initialize with custom error message."""
        super().__init__("", "", Exception("test"))  # Required args for IntegrityError
        self._error_message = error_message

    def __str__(self) -> str:
        """Return custom error message."""
        return self._error_message


class TestIntegrityErrorHandler:
    """Test suite for integrity_error_handler."""

    def test_handles_integrity_error_with_name_conflict(self) -> None:
        """Test handling of IntegrityError that looks like a name conflict."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/providers"

        # Create a mock IntegrityError that looks like a name conflict
        exc = MockIntegrityError("UNIQUE constraint failed: providers.name")

        response = integrity_error_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 409  # Name conflict
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["name_conflict"]
        assert data["title"] == "Name Conflict"
        assert data["detail"] == "A resource with this name already exists"
        assert data["code"] == "INTEGRITY_NAME_CONFLICT"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/providers"

    def test_handles_integrity_error_non_name_conflict(self) -> None:
        """Test handling of IntegrityError that is not a name conflict."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        # Create a mock IntegrityError that is not a name conflict
        exc = MockIntegrityError("FOREIGN KEY constraint failed")

        response = integrity_error_handler(request, exc)

        assert response.status_code == 400
        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["integrity_constraint"]
        assert data["title"] == "Integrity Constraint Violation"
        assert data["detail"] == "A database constraint was violated - please check your input data"
        assert data["code"] == "INTEGRITY_CONSTRAINT_VIOLATION"
        assert data["retryable"] is False

    @pytest.mark.parametrize(
        ("error_message", "expected_is_name_conflict"),
        [
            ("UNIQUE constraint failed: providers.name", True),
            ("unique constraint failed: table.name", True),
            ("UNIQUE CONSTRAINT FAILED: NAME", True),  # Case insensitive
            ("Foreign key constraint failed", False),
            ("Check constraint violated", False),
            ("UNIQUE constraint failed: providers.id", False),  # UNIQUE but not name
            ("Some other error with name in it", False),  # name but not unique
            ("unique email constraint failed", False),  # unique but not name field
        ],
    )
    def test_name_conflict_detection(self, error_message: str, *, expected_is_name_conflict: bool) -> None:
        """Test detection of name conflict from error message."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = MockIntegrityError(error_message)

        response = integrity_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        if expected_is_name_conflict:
            assert response.status_code == 409
            assert data["code"] == "INTEGRITY_NAME_CONFLICT"
        else:
            assert response.status_code == 400
            assert data["code"] == "INTEGRITY_CONSTRAINT_VIOLATION"

    def test_logs_full_error_but_does_not_expose_details(self) -> None:
        """Test that full error is logged but not exposed to user."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        sensitive_error = "UNIQUE constraint failed: providers.name (secret_value='sensitive_data')"
        exc = MockIntegrityError(sensitive_error)

        response = integrity_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        # Should not contain sensitive information from the database error
        assert "secret_value" not in data["detail"]
        assert "sensitive_data" not in data["detail"]
        # Should contain generic message
        assert data["detail"] == "A resource with this name already exists"

    def test_not_retryable(self) -> None:
        """Test that integrity errors are not retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = MockIntegrityError("Some constraint violation")

        response = integrity_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False

    def test_preserves_request_url(self) -> None:
        """Test that request URL is preserved in instance field."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/providers/create"

        exc = MockIntegrityError("Constraint violation")

        response = integrity_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["instance"] == "https://api.example.com/providers/create"

    def test_edge_case_empty_error_message(self) -> None:
        """Test handling of IntegrityError with empty error message."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        exc = MockIntegrityError("")

        response = integrity_error_handler(request, exc)

        # Should not detect as name conflict due to empty message
        assert response.status_code == 400
        data = json.loads(bytes(response.body).decode())
        assert data["code"] == "INTEGRITY_CONSTRAINT_VIOLATION"

    def test_case_insensitive_detection(self) -> None:
        """Test that name conflict detection is case insensitive."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/test"

        # Mix of cases
        exc = MockIntegrityError("UniQue constraint failed: table.NAME")

        response = integrity_error_handler(request, exc)

        # Should detect as name conflict despite mixed case
        assert response.status_code == 409
        data = json.loads(bytes(response.body).decode())
        assert data["code"] == "INTEGRITY_NAME_CONFLICT"
