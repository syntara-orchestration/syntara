"""Orchestrator Agent for LangGraph-based agent coordination.

This agent serves as the entry point for the LangGraph state machine,
handling context integration and routing requests to appropriate specialist agents.
"""

import asyncio
import copy
import time
from typing import Any, ClassVar

import structlog

from syntara.agent_orchestrator.audit.agent_execution import (
    AgentExecutionEvent,
    AgentExecutionStatus,
)
from syntara.agent_orchestrator.audit.context_integration import (
    ContextIntegrationEvent,
    ContextIntegrationStatus,
)
from syntara.agent_orchestrator.constants import AgentRoutes
from syntara.agent_orchestrator.context_manager.planner import ContextManagerPlanner
from syntara.agent_orchestrator.exceptions import ContextIntegrationError
from syntara.agent_orchestrator.models.agent_state import AgentState
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.types import MetricType
from syntara.settings.cache.settings_cache import get_runtime_settings

logger = structlog.stdlib.get_logger(__name__)


class OrchestratorAgent:
    """Orchestrator agent responsible for context integration and routing.

    This agent:
    1. Calls the Context Manager to enhance prompts with relevant context
    2. Routes requests to appropriate specialist agents based on simple keyword analysis
    3. Handles graceful fallback when context integration fails
    """

    # Workflow keywords for routing decisions
    WORKFLOW_KEYWORDS: ClassVar[list[str]] = ["workflow", "create", "build", "generate"]

    def __init__(self, context_manager_planner: ContextManagerPlanner) -> None:
        """Initialize the orchestrator agent.

        Args:
            context_manager_planner: Context manager for prompt enhancement

        """
        self.context_manager = context_manager_planner
        self.settings = get_runtime_settings()

    async def execute(self, state: AgentState) -> AgentState:
        """Execute orchestration: context integration and routing.

        Args:
            state: Current LangGraph state

        Returns:
            Updated state with enhanced prompt and routing decision

        """
        # Extract context from AgentState
        session_id = state["session_id"]
        invocation_id = state["invocation_id"]
        execution_id = state.get("execution_id", None)
        request_id = state.get("request_id", None)

        # Emit START event (ContextVar also set by invocation_executor)
        AuditEventDispatcher.dispatch(
            AgentExecutionEvent(
                agent_type="orchestrator",
                session_id=session_id,
                invocation_id=invocation_id,
                execution_id=execution_id,
                request_id=request_id,
                status=AgentExecutionStatus.STARTED,
            )
        )

        try:
            logger.info("Orchestrator processing invocation", invocation_id=invocation_id)

            # Step 1: Context Integration
            enhanced_state = await self._integrate_context(state)

            # Step 2: Route to appropriate agent
            routed_state = self._route_request(enhanced_state)

            # Extract context package data
            context_pkg = routed_state.get("context_package")
            context_applied = context_pkg is not None
            grounding_score = context_pkg.get("grounding_score") if context_pkg is not None else None

            # Emit COMPLETED event
            AuditEventDispatcher.dispatch(
                AgentExecutionEvent(
                    agent_type="orchestrator",
                    session_id=session_id,
                    invocation_id=invocation_id,
                    execution_id=execution_id,
                    request_id=request_id,
                    status=AgentExecutionStatus.COMPLETED,
                    context_applied=context_applied,
                    grounding_score=grounding_score,
                    routed_to_agent=routed_state["current_agent"],
                )
            )

            logger.info(
                "Orchestrator routed for invocation",
                current_agent=routed_state["current_agent"],
                invocation_id=invocation_id,
            )

            return routed_state

        except Exception as e:
            # Emit FAILED event
            AuditEventDispatcher.dispatch(
                AgentExecutionEvent(
                    agent_type="orchestrator",
                    session_id=session_id,
                    invocation_id=invocation_id,
                    execution_id=execution_id,
                    request_id=request_id,
                    status=AgentExecutionStatus.FAILED,
                    error_type=type(e).__name__,
                )
            )
            raise

    async def _integrate_context(self, state: AgentState) -> AgentState:
        """Integrate context manager to enhance the prompt.

        Args:
            state: Current state

        Returns:
            State with enhanced prompt and context package

        """
        start = time.perf_counter()

        # Extract context from AgentState
        actor_context = state.get("actor_context")
        session_id = state["session_id"]
        invocation_id = state["invocation_id"]
        execution_id = state.get("execution_id", None)
        request_id = state.get("request_id", None)
        original_prompt = state["original_prompt"]

        # Extract activity context from metadata for audit correlation
        metadata = state.get("metadata", {}) or {}
        activity_id = metadata.get("activity_id")
        activity_name = metadata.get("activity_name")

        try:
            logger.debug("Calling context manager for session", session_id=session_id)

            # Get timeout from runtime settings
            timeout = await self.settings.get_int("context_manager.request_timeout_seconds")

            # Call context manager using PR 168 pattern with configurable timeout
            user_id = actor_context.actor_id if actor_context else None

            context_package = await asyncio.wait_for(
                self.context_manager.plan_request(
                    session_id=session_id,
                    invocation_id=invocation_id,
                    execution_id=execution_id,
                    request_id=request_id,
                    query=original_prompt,
                    user_id=user_id,
                    activity_id=activity_id,
                    activity_name=activity_name,
                ),
                timeout=timeout,
            )

            # Enhance prompt with context
            enhanced_prompt = self._format_context_prompt(original_prompt, context_package.payload)

            # Update state with context information
            updated_state = copy.deepcopy(state)
            updated_state["prompt"] = enhanced_prompt
            updated_state["context_package"] = {
                "package_id": context_package.id,
                "grounding_score": context_package.grounding_score,
                "citations": context_package.citations,
                "context_applied": True,
            }

            # Emit SUCCESS event
            AuditEventDispatcher.dispatch(
                ContextIntegrationEvent(
                    session_id=session_id,
                    invocation_id=invocation_id,
                    execution_id=execution_id,
                    request_id=request_id,
                    status=ContextIntegrationStatus.SUCCESS,
                    grounding_score=context_package.grounding_score,
                    citations_count=len(context_package.citations) if context_package.citations else 0,
                    activity_id=activity_id,
                    activity_name=activity_name,
                )
            )

            logger.info(
                "Context enhanced prompt for invocation",
                invocation_id=invocation_id,
                grounding_score=context_package.grounding_score,
            )

            return updated_state

        except TimeoutError as e:
            # Emit TIMEOUT event
            AuditEventDispatcher.dispatch(
                ContextIntegrationEvent(
                    session_id=session_id,
                    invocation_id=invocation_id,
                    execution_id=execution_id,
                    request_id=request_id,
                    status=ContextIntegrationStatus.TIMEOUT,
                    activity_id=activity_id,
                    activity_name=activity_name,
                )
            )

            # Wrap the underlying exception in our custom exception type
            context_error = ContextIntegrationError(f"Context integration failed: {e}", str(invocation_id))
            logger.warning(
                "Context integration failed for invocation. Proceeding with original prompt.",
                invocation_id=invocation_id,
                error=str(context_error),
            )

            # Graceful fallback: use original prompt without context
            fallback_state = copy.deepcopy(state)
            fallback_state["context_package"] = None
            return fallback_state

        except (ConnectionError, ValueError, KeyError, AttributeError, RuntimeError) as e:
            context_error = ContextIntegrationError(f"Context integration failed: {e}", str(invocation_id))

            # Emit FALLBACK event
            AuditEventDispatcher.dispatch(
                ContextIntegrationEvent(
                    session_id=session_id,
                    invocation_id=invocation_id,
                    execution_id=execution_id,
                    request_id=request_id,
                    status=ContextIntegrationStatus.FALLBACK,
                    activity_id=activity_id,
                    activity_name=activity_name,
                )
            )

            logger.warning(
                "Context integration failed for invocation. Proceeding with original prompt.",
                invocation_id=invocation_id,
                error=str(context_error),
            )

            # Graceful fallback: use original prompt without context
            fallback_state = copy.deepcopy(state)
            fallback_state["context_package"] = None
            return fallback_state
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            recorder = get_metrics_recorder()
            recorder.record(
                MetricType.CONTEXT_DURATION,
                duration_ms,
                unit="ms",
                labels={
                    "invocation_id": str(state["invocation_id"]),
                },
            )

    def _format_context_prompt(self, original_prompt: str, context_payload: dict[str, Any]) -> str:
        """Format context payload into enhanced prompt.

        Based on PR 168 prompt enhancement format.

        Args:
            original_prompt: User's original prompt
            context_payload: Context data from ContextManagerPlanner

        Returns:
            Enhanced prompt with context appended

        """
        if not context_payload:
            return original_prompt

        # Format context sections
        context_sections = []
        for key, value in context_payload.items():
            context_sections.append(f"## {key}\n{value}")

        formatted_context = "\n\n".join(context_sections)

        # Append context with clear delimiters
        return f"""{original_prompt}

--- CONTEXT ---
{formatted_context}
--- END CONTEXT ---"""

    def _route_request(self, state: AgentState) -> AgentState:
        """Route request to appropriate specialist agent.

        Uses simple keyword-based routing as agreed in planning session.

        Args:
            state: Current state with enhanced prompt

        Returns:
            State with current_agent set to target agent

        """
        start = time.perf_counter()
        prompt_lower = state["original_prompt"].lower()

        # Simple keyword matching for workflow generation
        if any(keyword in prompt_lower for keyword in self.WORKFLOW_KEYWORDS):
            target_agent = (
                AgentRoutes.GENERIC_AGENT
            )  # Routing to generic agent in both conditions, to keep space for workflow agent
            logger.debug("Routing based on workflow keywords", target_agent=target_agent)
        else:
            # Default to generic agent
            target_agent = AgentRoutes.GENERIC_AGENT
            logger.debug("Routing to default agent", target_agent=target_agent)

        # Update state with routing decision
        routed_state = copy.deepcopy(state)
        routed_state["current_agent"] = target_agent

        duration_ms = (time.perf_counter() - start) * 1000
        routed_state["routing_duration_ms"] = duration_ms

        recorder = get_metrics_recorder()
        recorder.record(
            MetricType.AGENT_ROUTING_DURATION,
            duration_ms,
            unit="ms",
            labels={
                "invocation_id": str(state["invocation_id"]),
                "target_agent": target_agent,
            },
        )

        return routed_state
