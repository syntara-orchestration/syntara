"""Unit tests for validation error handlers."""

import json
from unittest.mock import Mock

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.files.error_handlers import (
    file_error_handler,
    file_integrity_error_handler,
    file_not_found_error_handler,
    file_validation_error_handler,
)
from syntara.files.exceptions import FileContentNotFoundError, FileError, FileIntegrityError, FileValidationError


class TestFileValidationErrorHandler:
    """Test suite for file_validation_error_handler."""

    def test_handles_file_validation_error(self) -> None:
        """Test handling of FileValidationError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/files/upload"

        exc = FileValidationError("File format not supported")
        response = file_validation_error_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["validation_error"]
        assert data["title"] == "File Validation Error"
        assert data["detail"] == "File format not supported"
        assert data["code"] == "FILE_VALIDATION_ERROR"
        assert data["retryable"] is False
        assert data["instance"] == "https://api.example.com/files/upload"

    def test_not_retryable(self) -> None:
        """Test that file validation errors are not retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/files/test"

        exc = FileValidationError("Invalid file")
        response = file_validation_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False


class TestFileNotFoundErrorHandler:
    """Test suite for file_not_found_error_handler."""

    def test_returns_404(self) -> None:
        """Test handling of FileContentNotFoundError returns 404."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/files/abc/download"

        exc = FileContentNotFoundError("File not found: nexus-abc-report.pdf")
        response = file_not_found_error_handler(request, exc)

        assert response.status_code == 404
        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_not_found"]
        assert data["code"] == "FILE_NOT_FOUND"
        assert data["retryable"] is False


class TestFileIntegrityErrorHandler:
    """Test suite for file_integrity_error_handler."""

    def test_returns_500(self) -> None:
        """Test handling of FileIntegrityError returns 500."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/files/abc/download"

        exc = FileIntegrityError("Hash mismatch: expected abc123, got def456")
        response = file_integrity_error_handler(request, exc)

        assert response.status_code == 500
        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["internal_error"]
        assert data["code"] == "FILE_INTEGRITY_ERROR"
        assert data["retryable"] is False
        assert data["detail"] == "File integrity verification failed"


class TestFileErrorHandler:
    """Test suite for file_error_handler (catch-all)."""

    def test_returns_502_retryable(self) -> None:
        """Test handling of FileError returns 502 with retryable=True."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/files/abc/download"

        exc = FileError("S3 storage unavailable")
        response = file_error_handler(request, exc)

        assert response.status_code == 502
        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["service_unavailable"]
        assert data["code"] == "FILE_STORAGE_ERROR"
        assert data["retryable"] is True
