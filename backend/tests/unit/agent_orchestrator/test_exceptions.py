"""Unit tests for agent orchestrator exceptions."""

from uuid import uuid4

from syntara.agent_orchestrator.exceptions import (
    AgentConfigurationError,
    AgentOrchestratorError,
    AgentRateLimitError,
    AgentTimeoutError,
    ContextIntegrationError,
    EmptyLLMResponseError,
    LLMConfigurationError,
    OrchestrationError,
)
from syntara.core.exceptions import RetryableError


class TestLLMConfigurationError:
    """Tests for LLMConfigurationError exception."""

    def test_message_is_preserved(self) -> None:
        """Test that exception message is preserved."""
        message = "No LLM API key available. Attach an LLM Provider credential to the workflow's agentic node."
        error = LLMConfigurationError(message)
        assert str(error) == message


class TestAgentOrchestratorError:
    """Test base AgentOrchestratorError functionality."""

    def test_agent_orchestrator_error_initialization(self) -> None:
        """Test AgentOrchestratorError initialization with message and invocation_id."""
        message = "Test error message"
        invocation_id = str(uuid4())

        error = AgentOrchestratorError(message, invocation_id)

        assert str(error) == message
        assert error.message == message
        assert error.invocation_id == invocation_id

    def test_agent_orchestrator_error_initialization_without_invocation_id(self) -> None:
        """Test AgentOrchestratorError initialization without invocation_id."""
        message = "Test error without invocation ID"

        error = AgentOrchestratorError(message)

        assert str(error) == message
        assert error.message == message
        assert error.invocation_id is None


class TestEmptyLLMResponseError:
    """Tests for EmptyLLMResponseError exception."""

    def test_initialization_with_invocation_id(self) -> None:
        """Test EmptyLLMResponseError preserves invocation_id."""
        invocation_id = str(uuid4())
        error = EmptyLLMResponseError(invocation_id=invocation_id)

        assert str(error) == "LLM returned empty response with no tool calls"
        assert error.message == "LLM returned empty response with no tool calls"
        assert error.invocation_id == invocation_id

    def test_initialization_without_invocation_id(self) -> None:
        """Test EmptyLLMResponseError defaults invocation_id to None."""
        error = EmptyLLMResponseError()

        assert str(error) == "LLM returned empty response with no tool calls"
        assert error.invocation_id is None

    def test_inherits_from_both_base_classes(self) -> None:
        """Test EmptyLLMResponseError inherits from AgentOrchestratorError and RetryableError."""
        error = EmptyLLMResponseError(invocation_id="test-id")

        assert isinstance(error, AgentOrchestratorError)
        assert isinstance(error, RetryableError)


class TestExceptionInheritance:
    """Test that all exception types inherit from AgentOrchestratorError."""

    def test_configuration_error_inherits_agent_orchestrator_error(self) -> None:
        """Test AgentConfigurationError inherits from AgentOrchestratorError."""
        error = AgentConfigurationError("Config error")
        assert isinstance(error, AgentOrchestratorError)
        assert str(error) == "Config error"

    def test_rate_limit_error_inherits_agent_orchestrator_error(self) -> None:
        """Test AgentRateLimitError inherits from AgentOrchestratorError."""
        error = AgentRateLimitError("Rate limit exceeded")
        assert isinstance(error, AgentOrchestratorError)
        assert str(error) == "Rate limit exceeded"

    def test_timeout_error_inherits_agent_orchestrator_error(self) -> None:
        """Test AgentTimeoutError inherits from AgentOrchestratorError."""
        error = AgentTimeoutError("Request timeout")
        assert isinstance(error, AgentOrchestratorError)
        assert str(error) == "Request timeout"

    def test_context_integration_error_inherits_agent_orchestrator_error(self) -> None:
        """Test ContextIntegrationError inherits from AgentOrchestratorError."""
        error = ContextIntegrationError("Context integration failed")
        assert isinstance(error, AgentOrchestratorError)
        assert str(error) == "Context integration failed"

    def test_orchestration_error_inherits_agent_orchestrator_error(self) -> None:
        """Test OrchestrationError inherits from AgentOrchestratorError."""
        error = OrchestrationError("Orchestration failed")
        assert isinstance(error, AgentOrchestratorError)
        assert str(error) == "Orchestration failed"


class TestErrorChaining:
    """Test error chaining and cause tracking."""

    def test_errors_can_be_chained(self) -> None:
        """Test that errors can be properly chained."""
        original_error = ConnectionError("Network failed")

        agent_error = AgentOrchestratorError(f"Processing failed: {original_error}")

        assert "Network failed" in str(agent_error)
        assert isinstance(agent_error, Exception)

    def test_configuration_error_with_underlying_cause(self) -> None:
        """Test configuration error with underlying cause."""
        original_error = KeyError("API_KEY")

        config_error = AgentConfigurationError(f"Missing configuration: {original_error}")

        assert "API_KEY" in str(config_error)
        assert isinstance(config_error, AgentOrchestratorError)
