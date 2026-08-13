"""AgentState model for LangGraph state management.

This module defines the state structure that flows through the LangGraph
state machine during agent orchestration.
"""

import operator
from typing import Annotated, Any, NotRequired
from uuid import UUID

from langchain.messages import AnyMessage
from langchain_core.messages import HumanMessage
from typing_extensions import TypedDict

from syntara.agent_orchestrator.constants import AgentRoutes
from syntara.audit.emitter import AuditActorContext


class AgentState(TypedDict):
    """State model for LangGraph agent orchestration.

    This state is passed between nodes in the LangGraph execution flow,
    containing all necessary information for agent coordination and
    context management.
    """

    # Core prompt data
    prompt: str
    """The current prompt being processed (may be context-enhanced)"""

    original_prompt: str
    """The original user prompt before context enhancement"""

    # Session tracking
    session_id: str
    """Session identifier for multi-turn conversation tracking"""

    invocation_id: UUID
    """UUID of the invocation being processed"""

    actor_context: AuditActorContext
    """Actor context with atomic actor_id and actor_username"""

    # Context management
    context_package: dict[str, Any] | None
    """Context package from ContextManagerPlanner, if available"""

    # Routing and execution state
    current_agent: str
    """Name of the current/target agent ('orchestrator', 'generic_agent', 'workflow_generator')"""

    # Metadata and context
    metadata: dict[str, Any] | None
    """Metadata from invocation context_data (includes callback_url for PR #271)"""

    # Tool execution messages
    messages: Annotated[list[AnyMessage], operator.add]
    """Messages for LangGraph ToolNode execution and LLM communication"""

    # Results
    result: dict[str, Any] | None
    """Final result from agent execution"""

    # Token usage tracking (accumulated across LLM calls via operator.add)
    llm_token_usage_log: Annotated[list[dict[str, Any]], operator.add]
    """Per-call token usage entries from LLM provider responses"""

    # Workflow execution correlation
    execution_id: NotRequired[UUID | None]
    """Optional workflow execution ID for telemetry correlation"""

    # Workflow request correlation
    request_id: NotRequired[UUID | None]
    """Optional workflow request ID for telemetry correlation"""

    # Structured output support
    response_schema: NotRequired[dict[str, Any] | None]
    """Optional JSON Schema for structured output"""

    # Orchestrator timing (populated by OrchestratorAgent._route_request)
    routing_duration_ms: NotRequired[float | None]
    """Time spent in the routing decision, in milliseconds"""


class AgentStateFactory:
    """Factory for creating AgentState instances."""

    @staticmethod
    def create_initial_state(
        prompt: str,
        session_id: str,
        invocation_id: UUID,
        actor_context: AuditActorContext,
        metadata: dict[str, Any] | None = None,
        execution_id: UUID | None = None,
        request_id: UUID | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> AgentState:
        """Create initial state for LangGraph execution.

        Args:
            prompt: User's original prompt
            session_id: Session identifier
            invocation_id: Invocation UUID
            metadata: Optional metadata from invocation context_data (e.g., callback_url)
            actor_context: Optional audit actor context with atomic actor_id, actor_username, and actor_type
            execution_id: Optional workflow execution ID for telemetry correlation
            request_id: Optional X-Request-Id from the originating HTTP request.
            response_schema: Optional JSON Schema for structured output

        Returns:
            Initial AgentState ready for orchestration

        """
        return AgentState(
            prompt=prompt,
            original_prompt=prompt,
            session_id=session_id,
            invocation_id=invocation_id,
            actor_context=actor_context,
            context_package=None,
            current_agent=AgentRoutes.ORCHESTRATOR,
            metadata=metadata,
            messages=[HumanMessage(prompt)],
            result=None,
            llm_token_usage_log=[],
            execution_id=execution_id or None,
            request_id=request_id or None,
            response_schema=response_schema,
        )
