"""Unit tests for BaseAgent abstract class and error handling utilities."""

from unittest.mock import patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.agents.base_agent import BaseAgent
from syntara.agent_orchestrator.exceptions import (
    AgentConfigurationError,
    AgentOrchestratorError,
    AgentRateLimitError,
    AgentTimeoutError,
)
from syntara.agent_orchestrator.models.agent_response import GenericAgentResponse
from syntara.agent_orchestrator.models.agent_state import AgentState


class ConcreteAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""

    async def _execute(self, state: AgentState) -> AgentState:
        """Test implementation."""
        response = GenericAgentResponse(content="test response")
        state["result"] = response.model_dump(by_alias=True)
        return state


class TestBaseAgentInitialization:
    """Test BaseAgent initialization."""

    def test_base_agent_initializes_logger(self) -> None:
        """Test that BaseAgent initializes logger with correct name."""
        agent = ConcreteAgent()

        assert agent.logger is not None


class TestBaseAgentErrorHandling:
    """Test BaseAgent error handling helper method."""

    def test_handle_execution_error_converts_timeout_error(self) -> None:
        """Test that TimeoutError is converted to AgentTimeoutError."""
        agent = ConcreteAgent()
        invocation_id = uuid4()
        original_error = TimeoutError("Connection timed out")

        with pytest.raises(AgentTimeoutError) as exc_info:
            agent._handle_execution_error(original_error, invocation_id)

        assert exc_info.value.invocation_id == str(invocation_id)
        assert exc_info.value.__cause__ == original_error

    def test_handle_execution_error_converts_key_error(self) -> None:
        """Test that KeyError is converted to AgentConfigurationError."""
        agent = ConcreteAgent()
        invocation_id = uuid4()
        original_error = KeyError("API_KEY")

        with pytest.raises(AgentConfigurationError) as exc_info:
            agent._handle_execution_error(original_error, invocation_id)

        assert exc_info.value.invocation_id == str(invocation_id)
        assert "API_KEY" in str(exc_info.value)
        assert exc_info.value.__cause__ == original_error

    def test_handle_execution_error_converts_value_error(self) -> None:
        """Test that ValueError is converted to AgentConfigurationError."""
        agent = ConcreteAgent()
        invocation_id = uuid4()
        original_error = ValueError("Invalid configuration")

        with pytest.raises(AgentConfigurationError) as exc_info:
            agent._handle_execution_error(original_error, invocation_id)

        assert exc_info.value.invocation_id == str(invocation_id)
        assert "Invalid configuration" in str(exc_info.value)
        assert exc_info.value.__cause__ == original_error

    def test_handle_execution_error_detects_invalid_key_in_message(self) -> None:
        """Test errors with 'invalid key' become AgentConfigurationError."""
        agent = ConcreteAgent()
        invocation_id = uuid4()
        original_error = RuntimeError("Invalid API key provided")

        with pytest.raises(AgentConfigurationError) as exc_info:
            agent._handle_execution_error(original_error, invocation_id)

        assert exc_info.value.invocation_id == str(invocation_id)
        assert "Invalid API key" in str(exc_info.value)
        assert exc_info.value.__cause__ == original_error

    def test_handle_execution_error_detects_rate_limit_in_message(self) -> None:
        """Test that errors with 'rate limit' in message become AgentRateLimitError."""
        agent = ConcreteAgent()
        invocation_id = uuid4()
        original_error = RuntimeError("Rate limit exceeded for API")

        with pytest.raises(AgentRateLimitError) as exc_info:
            agent._handle_execution_error(original_error, invocation_id)

        assert exc_info.value.invocation_id == str(invocation_id)
        assert "Rate limit exceeded" in str(exc_info.value)
        assert exc_info.value.__cause__ == original_error

    def test_handle_execution_error_converts_general_errors(self) -> None:
        """Test that general errors are converted to AgentOrchestratorError."""
        agent = ConcreteAgent()
        invocation_id = uuid4()
        original_error = ConnectionError("Network failure")

        with pytest.raises(AgentOrchestratorError) as exc_info:
            agent._handle_execution_error(original_error, invocation_id)

        assert exc_info.value.invocation_id == str(invocation_id)
        assert "Network failure" in str(exc_info.value)
        assert exc_info.value.__cause__ == original_error


class TestBaseAgentLogging:
    """Test BaseAgent logging helper methods."""

    def test_log_execution_start_logs_with_correct_format(self) -> None:
        """Test that execution start is logged with invocation and session IDs."""
        agent = ConcreteAgent()
        invocation_id = uuid4()
        session_id = "test-session-123"

        with patch.object(agent.logger, "info") as mock_info:
            agent._log_execution_start(invocation_id, session_id)

            mock_info.assert_called_once()
            call_args = mock_info.call_args[0]
            call_kwargs = mock_info.call_args[1]
            # First arg is the message string
            assert "executing as node" in call_args[0]
            # Check kwargs for the values
            assert call_kwargs.get("agent_class") == "ConcreteAgent"
            assert call_kwargs.get("invocation_id") == invocation_id
            assert call_kwargs.get("session_id") == session_id

    def test_log_execution_success_logs_with_correct_format(self) -> None:
        """Test that execution success is logged with invocation ID."""
        agent = ConcreteAgent()
        invocation_id = uuid4()

        with patch.object(agent.logger, "info") as mock_info:
            agent._log_execution_success(invocation_id)

            mock_info.assert_called_once()
            call_args = mock_info.call_args[0]
            call_kwargs = mock_info.call_args[1]
            # First arg is the message string
            assert "completed successfully" in call_args[0]
            # Check kwargs for the values
            assert call_kwargs.get("agent_class") == "ConcreteAgent"
            assert call_kwargs.get("invocation_id") == invocation_id
