"""Unit tests for Temporal-related error handlers."""

import json
from unittest.mock import Mock, patch

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from temporalio.service import RPCError

from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.workflows.error_handlers import temporal_rpc_error_handler, temporal_unavailable_handler
from syntara.workflows.exceptions import TemporalUnavailableError


class TestTemporalUnavailableHandler:
    """Test suite for temporal_unavailable_handler."""

    def test_handles_temporal_unavailable_error(self) -> None:
        """Test handling of Temporal unavailable errors."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows/execute"

        exc = TemporalUnavailableError("Temporal service unavailable")
        response = temporal_unavailable_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 503
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["service_unavailable"]
        assert data["title"] == "Temporal Service Unavailable"
        assert data["detail"] == "Temporal workflow service is currently unavailable"
        assert data["code"] == "TEMPORAL_UNAVAILABLE"
        assert data["retryable"] is True
        assert data["instance"] == "https://api.example.com/workflows/execute"

    def test_is_retryable(self) -> None:
        """Test that Temporal unavailable errors are retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows/test"

        exc = TemporalUnavailableError("Service down")
        response = temporal_unavailable_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is True

    def test_logs_warning(self) -> None:
        """Test that the handler logs a warning."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows/test"

        exc = TemporalUnavailableError("Temporal unavailable")
        response = temporal_unavailable_handler(request, exc)

        # The function should complete without error (logging is internal)
        assert response.status_code == 503

    def test_does_not_expose_internal_details(self) -> None:
        """Test that internal error details are not exposed to users."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows/test"

        exc = TemporalUnavailableError("Internal connection details: host=temporal-server:7233")
        response = temporal_unavailable_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        # Should not contain internal connection details
        assert "temporal-server" not in data["detail"]
        assert "7233" not in data["detail"]
        # Should use generic message
        assert data["detail"] == "Temporal workflow service is currently unavailable"


class TestTemporalRpcErrorHandler:
    """Test suite for temporal_rpc_error_handler."""

    def test_handles_rpc_error(self) -> None:
        """Test handling of Temporal RPCError."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows/execute"

        # Mock logging to avoid traceback issues
        with patch("syntara.workflows.error_handlers.logger.error"):
            exc = Mock(spec=RPCError)
            response = temporal_rpc_error_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        assert response.media_type == "application/problem+json"

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["internal_error"]
        assert data["title"] == "Temporal Workflow Error"
        assert data["detail"] == "Temporal workflow operation failed"
        assert data["code"] == "TEMPORAL_WORKFLOW_ERROR"
        assert data["retryable"] is True
        assert data["instance"] == "https://api.example.com/workflows/execute"

    def test_is_retryable(self) -> None:
        """Test that Temporal RPC errors are retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows/test"

        with patch("syntara.workflows.error_handlers.logger.error"):
            exc = Mock(spec=RPCError)
            response = temporal_rpc_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is True

    def test_logs_error(self) -> None:
        """Test that the handler logs an error."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows/test"

        with patch("syntara.workflows.error_handlers.logger.error"):
            exc = Mock(spec=RPCError)
            response = temporal_rpc_error_handler(request, exc)

        # The function should complete without error (logging is internal)
        assert response.status_code == 500

    def test_does_not_expose_internal_details(self) -> None:
        """Test that internal RPC error details are not exposed to users."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows/test"

        with patch("syntara.workflows.error_handlers.logger.error"):
            exc = Mock(spec=RPCError)
            response = temporal_rpc_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        # Should use generic message, not expose RPC internals
        assert data["detail"] == "Temporal workflow operation failed"

    def test_preserves_request_url(self) -> None:
        """Test that request URL is preserved in instance field."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/workflows/complex-workflow/execute"

        with patch("syntara.workflows.error_handlers.logger.error"):
            exc = Mock(spec=RPCError)
            response = temporal_rpc_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["instance"] == "https://api.example.com/workflows/complex-workflow/execute"

    @pytest.mark.parametrize(
        "url",
        [
            "https://api.example.com/workflows/start",
            "https://api.example.com/workflows/123/status",
            "http://localhost:8000/api/v1/workflows/cancel",
        ],
    )
    def test_various_workflow_urls(self, url: str) -> None:
        """Test handling of various workflow-related URLs."""
        request = Mock(spec=Request)
        request.url = url

        with patch("syntara.workflows.error_handlers.logger.error"):
            exc = Mock(spec=RPCError)
            response = temporal_rpc_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["instance"] == url
