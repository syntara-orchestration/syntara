"""Unit tests for generic error handlers."""

import json
from unittest.mock import Mock

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.agent_orchestrator.error_handlers import llm_configuration_error_handler
from syntara.agent_orchestrator.exceptions import LLMConfigurationError
from syntara.core.error_handlers import PROBLEM_TYPES


class TestLlmConfigurationErrorHandler:
    """Test suite for llm_configuration_error_handler."""

    def test_handles_llm_configuration_error(self) -> None:
        """Test handling of LLM configuration errors."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/llm/generate"

        exc = LLMConfigurationError("LLM configuration error")
        response = llm_configuration_error_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 503

        data = json.loads(bytes(response.body).decode())
        assert data["type"] == PROBLEM_TYPES["service_unavailable"]
        assert data["title"] == "LLM Configuration Error"
        assert data["detail"] == "Language model service is not properly configured"
        assert data["code"] == "LLM_CONFIGURATION_ERROR"
        assert data["retryable"] is False

    def test_not_retryable(self) -> None:
        """Test that LLM configuration errors are not retryable."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/llm/test"

        exc = LLMConfigurationError("Config error")
        response = llm_configuration_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        assert data["retryable"] is False

    def test_logs_error(self) -> None:
        """Test that the handler logs an error."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/llm/test"

        exc = LLMConfigurationError("LLM config issue")
        response = llm_configuration_error_handler(request, exc)

        # The function should complete without error (logging is internal)
        assert response.status_code == 503

    def test_does_not_expose_configuration_details(self) -> None:
        """Test that configuration details are not exposed to users."""
        request = Mock(spec=Request)
        request.url = "https://api.example.com/llm/test"

        exc = LLMConfigurationError("API key invalid: sk-1234567890abcdef")
        response = llm_configuration_error_handler(request, exc)

        data = json.loads(bytes(response.body).decode())
        # Should not contain API key or other sensitive config
        assert "sk-1234567890abcdef" not in data["detail"]
        # Should use generic message
        assert data["detail"] == "Language model service is not properly configured"
