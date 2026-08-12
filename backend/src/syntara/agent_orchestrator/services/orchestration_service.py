"""OrchestrationService for LangGraph-based agent coordination.

This service manages the LangGraph state machine that coordinates
multiple specialized agents with context integration and checkpointing.
"""

import asyncio
import contextlib
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse, urlunparse
from uuid import UUID

import httpx
import structlog
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from syntara.agent_orchestrator.agents.generic_agent import GenericAgent
from syntara.agent_orchestrator.agents.orchestrator_agent import OrchestratorAgent
from syntara.agent_orchestrator.constants import AgentRoutes
from syntara.agent_orchestrator.context_manager.planner import ContextManagerPlanner
from syntara.agent_orchestrator.models.agent_response import GenericAgentResponse
from syntara.agent_orchestrator.models.agent_state import AgentState, AgentStateFactory
from syntara.agent_orchestrator.models.context_data import InvocationContextData
from syntara.agent_orchestrator.models.streaming_events import (
    CompletionEventData,
    DeltaEventData,
    ToolCallEventData,
    ToolResultEventData,
)
from syntara.agent_orchestrator.services.error_handler import classify_streaming_error
from syntara.agent_orchestrator.services.streaming_service import get_invocation_stream_id
from syntara.agent_orchestrator.tool_manager import ToolRetriever
from syntara.agent_orchestrator.tool_manager.execution_failure_handler import (
    create_tool_awrapper,
    create_tool_wrapper,
)
from syntara.agent_orchestrator.utils.context_helpers import extract_request_id
from syntara.agent_orchestrator.utils.token_usage import aggregate_token_usage
from syntara.agent_orchestrator.utils.used_tools import aggregate_used_tools
from syntara.agent_orchestrator.utils.workflow_signal_client import WorkflowSignalClient
from syntara.audit.decorators import audit
from syntara.audit.emitter import AuditActorContext
from syntara.audit.models.audit_event import EventCategory, EventSeverity
from syntara.core.cache.stream import StreamClient
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.instrumentation import LLMStreamTracker

logger = structlog.stdlib.get_logger(__name__)


_MAX_TOOL_OUTPUT_LENGTH = 10_000
_MAX_TOOL_CONTENT_LENGTH = 200


class _TraceAccumulator:
    """Accumulates LangGraph streaming events into a persisted agent trace.

    Coalesces consecutive LLM delta tokens into single reasoning blocks and
    captures tool call/result steps with timing and token metadata.
    """

    def __init__(self) -> None:
        self._steps: list[dict[str, Any]] = []
        self._reasoning_buffer: list[str] = []
        self._reasoning_start_ns: int | None = None
        self._reasoning_explicit_tokens: int = 0
        self._reasoning_fallback_chunks: int = 0
        self._tool_start_ns: dict[int, int] = {}
        self._tool_run_to_call_index: dict[str, int] = {}
        self._tool_name_to_call_indices: dict[str, deque[int]] = defaultdict(deque)
        self._tool_call_counter: int = 0

    def accumulate(self, event_dict: dict[str, Any]) -> None:
        event_type = event_dict.get("event")
        if event_type == "on_chat_model_stream":
            self._on_chat_stream(event_dict)
        elif event_type == "on_tool_start":
            self._on_tool_start(event_dict)
        elif event_type == "on_tool_end":
            self._on_tool_end(event_dict)

    def _on_chat_stream(self, event: dict[str, Any]) -> None:
        data = event.get("data")
        if not isinstance(data, dict):
            return
        chunk = data.get("chunk")
        if chunk is None:
            return
        content = chunk.content if hasattr(chunk, "content") else None
        if not content:
            return

        if self._reasoning_start_ns is None:
            self._reasoning_start_ns = time.monotonic_ns()
        self._reasoning_buffer.append(content)
        token_count = 0
        usage = getattr(chunk, "usage_metadata", None)
        if isinstance(usage, dict):
            raw = usage.get("output_tokens", 0)
            token_count = raw if isinstance(raw, int) else 0
        # Prefer provider-reported output tokens when available.
        # If unavailable for the full block, fall back to chunk count.
        if token_count > 0:
            self._reasoning_explicit_tokens += token_count
        else:
            self._reasoning_fallback_chunks += 1

    def _on_tool_start(self, event: dict[str, Any]) -> None:
        self._flush_reasoning()
        tool_name = event.get("name", "unknown")
        data = event.get("data", {})
        tool_input = data.get("input", {}) if isinstance(data, dict) else {}
        serializable_types = (str, int, float, bool, list, dict, type(None))
        tool_input = {k: v for k, v in tool_input.items() if isinstance(v, serializable_types)}

        call_index = self._tool_call_counter
        self._tool_call_counter += 1
        self._tool_start_ns[call_index] = time.monotonic_ns()
        self._tool_name_to_call_indices[tool_name].append(call_index)
        run_id = event.get("run_id")
        if isinstance(run_id, str) and run_id:
            self._tool_run_to_call_index[run_id] = call_index
        call_id = f"call-{call_index}"
        self._steps.append(
            {
                "type": "tool_call",
                "timestamp": datetime.now(UTC).isoformat(),
                "content": f"Calling {tool_name}",
                "tool_name": tool_name,
                "tool_input": tool_input,
                "call_id": call_id,
                "_call_index": call_index,
            }
        )

    @staticmethod
    def _detect_tool_failure(data: object, raw_output: object) -> str:
        if isinstance(data, dict) and data.get("error") is not None:
            return "failed"
        if hasattr(raw_output, "status") and raw_output.status in ("error", "failed"):
            return "failed"
        if isinstance(raw_output, dict) and raw_output.get("status") in ("error", "failed"):
            return "failed"
        return "success"

    def _evict_stale_name_index(self, tool_name: str, call_index: int) -> None:
        q = self._tool_name_to_call_indices.get(tool_name)
        if q:
            with contextlib.suppress(ValueError):
                q.remove(call_index)

    def _resolve_call_index(self, tool_name: str, event: dict[str, Any]) -> int | None:
        run_id = event.get("run_id")
        if isinstance(run_id, str) and run_id:
            call_index = self._tool_run_to_call_index.pop(run_id, None)
            if call_index is not None:
                self._evict_stale_name_index(tool_name, call_index)
                return call_index
        q = self._tool_name_to_call_indices.get(tool_name)
        return q.popleft() if q else None

    def _on_tool_end(self, event: dict[str, Any]) -> None:
        tool_name = event.get("name", "unknown")
        data = event.get("data", {})
        raw_output = data.get("output", "") if isinstance(data, dict) else ""
        tool_output = str(raw_output.content) if hasattr(raw_output, "content") else str(raw_output)
        status = self._detect_tool_failure(data, raw_output)

        call_index = self._resolve_call_index(tool_name, event)
        duration_ms: int | None = None
        if call_index is not None:
            start_ns = self._tool_start_ns.pop(call_index, None)
            if start_ns is not None:
                duration_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)

        if len(tool_output) > _MAX_TOOL_OUTPUT_LENGTH:
            tool_output = tool_output[:_MAX_TOOL_OUTPUT_LENGTH] + "... [truncated]"

        result_step: dict[str, Any] = {
            "type": "tool_result",
            "timestamp": datetime.now(UTC).isoformat(),
            "content": (
                tool_output[:_MAX_TOOL_CONTENT_LENGTH] if len(tool_output) > _MAX_TOOL_CONTENT_LENGTH else tool_output
            ),
            "tool_name": tool_name,
            "tool_output": tool_output,
            "status": status,
        }
        if call_index is not None:
            result_step["call_id"] = f"call-{call_index}"
        if duration_ms is not None:
            result_step["duration_ms"] = duration_ms
        self._steps.append(result_step)

    def _flush_reasoning(self) -> None:
        if not self._reasoning_buffer:
            return
        text = "".join(self._reasoning_buffer)
        duration_ms: int | None = None
        if self._reasoning_start_ns is not None:
            duration_ms = int((time.monotonic_ns() - self._reasoning_start_ns) / 1_000_000)

        step: dict[str, Any] = {
            "type": "reasoning",
            "timestamp": datetime.now(UTC).isoformat(),
            "content": text,
            "tokens": (
                self._reasoning_explicit_tokens
                if self._reasoning_explicit_tokens > 0
                else self._reasoning_fallback_chunks
            ),
        }
        if duration_ms is not None:
            step["duration_ms"] = duration_ms
        self._steps.append(step)
        self._reasoning_buffer.clear()
        self._reasoning_start_ns = None
        self._reasoning_explicit_tokens = 0
        self._reasoning_fallback_chunks = 0

    def finalize(self, model_name: str, final_answer: str | None = None) -> dict[str, Any]:
        self._flush_reasoning()
        last_reasoning = next(
            (s.get("content") for s in reversed(self._steps) if s.get("type") == "reasoning"),
            None,
        )
        if final_answer and final_answer != last_reasoning:
            self._steps.append(
                {
                    "type": "final_answer",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "content": final_answer,
                }
            )

        # Strip any remaining internal tracking keys
        for step in self._steps:
            step.pop("_call_index", None)

        total_tokens = sum(s.get("tokens", 0) for s in self._steps)
        total_duration_ms = sum(s.get("duration_ms", 0) for s in self._steps)
        return {
            "model": model_name,
            "total_tokens": total_tokens,
            "total_duration_ms": total_duration_ms,
            "steps": self._steps,
        }


class OrchestrationService:
    """Service for managing LangGraph-based agent orchestration.

    This service:
    1. Sets up the LangGraph state machine with agent nodes
    2. Manages routing between orchestrator, generic_agent, and workflow_generator
    3. Handles checkpointing for multi-turn conversations
    4. Provides execution interface for the InvocationService
    """

    def __init__(
        self,
        llm: ChatOpenAI,
        context_manager_planner: ContextManagerPlanner,
        credential_resolver: Callable[[UUID], Awaitable[str | None]] | None = None,
        tool_selection_strategy: str | None = None,
        tool_selections: list[str] | None = None,
    ) -> None:
        """Initialize the orchestration service.

        Args:
            llm: Language model for agent execution
            context_manager_planner: Context manager for prompt enhancement
            credential_resolver: Optional async callable that resolves a bearer token given an
                integration_id. Passed to ToolRetriever so MCP providers with a linked
                integration are authenticated at tool-call time.
            tool_selection_strategy: "ALL", "NONE", or "SELECTED". None/absent treated as "NONE" (no tools).
            tool_selections: Tool UUIDs to make available when strategy is "SELECTED".

        """
        self.llm = llm
        self.context_manager = context_manager_planner
        self._credential_resolver = credential_resolver
        self._tool_selection_strategy = tool_selection_strategy
        self._tool_selections = set(tool_selections or [])

    async def _setup_graph(self, state: AgentState) -> CompiledStateGraph[AgentState, None, Any, Any]:
        """Set up the LangGraph state machine with ToolNode integration.

        Returns:
            Compiled LangGraph state machine

        """
        logger.info("Initializing LangGraph orchestration with ToolNode support")

        # Create state graph
        workflow = StateGraph(AgentState)

        # Add agent nodes
        session_id: str = state["session_id"]
        invocation_id: UUID = state["invocation_id"]
        execution_id: UUID | None = state["execution_id"]
        request_id: UUID | None = state["request_id"]
        metadata = state.get("metadata") or {}
        activity_id = metadata.get("activity_id")
        activity_name = metadata.get("activity_name")
        available_tools: list[BaseTool] = await self._get_tools(
            session_id, invocation_id, execution_id, request_id, activity_id, activity_name
        )

        workflow.add_node(AgentRoutes.ORCHESTRATOR, self._create_orchestrator_node())
        workflow.add_node(AgentRoutes.GENERIC_AGENT, self._create_generic_agent_node(available_tools))
        workflow.add_node(
            AgentRoutes.TOOLS,
            self._create_tool_node(
                available_tools,
                session_id,
                invocation_id,
                execution_id=execution_id,
                request_id=request_id,
                activity_id=activity_id,
                activity_name=activity_name,
            ),
        )

        # Set entry point to ToolNode
        workflow.set_entry_point(AgentRoutes.ORCHESTRATOR)

        # Add conditional edges from orchestrator to specialist agents
        workflow.add_conditional_edges(
            AgentRoutes.ORCHESTRATOR,
            self._route_after_orchestrator,
            {
                AgentRoutes.GENERIC_AGENT: AgentRoutes.GENERIC_AGENT,
            },
        )

        # Add conditional edges from GenericAgent to Tools
        workflow.add_conditional_edges(AgentRoutes.GENERIC_AGENT, self._should_call_tools, [AgentRoutes.TOOLS, END])

        # Tools to GenericAgent route
        workflow.add_edge(AgentRoutes.TOOLS, AgentRoutes.GENERIC_AGENT)

        # Compile graph with checkpointing for multi-turn support
        checkpointer = MemorySaver()
        graph = workflow.compile(checkpointer=checkpointer)

        logger.info("LangGraph orchestration with ToolNode initialized successfully")
        return graph

    async def _get_tools(
        self,
        session_id: str,
        invocation_id: UUID,
        execution_id: UUID | None = None,
        request_id: UUID | None = None,
        activity_id: str | None = None,
        activity_name: str | None = None,
    ) -> list[BaseTool]:
        """Get available tools for the agent execution.

        Performs tool discovery and synchronization to ensure all available
        tools are properly registered and accessible for the current invocation.

        Args:
            session_id: Session identifier
            invocation_id: Unique identifier for the current invocation
            execution_id: Optional Workflow Execution ID
            request_id: Optional X-Request-Id from the originating HTTP request.
            activity_id: Optional activity identifier from workflow context
            activity_name: Optional activity name from workflow context

        Returns:
            List of synchronized BaseTool instances available for agent use

        """
        retriever = ToolRetriever(
            session_id,
            invocation_id,
            execution_id=execution_id,
            request_id=request_id,
            credential_resolver=self._credential_resolver,
            activity_id=activity_id,
            activity_name=activity_name,
        )
        tools = await retriever.retrieve_tools()
        return self._apply_tool_selection(tools)

    def _apply_tool_selection(self, tools: list[BaseTool]) -> list[BaseTool]:
        """Filter tools according to the configured selection strategy.

        ALL: return all enabled tools unchanged.
        SELECTED: return only tools whose tool_id is in self._tool_selections.
            Invalid/unavailable selected IDs are reported via warning log; execution
            continues with the valid tools.
        None or NONE: return an empty list (NONE is the explicit default).
        """
        strategy = self._tool_selection_strategy
        if strategy == "ALL":
            return tools
        if strategy == "SELECTED":
            available_ids = {(t.metadata or {}).get("tool_id", "") for t in tools}
            available_ids.discard("")
            invalid_ids = sorted(self._tool_selections - available_ids)
            if invalid_ids:
                logger.warning(
                    "Invalid or unavailable tool selections ignored at runtime; proceeding with valid tools only",
                    invalid_tool_ids=invalid_ids,
                    selected_count=len(self._tool_selections),
                    available_count=len(available_ids),
                )
            return [t for t in tools if (t.metadata or {}).get("tool_id", "") in self._tool_selections]
        # None or "NONE" → no tools
        return []

    @audit(
        EventCategory.AGENT_INTERACTION,
        event_action="orchestrate",
        source_component="syntara.agent_orchestrator.orchestration",
        event_severity=EventSeverity.INFO,
        capture_args={"session_id", "invocation_id", "execution_id"},
    )
    async def execute(
        self,
        prompt: str,
        session_id: str,
        invocation_id: UUID,
        actor_context: AuditActorContext,
        ctx: InvocationContextData,
        execution_id: UUID | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute agent orchestration with LLM streaming through LangGraph.

        Uses LangGraph's astream_events() to capture LLM streaming deltas and publish
        them to Redis for WebSocket clients to consume.

        Args:
            prompt: User's prompt to process
            session_id: Session identifier for multi-turn tracking
            invocation_id: Invocation UUID
            actor_context: Optional AuditActorContext with actor_id, actor_username, actor_type
            ctx: Parsed context_data model
            execution_id: Optional workflow execution ID for telemetry correlation
            response_schema: Optional JSON Schema for structured output

        Returns:
            Agent execution result with context enhancement metadata (dict format for DB storage)

        Raises:
            Any exceptions from LLM API or streaming infrastructure

        """
        logger.info("Executing streaming orchestration for invocation", invocation_id=invocation_id)

        stream_id = get_invocation_stream_id(invocation_id)
        request_id = extract_request_id(ctx)

        # Create initial state — AgentState is a LangGraph TypedDict,
        # so we pass a plain dict with secrets revealed.
        initial_state = AgentStateFactory.create_initial_state(
            prompt=prompt,
            session_id=session_id,
            invocation_id=invocation_id,
            metadata=ctx.to_state_dict() if ctx else None,
            actor_context=actor_context,
            execution_id=execution_id,
            request_id=request_id,
            response_schema=response_schema,
        )

        graph: CompiledStateGraph[AgentState, None, Any, Any] = await self._setup_graph(initial_state)

        trace_accumulator = _TraceAccumulator()

        async with StreamClient() as client:
            try:
                # Execute graph with streaming events
                config: RunnableConfig = cast("RunnableConfig", {"configurable": {"thread_id": session_id}})
                final_state = await self._execute_graph_streaming(
                    graph, initial_state, config, invocation_id, stream_id, client, trace_accumulator
                )

                # Build response with streaming metadata and context enhancement
                result = self._build_streaming_result(invocation_id, stream_id, final_state)

                # Embed agent trace in result so it flows to workflow activity output_data
                final_answer = self._extract_final_answer_text(final_state)
                result["agent_trace"] = trace_accumulator.finalize(
                    model_name=self._get_model_name(),
                    final_answer=final_answer,
                )
                tool_calls = [
                    {
                        "tool_name": s["tool_name"],
                        "duration_ms": s.get("duration_ms"),
                        "status": s.get("status", "success"),
                    }
                    for s in result["agent_trace"]["steps"]
                    if s.get("type") == "tool_result"
                ]
                tools_used = [s["tool_name"] for s in result["agent_trace"]["steps"] if s.get("type") == "tool_call"]
                result["tools_used"] = tools_used
                result["tool_calls"] = tool_calls
                # Prefer provider-reported prompt+completion totals (includes context)
                # over stream-derived reasoning-step estimates for Agent Steps header.
                self._apply_provider_token_totals(result)

                # Publish completion event
                await self._publish_completion_event(invocation_id, stream_id, client)

                # Handle completion callback with enriched result payload.
                await self._handle_completion_callback(final_state, invocation_id, ctx, signal_result=result)

                logger.info("Streaming orchestration completed", invocation_id=invocation_id)

                return result

            except Exception as e:
                # Handle streaming errors
                logger.exception(
                    "Exception in orchestration service",
                    invocation_id=invocation_id,
                    error_type=type(e).__name__,
                )
                await self._handle_streaming_error(e, invocation_id, stream_id, client)

                # Send failure signal to workflow if callback_url is present
                cb_url = ctx.callback_url.get_secret_value() if ctx and ctx.callback_url else None
                await WorkflowSignalClient.send_failure_signal(cb_url, invocation_id, e)

                raise

    async def _execute_graph_streaming(
        self,
        graph: CompiledStateGraph[AgentState, None, Any, Any],
        initial_state: AgentState,
        config: RunnableConfig,
        invocation_id: UUID,
        stream_id: str,
        client: StreamClient,
        trace_accumulator: _TraceAccumulator,
    ) -> AgentState | None:
        """Execute graph with streaming and capture final state.

        Args:
            graph: Compiled LangGraph state machine
            initial_state: Initial agent state
            config: Runnable config with thread_id
            invocation_id: Invocation UUID
            stream_id: Redis stream ID
            client: StreamClient for publishing events
            trace_accumulator: Accumulates events for persistence

        Returns:
            Final agent state or None if not captured

        """
        final_state: AgentState | None = None
        ttft_tracker = LLMStreamTracker(
            recorder=get_metrics_recorder(),
            model=self._get_model_name(),
        )

        # Stream events from LangGraph
        async for event in graph.astream_events(initial_state, config, version="v2"):
            # Process streaming events (event is StandardStreamEvent | CustomStreamEvent)
            event_dict = cast("dict[str, Any]", event)
            ttft_tracker.process_event(event_dict)
            await self._process_streaming_event(event_dict, invocation_id, stream_id, client)

            # Accumulate for trace persistence
            trace_accumulator.accumulate(event_dict)

            # Capture final state from graph end events
            final_state = self._extract_final_state(event_dict, final_state)

        return final_state

    def _extract_final_state(
        self, event_dict: dict[str, Any], current_final_state: AgentState | None
    ) -> AgentState | None:
        """Extract final state from graph end event.

        Args:
            event_dict: Event dictionary from astream_events
            current_final_state: Current captured final state

        Returns:
            Updated final state or current state if not a graph end event

        """
        if event_dict.get("event") == "on_chain_end" and event_dict.get("name") == "LangGraph":
            data = event_dict.get("data")
            if isinstance(data, dict):
                return cast("AgentState | None", data.get("output"))

        return current_final_state

    @staticmethod
    def _extract_final_answer_text(final_state: AgentState | None) -> str | None:
        """Extract the final answer text from the agent's result."""
        if not final_state:
            return None
        result = final_state.get("result")
        if isinstance(result, dict):
            return result.get("content")
        return None

    async def _handle_completion_callback(
        self,
        final_state: AgentState | None,
        invocation_id: UUID,
        ctx: InvocationContextData | None = None,
        signal_result: dict[str, Any] | None = None,
    ) -> None:
        """Handle completion callback with error handling.

        Args:
            final_state: Final agent state with callback metadata
            invocation_id: Invocation UUID for logging
            ctx: Original typed context_data (fallback when final_state
                doesn't preserve metadata, e.g. some LangGraph configurations)
            signal_result: Pre-built result dict to send in the callback signal

        """
        logger.info(
            "Checking for completion callback",
            invocation_id=invocation_id,
            has_final_state=final_state is not None,
        )

        if not final_state:
            logger.warning("No final_state available for callback", invocation_id=invocation_id)
            return

        try:
            await self._send_completion_callback(final_state, invocation_id, ctx, signal_result=signal_result)
        except (httpx.RequestError, httpx.HTTPStatusError, httpx.TimeoutException):
            logger.exception("Activity signal failed for invocation", invocation_id=invocation_id)
            # Continue without failing - notification is not critical
        except Exception:
            logger.exception("Unexpected error during activity signal for invocation", invocation_id=invocation_id)
            # Continue without failing - notification is not critical

    async def _process_streaming_event(
        self, event: dict[str, Any], invocation_id: UUID, stream_id: str, client: StreamClient
    ) -> None:
        """Process a single streaming event from LangGraph.

        Args:
            event: Event dictionary from astream_events()
            invocation_id: Invocation UUID
            stream_id: Redis stream ID
            client: StreamClient for publishing events

        """
        event_type = event.get("event")

        # Handle LLM streaming events
        if event_type == "on_chat_model_stream":
            await self._process_chat_stream_event(event, invocation_id, stream_id, client)

        # Handle tool start events
        elif event_type == "on_tool_start":
            await self._process_tool_start_event(event, invocation_id, stream_id, client)

        # Handle tool end events
        elif event_type == "on_tool_end":
            await self._process_tool_end_event(event, invocation_id, stream_id, client)

    async def _publish_stream_event(
        self,
        client: StreamClient,
        stream_id: str,
        event_type: str,
        invocation_id: UUID,
        data: dict[str, Any],
    ) -> None:
        """Build a streaming event dict and publish it to Redis.

        Centralises the repeated pattern of constructing an event envelope
        (event_type + invocation_id + timestamp + data) and publishing it
        via the ``StreamClient``.

        Args:
            client: StreamClient for publishing events
            stream_id: Redis stream ID
            event_type: Event type string (e.g. "delta", "tool_call", "error")
            invocation_id: Invocation UUID
            data: Pre-serialised event payload (already a dict)

        """
        event = {
            "event_type": event_type,
            "invocation_id": str(invocation_id),
            "timestamp": datetime.now(UTC).isoformat(),
            "data": data,
        }
        await client.publish(stream_id, event)

    async def _process_chat_stream_event(
        self, event: dict[str, Any], invocation_id: UUID, stream_id: str, client: StreamClient
    ) -> None:
        """Process LLM chat model streaming event.

        Args:
            event: Event dictionary from astream_events()
            invocation_id: Invocation UUID
            stream_id: Redis stream ID
            client: StreamClient for publishing events

        """
        data = event.get("data")
        if isinstance(data, dict):
            chunk = data.get("chunk")
            if chunk is not None:
                content = chunk.content if hasattr(chunk, "content") else None

                if content:
                    # Publish delta event to Redis
                    delta_data = DeltaEventData(delta=content)
                    await self._publish_stream_event(client, stream_id, "delta", invocation_id, delta_data.model_dump())
                    logger.debug("Published delta event", invocation_id=invocation_id)

    async def _process_tool_start_event(
        self, event: dict[str, Any], invocation_id: UUID, stream_id: str, client: StreamClient
    ) -> None:
        """Process tool execution start event.

        Args:
            event: Event dictionary from astream_events()
            invocation_id: Invocation UUID
            stream_id: Redis stream ID
            client: StreamClient for publishing events

        """
        tool_name = event.get("name", "unknown")
        data = event.get("data", {})
        tool_input = data.get("input", {}) if isinstance(data, dict) else {}

        logger.info("Tool call started", tool_name=tool_name, invocation_id=invocation_id)

        # Detect non-serializable objects leaked by LangChain internals (e.g.
        # AsyncCallbackManager) so we get actionable diagnostics instead of an
        # opaque json.dumps TypeError deep in the Redis publish path.
        _bad = {
            k: type(v).__name__
            for k, v in tool_input.items()
            if not isinstance(v, (str, int, float, bool, list, dict, type(None)))
        }
        if _bad:
            logger.error(
                "tool_input contains non-JSON-serializable values. "
                "Stripping offending keys so the event can still be published.",
                tool_name=tool_name,
                invocation_id=invocation_id,
                bad_keys=_bad,
            )
            tool_input = {k: v for k, v in tool_input.items() if k not in _bad}

        # Publish streaming event for real-time WebSocket
        tool_call_data = ToolCallEventData(tool_name=tool_name, tool_input=tool_input)
        await self._publish_stream_event(client, stream_id, "tool_call", invocation_id, tool_call_data.model_dump())

    async def _process_tool_end_event(
        self, event: dict[str, Any], invocation_id: UUID, stream_id: str, client: StreamClient
    ) -> None:
        """Process tool execution end event.

        Args:
            event: Event dictionary from astream_events()
            invocation_id: Invocation UUID
            stream_id: Redis stream ID
            client: StreamClient for publishing events

        """
        tool_name = event.get("name", "unknown")
        data = event.get("data", {})

        # Extract tool output - handle both raw strings and ToolMessage objects
        raw_output = data.get("output", "") if isinstance(data, dict) else ""
        tool_output = str(raw_output.content) if hasattr(raw_output, "content") else str(raw_output)

        logger.info("Tool call completed", tool_name=tool_name, invocation_id=invocation_id)

        # Publish streaming event for real-time WebSocket
        tool_result_data = ToolResultEventData(tool_name=tool_name, tool_output=tool_output)
        await self._publish_stream_event(client, stream_id, "tool_result", invocation_id, tool_result_data.model_dump())

    async def _publish_completion_event(self, invocation_id: UUID, stream_id: str, client: StreamClient) -> None:
        """Publish completion event to Redis.

        Args:
            invocation_id: Invocation UUID
            stream_id: Redis stream ID
            client: StreamClient for publishing

        """
        completion_data = CompletionEventData()
        await self._publish_stream_event(client, stream_id, "completion", invocation_id, completion_data.model_dump())

    async def _handle_streaming_error(
        self,
        exception: Exception,
        invocation_id: UUID,
        stream_id: str,
        client: StreamClient,
    ) -> None:
        """Handle streaming error with logging and event publishing.

        Args:
            exception: The exception that occurred
            invocation_id: Invocation UUID
            stream_id: Redis stream ID
            client: StreamClient for publishing events

        """
        logger.exception("Streaming orchestration failed", invocation_id=invocation_id)

        # Publish error event with RFC 9457 classification
        error_data = classify_streaming_error(exception, invocation_id=invocation_id)
        await self._publish_stream_event(
            client, stream_id, "error", invocation_id, error_data.model_dump(exclude_none=True)
        )

    def _build_streaming_result(
        self, invocation_id: UUID, stream_id: str, final_state: AgentState | None = None
    ) -> dict[str, Any]:
        """Build result dictionary with streaming metadata and context enhancement.

        Args:
            invocation_id: Invocation UUID
            stream_id: Redis stream ID
            final_state: Final LangGraph state containing context metadata and result

        Returns:
            Result dictionary for database storage with context enhancement metadata

        """
        # If we have final state with result, use that as the base (includes actual LLM response)
        if final_state and final_state.get("result"):
            enhanced_result = final_state["result"]
            if isinstance(enhanced_result, dict):
                # Thread token usage log through to InvocationExecutor
                llm_token_usage_log = final_state.get("llm_token_usage_log", [])
                if llm_token_usage_log:
                    enhanced_result["llm_token_usage_log"] = llm_token_usage_log
                result = self._enhance_result_with_streaming_metadata(enhanced_result, stream_id)
                # Persist orchestrator timing so the API server's completion
                # poller can emit agent metrics (the Temporal worker and the
                # API server have separate in-memory MetricsRecorder instances).
                routing_ms = final_state.get("routing_duration_ms")
                if routing_ms is not None:
                    result.setdefault("response_metadata", {})["routing_duration_ms"] = routing_ms
                    result["response_metadata"]["routed_to_agent"] = final_state.get("current_agent", "unknown")
                return result

        # Fallback: Build placeholder response if no final state available
        return self._build_fallback_response(invocation_id, stream_id)

    @staticmethod
    def _apply_provider_token_totals(result: dict[str, Any]) -> None:
        """Set agent_trace/tokens_used from full provider usage when available.

        Stream-derived step tokens only capture reasoning output estimates.
        ``llm_token_usage_log`` includes prompt + completion for every LLM call
        (prompt, context, tool-loop turns), which is what Agent Steps should show.
        Falls back to stream-derived ``agent_trace.total_tokens`` when the usage
        log is absent.
        """
        agent_trace = result.get("agent_trace")
        usage_log = result.get("llm_token_usage_log") or []

        if usage_log:
            _prompt, _completion, total_tokens, _details = aggregate_token_usage(usage_log)
            if isinstance(agent_trace, dict):
                agent_trace["total_tokens"] = total_tokens
        elif isinstance(agent_trace, dict):
            total_tokens = int(agent_trace.get("total_tokens") or 0)
        else:
            result["tokens_used"] = 0
            return

        result["tokens_used"] = total_tokens

    def _get_model_name(self) -> str:
        """Safely extract model name from LLM instance.

        Returns:
            Model name string, or "unknown" if unavailable

        """
        if hasattr(self.llm, "model_name"):
            try:
                return str(self.llm.model_name)
            except (AttributeError, TypeError, ValueError):
                logger.debug("Failed to extract model_name from LLM", exc_info=True)
                return "unknown"
        return "unknown"

    def _enhance_result_with_streaming_metadata(self, result: dict[str, Any], stream_id: str) -> dict[str, Any]:
        """Enhance result with streaming metadata.

        Args:
            result: Result dictionary to enhance
            stream_id: Redis stream ID

        Returns:
            Enhanced result with streaming metadata

        """
        enhanced = result.copy()

        # Add streaming metadata to response_metadata
        if "response_metadata" not in enhanced:
            enhanced["response_metadata"] = {}

        enhanced["response_metadata"]["source"] = "streaming"
        enhanced["response_metadata"]["stream_id"] = stream_id
        enhanced["response_metadata"]["orchestration"] = "langgraph"
        enhanced["response_metadata"]["model"] = self._get_model_name()

        return enhanced

    def _build_fallback_response(self, invocation_id: UUID, stream_id: str) -> dict[str, Any]:
        """Build fallback response when final state is unavailable.

        Args:
            invocation_id: Invocation UUID
            stream_id: Redis stream ID

        Returns:
            Fallback response dictionary

        """
        ws_endpoint = f"/ws/agent_orchestrator/v1/invocations/{invocation_id}"
        content_msg = f"Response streamed successfully. Connect to WebSocket endpoint {ws_endpoint} to view events."

        response = GenericAgentResponse(
            type="answer",
            content=content_msg,
            response_metadata={
                "source": "streaming",
                "stream_id": stream_id,
                "model": self._get_model_name(),
                "orchestration": "langgraph",
            },
        )

        return response.model_dump()

    async def _send_completion_callback(
        self,
        final_state: AgentState,
        invocation_id: UUID,
        ctx: InvocationContextData | None = None,
        signal_result: dict[str, Any] | None = None,
    ) -> None:
        """Send completion callback to workflow after agent execution.

        Sends HTTP callback to workflow when agent completes, replicating the functionality
        previously handled by NotificationNode.

        Falls back to ``ctx`` (typed invocation context_data) when LangGraph's
        final state doesn't preserve ``metadata`` or ``result``.

        Args:
            final_state: Final state containing agent result and metadata
            invocation_id: Invocation UUID for logging
            ctx: Original typed context_data (fallback for callback_url)
            signal_result: Pre-built result dict to send in the callback signal

        """
        logger.debug(
            "Checking completion callback for invocation",
            invocation_id=invocation_id,
            final_state_keys=list(final_state.keys()) if final_state else None,
        )

        # Extract callback URL from final_state metadata, falling back to typed context_data
        state_metadata = final_state.get("metadata") or {}
        callback_url = state_metadata.get("callback_url")
        if not callback_url and ctx and ctx.callback_url:
            callback_url = ctx.callback_url.get_secret_value()

        if not callback_url:
            logger.warning(
                "No callback_url found in metadata for invocation, skipping callback",
                invocation_id=invocation_id,
            )
            return

        # Extract agent result, preferring explicit payload prepared by execute().
        result = signal_result if signal_result is not None else final_state.get("result")
        if not result:
            logger.warning("No result found in final_state for callback", invocation_id=invocation_id)
            return

        # Attach tool-usage summary for execution results.
        # Shallow-copy so we do not mutate the shared final_state["result"] reference.
        payload = result
        if isinstance(result, dict):
            used_tools = aggregate_used_tools(final_state.get("messages"))
            if used_tools:
                payload = {**result, "used_tools": used_tools}

        parsed = urlparse(callback_url)
        redacted_url = urlunparse(parsed._replace(query="", fragment=""))
        logger.info("Sending callback activity signal", callback_url=redacted_url, invocation_id=invocation_id)
        await WorkflowSignalClient.send_success_signal(callback_url, invocation_id, payload)

    # ===============================
    # Nodes
    # -------------------------------

    def _create_orchestrator_node(self) -> Callable[..., Coroutine[Any, Any, AgentState]]:
        async def _orchestrator_node(state: AgentState) -> AgentState:
            """Execute orchestrator agent node.

            Args:
                state: Current graph state

            Returns:
                Updated state with context integration and routing

            """
            orchestrator = OrchestratorAgent(self.context_manager)
            return await orchestrator.execute(state)

        return _orchestrator_node

    def _create_generic_agent_node(
        self, available_tools: list[BaseTool]
    ) -> Callable[..., Coroutine[Any, Any, AgentState]]:
        async def _generic_agent_node(state: AgentState) -> AgentState:
            """Execute generic agent node.

            Args:
                state: Current graph state

            Returns:
                State with generic agent result

            """
            # Use direct import
            agent_class = GenericAgent

            logger.info("Executing GenericAgent for invocation", invocation_id=state["invocation_id"])

            agent = agent_class(llm=self.llm, available_tools=available_tools)
            updated_state = await agent.execute_as_node(state)

            # Enhance result with context metadata if available
            self._enhance_result_with_context_metadata(updated_state)

            return updated_state

        return _generic_agent_node

    def _create_tool_node(
        self,
        tools: list[BaseTool],
        session_id: str,
        invocation_id: UUID,
        execution_id: UUID | None = None,
        request_id: UUID | None = None,
        activity_id: str | None = None,
        activity_name: str | None = None,
    ) -> ToolNode:
        """Create ToolNode with retry error handling for both sync and async tools."""
        # Get the current event loop to pass to sync wrapper for reliable tool disable operations
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        # Create ToolNode with both sync and async wrappers for comprehensive failure handling
        return ToolNode(
            tools,
            awrap_tool_call=create_tool_awrapper(
                session_id=session_id,
                invocation_id=invocation_id,
                execution_id=execution_id,
                request_id=request_id,
                activity_id=activity_id,
                activity_name=activity_name,
            ),
            wrap_tool_call=create_tool_wrapper(
                session_id=session_id,
                invocation_id=invocation_id,
                execution_id=execution_id,
                request_id=request_id,
                loop=loop,
                activity_id=activity_id,
                activity_name=activity_name,
            ),
        )

    # ===============================

    # ===============================
    # Conditional routing
    # -------------------------------

    def _route_after_orchestrator(self, state: AgentState) -> str:
        """Determine routing after orchestrator execution.

        Args:
            state: Current graph state after orchestrator

        Returns:
            Target agent route

        """
        return state["current_agent"]

    def _should_call_tools(self, state: AgentState) -> str:
        """Decide if we should continue the loop or stop based upon whether the LLM requires a tool call."""
        messages = state["messages"]
        last_message = messages[-1]

        # If the LLM needs a tool call, then route to our ToolNode
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return AgentRoutes.TOOLS

        # Otherwise, we stop (reply to the user)
        return END

    # ===============================

    def _enhance_result_with_context_metadata(self, state: AgentState) -> None:
        """Enhance AgentState with context metadata.

        Args:
            state: Current state with context information

        """
        # Add context enhancement metadata if available
        result = state.get("result")
        context_package = state.get("context_package")
        if result is not None and context_package is not None:
            result["grounding_score"] = context_package["grounding_score"]
            result["context_enhancement"] = {
                "turn_id": context_package["package_id"],  # Use turn_id as per API schema
                "citations": context_package["citations"],
                "context_applied": context_package["context_applied"],
            }
