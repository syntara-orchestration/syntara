"""Base agent class providing common functionality for all agents."""

import time
from abc import ABC, abstractmethod
from typing import NoReturn
from uuid import UUID

import structlog

from syntara.agent_orchestrator.exceptions import (
    AgentConfigurationError,
    AgentOrchestratorError,
    AgentRateLimitError,
    AgentTimeoutError,
)
from syntara.agent_orchestrator.models.agent_state import AgentState
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.types import MetricType

logger = structlog.stdlib.get_logger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all agents in the orchestration system.

    Provides common functionality including:
    - Standardized error handling
    - Logging patterns
    - LangGraph node execution interface via Template Method pattern
    """

    def __init__(self) -> None:
        """Initialize base agent."""
        self.logger = structlog.stdlib.get_logger(self.__class__.__name__)

    async def execute_as_node(self, state: AgentState) -> AgentState:
        """Execute as LangGraph node with standardized workflow.

        This template method enforces a consistent execution pattern across all agents:
        1. Log execution start
        2. Execute agent-specific logic via _execute()
        3. Convert SQLModel response to dict for LangGraph
        4. Log execution success
        5. Handle errors consistently

        Args:
            state: LangGraph state containing prompt and metadata

        Returns:
            Response dictionary compatible with AgentState (from SQLModel.model_dump())

        Raises:
            AgentOrchestratorError: For general agent execution errors
            AgentTimeoutError: When execution times out
            AgentConfigurationError: For configuration/validation errors
            AgentRateLimitError: When rate limits are exceeded

        """
        self._log_execution_start(state["invocation_id"], state["session_id"])
        start = time.perf_counter()
        recorder = get_metrics_recorder()
        agent_name = self.__class__.__name__

        try:
            # Call agent-specific implementation (returns SQLModel instance)
            updated_state = await self._execute(state)

            duration_ms = (time.perf_counter() - start) * 1000
            recorder.record(
                MetricType.AGENT_INVOCATION_DURATION,
                duration_ms,
                unit="ms",
                labels={
                    "agent_type": agent_name,
                    "invocation_id": str(state["invocation_id"]),
                    "status": "success",
                },
            )

            self._log_execution_success(state["invocation_id"])

            return updated_state

        except Exception as e:  # noqa: BLE001
            duration_ms = (time.perf_counter() - start) * 1000
            recorder.record(
                MetricType.AGENT_INVOCATION_DURATION,
                duration_ms,
                unit="ms",
                labels={
                    "agent_type": agent_name,
                    "invocation_id": str(state["invocation_id"]),
                    "status": "error",
                },
            )
            self._handle_execution_error(e, state["invocation_id"])

    @abstractmethod
    async def _execute(self, state: AgentState) -> AgentState:
        """Execute agent-specific logic.

        This method must be implemented by each concrete agent to provide
        the actual execution logic. The base class handles logging, conversion
        to dict, and error handling.

        Args:
            state: LangGraph state containing prompt and metadata

        Returns:
            BaseAgentResponse subclass instance

        """

    def _handle_execution_error(self, error: Exception, invocation_id: UUID) -> NoReturn:
        """Handle execution errors by raising appropriate agent exceptions.

        This method inspects the error and raises the appropriate typed
        exception with proper chaining. Use this in except blocks to
        standardize error handling across agents.

        Args:
            error: The original exception that occurred
            invocation_id: Invocation ID for error context

        Raises:
            AgentTimeoutError: When the error is a timeout
            AgentConfigurationError: For configuration/validation errors
            AgentRateLimitError: When rate limits are detected
            AgentOrchestratorError: For all other errors

        """
        # Handle timeout errors
        if isinstance(error, TimeoutError):
            msg = "Request timed out"
            raise AgentTimeoutError(msg, str(invocation_id)) from error

        # Handle configuration and validation errors
        if isinstance(error, KeyError | ValueError):
            msg = f"Configuration or validation error: {error}"
            raise AgentConfigurationError(msg, str(invocation_id)) from error

        # Check for API configuration errors in message (invalid key, etc.)
        error_msg = str(error).lower()
        if "invalid" in error_msg and "key" in error_msg:
            raise AgentConfigurationError(str(error), str(invocation_id)) from error

        # Check for rate limit errors in error message
        if "rate limit" in error_msg:
            raise AgentRateLimitError(str(error), str(invocation_id)) from error

        # Handle as general agent error
        msg = f"Execution error: {error}"
        raise AgentOrchestratorError(msg, str(invocation_id)) from error

    def _log_execution_start(self, invocation_id: UUID, session_id: str) -> None:
        """Log the start of agent execution.

        Args:
            invocation_id: Invocation ID
            session_id: Session identifier for multi-tenant isolation

        """
        self.logger.info(
            "Agent executing as node",
            agent_class=self.__class__.__name__,
            invocation_id=invocation_id,
            session_id=session_id,
        )

    def _log_execution_success(self, invocation_id: UUID) -> None:
        """Log successful completion of agent execution.

        Args:
            invocation_id: Invocation ID

        """
        self.logger.info(
            "Agent node execution completed successfully",
            agent_class=self.__class__.__name__,
            invocation_id=invocation_id,
        )
