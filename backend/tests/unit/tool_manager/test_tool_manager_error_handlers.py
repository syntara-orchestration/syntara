"""Unit tests for generic error handlers."""

import json
from unittest.mock import Mock

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.tool_manager.error_handlers import tool_manager_error_handler
from syntara.tool_manager.exceptions import ToolManagerError


class TestToolManagerErrorHandler:
    """Test suite for tool_manager_error_handler."""

    def test_handles_tool_manager_error(self) -> None:
        """Test handling of ToolManagerError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/tools/execute"

        exc = ToolManagerError("Tool execution failed")
        response = tool_manager_error_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["provider_error"]
        assert data["title"] == "Tool Manager Error"
        assert data["detail"] == "Tool execution failed"
        assert data["code"] == "TOOL_MANAGER_ERROR"
        assert data["retryable"] is False

    def test_not_retryable(self) -> None:
        """Test that tool manager errors are not retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/tools/test"

        exc = ToolManagerError("Tool error")
        response = tool_manager_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False
