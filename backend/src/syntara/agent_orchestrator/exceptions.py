"""Custom exceptions for agent orchestration system."""

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import RetryableError, SyntaraError


class AgentOrchestratorError(SyntaraError):
    """Base exception for all agent orchestration errors."""

    def __init__(self, message: str, invocation_id: str | None = None) -> None:
        """Initialize AgentOrchestratorError.

        Args:
            message: Error message
            invocation_id: Optional invocation ID for context

        """
        super().__init__(message)
        self.invocation_id = invocation_id


class AgentConfigurationError(AgentOrchestratorError):
    """Exception for agent configuration and validation errors."""


class AgentRateLimitError(AgentOrchestratorError):
    """Exception for rate limiting errors."""


class AgentTimeoutError(AgentOrchestratorError):
    """Exception for timeout errors."""


class ContextIntegrationError(AgentOrchestratorError):
    """Exception for context manager integration failures."""


class OrchestrationError(AgentOrchestratorError):
    """Exception for orchestration service failures."""


@fastapi_exception(handler="syntara.agent_orchestrator.error_handlers.llm_configuration_error_handler")
class LLMConfigurationError(AgentOrchestratorError):
    """Raised when LLM model configuration is missing or invalid.

    This exception indicates a server-side configuration issue,
    not a problem with the client's request.
    """


class CredentialResolutionError(AgentOrchestratorError):
    """Raised when an execution credential cannot be resolved for an integration.

    Covers: credential not found, disabled, missing secret data, decryption
    failure, or injector template resolution failure.  Distinct from
    LLMConfigurationError which is specific to LLM provider credentials.
    """


class EmptyLLMResponseError(AgentOrchestratorError, RetryableError):
    """Raised when the LLM returns an empty response with no tool calls.

    MRO: EmptyLLMResponseError → AgentOrchestratorError → RetryableError → SyntaraError.
    RetryableError is a pure marker (no __init__); super().__init__ chains through
    AgentOrchestratorError to SyntaraError without conflict.
    """

    def __init__(self, invocation_id: str | None = None) -> None:
        """Initialize with optional invocation ID for context."""
        super().__init__("LLM returned empty response with no tool calls", invocation_id)


class InvocationCancelledError(AgentOrchestratorError):
    """Raised when an invocation has been cancelled during execution."""

    def __init__(self, invocation_id: str, phase: str = "unknown") -> None:
        """Initialize exception with invocation ID and phase where cancellation occurred.

        Args:
            invocation_id: The UUID of the cancelled invocation
            phase: The execution phase where cancellation was detected (e.g., 'retrieval', 'compression', 'assembly')

        """
        message = f"Invocation {invocation_id} was cancelled during {phase} phase"
        super().__init__(message, invocation_id)
        self.phase = phase
