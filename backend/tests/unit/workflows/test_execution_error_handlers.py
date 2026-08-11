"""Unit tests for execution-related error handlers."""

import json
from unittest.mock import Mock
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.workflows.error_handlers import (
    execution_not_retryable_handler,
    execution_terminal_state_handler,
)
from syntara.workflows.exceptions import (
    ExecutionInTerminalStateError,
    ExecutionNotRetryableError,
)


class TestExecutionNotRetryableHandler:
    """Test suite for execution_not_retryable_handler."""

    def test_returns_409_with_problem_json(self) -> None:
        """Test that handler returns 409 Conflict with RFC 9457 format."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/executions/123/retry"
        execution_id = uuid4()

        exc = ExecutionNotRetryableError(execution_id, "execution is in running state (must be terminal)")
        response = execution_not_retryable_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 409
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["resource_conflict"]
        assert data["title"] == "Execution Not Retryable"
        assert data["code"] == "EXECUTION_NOT_RETRYABLE"
        assert data["retryable"] is False
        assert str(execution_id) in data["detail"]

    def test_includes_reason_in_detail(self) -> None:
        """Test that the reason is included in the detail message."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/executions/123/retry"
        execution_id = uuid4()

        exc = ExecutionNotRetryableError(execution_id, "test executions cannot be retried")
        response = execution_not_retryable_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert "test executions cannot be retried" in data["detail"]


class TestExecutionTerminalStateHandler:
    """Test suite for execution_terminal_state_handler."""

    def test_returns_400_with_problem_json(self) -> None:
        """Test that handler returns 400 Bad Request with RFC 9457 format."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/executions/123/cancel"
        execution_id = uuid4()

        exc = ExecutionInTerminalStateError(execution_id, "completed", "cancel")
        response = execution_terminal_state_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["title"] == "Execution In Terminal State"
        assert data["code"] == "EXECUTION_TERMINAL_STATE"
        assert "cancel" in data["detail"]
        assert "completed" in data["detail"]
