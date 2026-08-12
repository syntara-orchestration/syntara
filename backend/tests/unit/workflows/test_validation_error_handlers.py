"""Unit tests for validation error handlers."""

import json
from unittest.mock import Mock

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.workflows.error_handlers import validation_error_handler
from syntara.workflows.exceptions import WorkflowValidationError


class TestValidationErrorHandler:
    """Test suite for validation_error_handler."""

    def test_handles_validation_error(self) -> None:
        """Test handling of core validation errors."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/validate"

        exc = WorkflowValidationError("Core validation error")
        response = validation_error_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 422

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["validation_error"]
        assert data["title"] == "Validation Error"
        assert data["detail"] == "Core validation error"
        assert data["code"] == "VALIDATION_ERROR"
        assert data["retryable"] is False

    def test_empty_message_uses_default_detail(self) -> None:
        """Test that an empty message falls back to the default detail string."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/validate"

        exc = WorkflowValidationError("")
        response = validation_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["detail"] == "The provided data failed validation requirements"
