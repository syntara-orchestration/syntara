"""Tool execution failure retry and auto-disable logic for FR-009 compliance.

This module provides retry policy configuration and failure handling for LangGraph
ToolNode integration. Uses LangGraph's built-in retry_policy instead of custom retry
mechanisms for proper integration with StateGraph execution.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from langchain_core.messages.tool import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from syntara.agent_orchestrator.audit.tool_management import ToolInvocationEvent, ToolInvocationStatus
from syntara.agent_orchestrator.tool_manager.tool_services import _get_tool_manager_client
from syntara.agent_orchestrator.utils import retry_with_backoff
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.models.principal import make_service_user
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.types import MetricType
from syntara.telemetry.events.tool_execution import ToolExecutedEvent
from syntara.tool_manager.models.tool import ToolStatus
from syntara.tool_manager.models.tool_execution import ToolExecutionStatus
from syntara.tool_manager.services.tool_metrics_service import ToolMetricsService

logger = structlog.stdlib.get_logger(__name__)

# Constants
MAX_ERROR_MESSAGE_LENGTH = 500


def _create_error_tool_message(error: Exception, tool_call_id: str, tool_name: str) -> ToolMessage:
    """Create a standardized error ToolMessage.

    Args:
        error: The exception that occurred during tool execution
        tool_call_id: ID of the tool call that failed
        tool_name: Name of the tool that failed

    Returns:
        ToolMessage containing the error information

    """
    return ToolMessage(
        content=f"Tool execution failed: {error.__class__.__name__}: {error!s}",
        tool_call_id=tool_call_id,
        name=tool_name,
        status="error",
    )


def _extract_tool_id_from_metadata(base_tool: Any, tool_name: str) -> UUID | None:  # noqa: ANN401
    """Extract and validate tool_id from BaseTool metadata.

    Args:
        base_tool: The BaseTool instance
        tool_name: Name of the tool for logging

    Returns:
        UUID if valid tool_id found, None otherwise

    """
    if not base_tool or not hasattr(base_tool, "metadata") or not isinstance(base_tool.metadata, dict):
        logger.error("BaseTool missing metadata - this indicates a bug in tool synchronization", tool_name=tool_name)
        return None

    tool_id_value = base_tool.metadata.get("tool_id")
    if not tool_id_value:
        logger.error(
            "BaseTool metadata missing tool_id - this indicates a bug in tool synchronization",
            tool_name=tool_name,
        )
        return None

    try:
        tool_id = UUID(str(tool_id_value))
        logger.debug("Extracted tool_id from metadata", tool_id=tool_id)
        return tool_id
    except (ValueError, TypeError):
        logger.exception(
            "Invalid tool_id format in metadata - this indicates a bug in tool synchronization",
            tool_name=tool_name,
            tool_id_value=tool_id_value,
        )
        return None


def _resolve_execution_status(error: Exception | None) -> ToolExecutionStatus:
    """Map an exception to a ToolExecutionStatus.

    Args:
        error: The exception from tool execution, or None for success.

    Returns:
        ToolExecutionStatus.TIMEOUT for TimeoutError, ERROR for other exceptions, SUCCESS otherwise.

    """
    if error is None:
        return ToolExecutionStatus.SUCCESS
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return ToolExecutionStatus.TIMEOUT
    return ToolExecutionStatus.ERROR


def _emit_tool_metrics(
    base_tool: Any,  # noqa: ANN401
    duration_ms: float,
    status: ToolExecutionStatus,
    error: Exception | None = None,
) -> None:
    """Emit tool execution metrics to MetricsRecorder (best-effort).

    Args:
        base_tool: The BaseTool instance with metadata.
        duration_ms: Execution duration in milliseconds.
        status: Resolved execution status.
        error: Optional exception for error_code labeling.

    """
    try:
        recorder = get_metrics_recorder()
        metadata = base_tool.metadata
        integration_id = metadata.get("integration_id", "unknown")
        labels: dict[str, str] = {
            "namespaced_name": metadata["namespaced_name"],
            "status": status.value,
            "integration_id": integration_id,
            "tool_id": metadata.get("tool_id", "unknown"),
            "error_code": type(error).__name__ if error is not None else "none",
        }
        recorder.record(MetricType.TOOL_EXECUTION_DURATION, duration_ms, unit="ms", labels=labels)
        recorder.record(MetricType.TOOL_EXECUTION_STATUS, 1.0, labels=labels)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to emit tool execution metrics", exc_info=True)


async def _persist_tool_execution_to_db(
    base_tool: Any,  # noqa: ANN401
    duration_ms: float,
    status: ToolExecutionStatus,
    error_message: str | None = None,
    session_factory: Callable[[], Any] = AsyncSessionLocal,
) -> None:
    """Persist a tool execution record to the database (best-effort).

    Opens its own DB session since this runs outside FastAPI request context.
    Uses the worker's service principal for audit fields.

    Args:
        base_tool: The BaseTool instance with metadata containing namespaced_name.
        duration_ms: Execution duration in milliseconds.
        status: Resolved execution status.
        error_message: Error description for failed executions.
        session_factory: Injectable async session maker for database access.

    """
    try:
        namespaced_name: str = base_tool.metadata["namespaced_name"]
        svc_user = make_service_user(get_settings().service_identity)
        async with session_factory() as session:
            try:
                service = ToolMetricsService(session, svc_user)
                await service.record_tool_execution(
                    namespaced_name=namespaced_name,
                    duration_ms=int(duration_ms),
                    status=status,
                    error_message=error_message,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    except Exception:  # noqa: BLE001
        logger.warning("Failed to persist tool execution to DB", exc_info=True)


# ---------------------------------------------------------------------------
# Shared bookkeeping helpers for async/sync tool wrappers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ToolInvocationContext:
    """Shared audit and telemetry parameters for tool invocation wrappers."""

    session_id: str
    invocation_id: UUID
    execution_id: UUID | None
    request_id: UUID | None
    activity_id: str | None
    activity_name: str | None


def _emit_start_audit(
    ctx: _ToolInvocationContext,
    tool_name: str,
    tool_input: dict[str, Any],
) -> None:
    """Emit STARTED audit event for a tool invocation."""
    _emit_tool_invocation_audit(
        tool_name=tool_name,
        status=ToolInvocationStatus.STARTED,
        session_id=ctx.session_id,
        invocation_id=ctx.invocation_id,
        execution_id=ctx.execution_id,
        request_id=ctx.request_id,
        tool_input=tool_input,
        activity_id=ctx.activity_id,
        activity_name=ctx.activity_name,
    )


def _emit_success_audit(
    ctx: _ToolInvocationContext,
    tool_name: str,
    result: ToolMessage | Command[Any],
) -> None:
    """Emit COMPLETED audit event for a successful tool invocation."""
    tool_output = str(result.content) if hasattr(result, "content") else str(result)
    _emit_tool_invocation_audit(
        tool_name=tool_name,
        status=ToolInvocationStatus.COMPLETED,
        session_id=ctx.session_id,
        invocation_id=ctx.invocation_id,
        execution_id=ctx.execution_id,
        request_id=ctx.request_id,
        tool_output=tool_output,
        activity_id=ctx.activity_id,
        activity_name=ctx.activity_name,
    )


def _handle_tool_execution_error(
    ctx: _ToolInvocationContext,
    request: ToolCallRequest,
    error: Exception,
) -> tuple[UUID | None, ToolMessage]:
    """Handle common error bookkeeping for tool execution failure.

    Emits the FAILED audit event, logs the exception, extracts the tool_id
    from metadata, and creates a standardized error ToolMessage.

    Args:
        ctx: Shared invocation context for audit correlation.
        request: The original tool call request.
        error: The exception raised during execution.

    Returns:
        Tuple of (tool_id, error_message). tool_id is None when metadata
        is missing or invalid. Callers use tool_id to disable the tool.

    """
    tool_name = request.tool_call["name"]
    tool_call_id = request.tool_call["id"]

    _emit_tool_invocation_audit(
        tool_name=tool_name,
        status=ToolInvocationStatus.FAILED,
        session_id=ctx.session_id,
        invocation_id=ctx.invocation_id,
        execution_id=ctx.execution_id,
        request_id=ctx.request_id,
        error_type=error.__class__.__name__,
        activity_id=ctx.activity_id,
        activity_name=ctx.activity_name,
    )

    logger.exception("Tool execution failed during wrapped call", tool_name=tool_name)

    tool_id = _extract_tool_id_from_metadata(request.tool, tool_name)
    error_msg = _create_error_tool_message(error, tool_call_id or "unknown", tool_name)

    return tool_id, error_msg


def _extract_namespaced_name(tool: Any) -> str:  # noqa: ANN401
    """Extract namespaced_name from tool metadata, defaulting to empty string."""
    if tool and hasattr(tool, "metadata") and isinstance(tool.metadata, dict):
        name: str = tool.metadata.get("namespaced_name", "")
        return name
    return ""


def _finalize_tool_execution(
    request: ToolCallRequest,
    start_time: float,
    caught_error: Exception | None,
    execution_id: UUID | None,
) -> tuple[int, ToolExecutionStatus]:
    """Emit metrics and telemetry for a completed tool execution.

    Computes duration and status, emits MetricsRecorder metrics, and dispatches
    the ToolExecutedEvent audit event. Database persistence is left to the caller
    because the async/sync bridging differs.

    Args:
        request: The original tool call request (provides tool metadata).
        start_time: ``time.perf_counter()`` value captured before execution.
        caught_error: The exception from execution, or None on success.
        execution_id: Parent workflow execution ID for telemetry.

    Returns:
        Tuple of (duration_ms, status) for the caller's DB persistence step.

    """
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    status = _resolve_execution_status(caught_error)
    namespaced_name = _extract_namespaced_name(request.tool)
    _emit_tool_metrics(request.tool, duration_ms, status, error=caught_error)
    AuditEventDispatcher.dispatch(
        ToolExecutedEvent(
            namespaced_name=namespaced_name,
            status=status,
            duration_ms=int(duration_ms),
            execution_id=execution_id,
        )
    )
    return duration_ms, status


def create_tool_awrapper(
    session_id: str,
    invocation_id: UUID,
    execution_id: UUID | None = None,
    request_id: UUID | None = None,
    activity_id: str | None = None,
    activity_name: str | None = None,
) -> Callable[
    [ToolCallRequest, Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]]],
    Awaitable[ToolMessage | Command[Any]],
]:
    """Create an async tool call wrapper that handles failures with tool context.

    This wrapper intercepts tool execution, provides access to the actual BaseTool,
    and handles failures with proper tool auto-disable functionality.

    Args:
        session_id: Session identifier for multi-tenant isolation
        invocation_id: Invocation UUID for audit correlation
        execution_id: Optional parent workflow execution ID for telemetry
        request_id: Optional X-Request-Id from the originating HTTP request.
        activity_id: Optional activity identifier from workflow context
        activity_name: Optional activity name from workflow context

    Returns:
        An async ToolCallWrapper function for use with ToolNode awrap_tool_call

    """
    ctx = _ToolInvocationContext(
        session_id=session_id,
        invocation_id=invocation_id,
        execution_id=execution_id,
        request_id=request_id,
        activity_id=activity_id,
        activity_name=activity_name,
    )

    @retry_with_backoff
    async def _execute(
        request: ToolCallRequest, execute: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]]
    ) -> ToolMessage | Command[Any]:
        # Execute async function
        return await execute(request)

    async def tool_awrapper(
        request: ToolCallRequest,
        execute: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """Execute tools and handle failures asynchronously.

        Args:
            request: ToolCallRequest containing tool info and arguments
            execute: Original async tool execution function

        Returns:
            ToolMessage or Command result from tool execution

        """
        start_time = time.perf_counter()
        caught_error: Exception | None = None
        tool_name = request.tool_call["name"]
        tool_input = request.tool_call.get("args", {})

        _emit_start_audit(ctx, tool_name, tool_input)

        try:
            result = await _execute(request, execute)
            _emit_success_audit(ctx, tool_name, result)
            return result
        except Exception as error:  # noqa: BLE001 - logged inside _handle_tool_execution_error
            caught_error = error
            tool_id, error_msg = _handle_tool_execution_error(ctx, request, error)
            if tool_id is not None:
                await _disable_tool_by_id(tool_id, error)
            return error_msg
        finally:
            duration_ms, status = _finalize_tool_execution(request, start_time, caught_error, execution_id)
            await _persist_tool_execution_to_db(
                request.tool,
                duration_ms,
                status,
                error_message=str(caught_error) if caught_error else None,
            )

    return tool_awrapper


def create_tool_wrapper(
    session_id: str,
    invocation_id: UUID,
    execution_id: UUID | None = None,
    request_id: UUID | None = None,
    activity_id: str | None = None,
    activity_name: str | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> Callable[[ToolCallRequest, Callable[[ToolCallRequest], ToolMessage | Command[Any]]], ToolMessage | Command[Any]]:
    """Create a synchronous tool call wrapper that handles failures with tool context.

    This wrapper intercepts tool execution, provides access to the actual BaseTool,
    and handles failures with proper tool auto-disable functionality for synchronous tools.

    Args:
        session_id: Session identifier for multi-tenant isolation
        invocation_id: Optional invocation UUID for audit correlation
        execution_id: Optional parent workflow execution ID for telemetry
        request_id: Optional X-Request-Id from the originating HTTP request.
        activity_id: Optional activity identifier from workflow context
        activity_name: Optional activity name from workflow context
        loop: Optional event loop to use for tool disable operations

    Returns:
        A sync ToolCallWrapper function for use with ToolNode wrap_tool_call

    """
    ctx = _ToolInvocationContext(
        session_id=session_id,
        invocation_id=invocation_id,
        execution_id=execution_id,
        request_id=request_id,
        activity_id=activity_id,
        activity_name=activity_name,
    )

    def _execute_sync(
        request: ToolCallRequest, execute: Callable[[ToolCallRequest], ToolMessage | Command[Any]]
    ) -> ToolMessage | Command[Any]:
        """Execute synchronous tool with retry logic."""
        # For sync tools, we use a simplified retry approach
        # since we can't use the async retry_with_backoff decorator
        settings = get_settings()
        max_retries = settings.adapter_max_retries

        for attempt in range(max_retries + 1):
            try:
                return execute(request)
            except Exception:
                if attempt < max_retries:
                    # Simple exponential backoff for sync retry
                    backoff_time = settings.adapter_initial_backoff_seconds * (
                        settings.adapter_backoff_growth_factor**attempt
                    )
                    backoff_time = min(backoff_time, settings.adapter_max_backoff_seconds)
                    time.sleep(backoff_time)
                    continue
                # Final attempt failed, re-raise the error
                raise

        # This should never be reached, but satisfy type checker
        unexpected_end_msg = "Unexpected end of retry loop"
        raise RuntimeError(unexpected_end_msg)

    def tool_wrapper(
        request: ToolCallRequest, execute: Callable[[ToolCallRequest], ToolMessage | Command[Any]]
    ) -> ToolMessage | Command[Any]:
        """Execute tools and handle failures synchronously.

        Args:
            request: ToolCallRequest containing tool info and arguments
            execute: Original sync tool execution function

        Returns:
            ToolMessage result from tool execution

        """
        start_time = time.perf_counter()
        caught_error: Exception | None = None
        tool_name = request.tool_call["name"]
        tool_input = request.tool_call.get("args", {})

        _emit_start_audit(ctx, tool_name, tool_input)

        try:
            result = _execute_sync(request, execute)
            _emit_success_audit(ctx, tool_name, result)
            return result
        except Exception as error:  # noqa: BLE001 - logged inside _handle_tool_execution_error
            caught_error = error
            tool_id, error_msg = _handle_tool_execution_error(ctx, request, error)
            if tool_id is not None:
                _run_coroutine_from_sync(_disable_tool_by_id(tool_id, error), loop, "tool auto-disable")
            return error_msg
        finally:
            duration_ms, status = _finalize_tool_execution(request, start_time, caught_error, execution_id)
            _run_coroutine_from_sync(
                _persist_tool_execution_to_db(
                    request.tool,
                    duration_ms,
                    status,
                    error_message=str(caught_error) if caught_error else None,
                ),
                loop,
                "tool execution DB persistence",
            )

    return tool_wrapper


def _emit_tool_invocation_audit(
    tool_name: str,
    status: ToolInvocationStatus,
    session_id: str,
    invocation_id: UUID,
    execution_id: UUID | None,
    request_id: UUID | None,
    tool_input: dict[str, Any] | None = None,
    tool_output: str | None = None,
    error_type: str | None = None,
    activity_id: str | None = None,
    activity_name: str | None = None,
) -> None:
    """Emit tool invocation audit event if invocation_id is available.

    Args:
        tool_name: Name of the tool being invoked
        status: Tool invocation status
        session_id: Session identifier for multi-tenant isolation
        invocation_id: Invocation UUID for audit correlation (required)
        execution_id: Optional parent workflow execution ID
        request_id: Optional X-Request-Id from the originating HTTP request.
        tool_input: Optional tool input parameters
        tool_output: Optional tool output
        error_type: Optional error type for failed invocations
        activity_id: Optional activity identifier from workflow context
        activity_name: Optional activity name from workflow context

    """
    AuditEventDispatcher.dispatch(
        ToolInvocationEvent(
            tool_name=tool_name,
            status=status,
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=execution_id,
            request_id=request_id,
            tool_input=tool_input,
            tool_output=tool_output,
            error_type=error_type,
            activity_id=activity_id,
            activity_name=activity_name,
        )
    )


def _run_coroutine_from_sync(
    coro: Awaitable[Any],
    loop: asyncio.AbstractEventLoop | None,
    description: str,
) -> None:
    """Run an async coroutine from a synchronous context (best-effort).

    Uses the provided event loop if available, otherwise falls back to ``asyncio.run``.

    Args:
        coro: The coroutine to execute.
        loop: Optional running event loop for ``run_coroutine_threadsafe``.
        description: Human-readable label used in warning log messages on failure.

    """
    if loop:
        try:
            _ = asyncio.run_coroutine_threadsafe(coro, loop)  # type: ignore[arg-type]
        except RuntimeError:
            logger.warning("Failed to schedule %s on provided event loop", description)
    else:
        try:
            asyncio.run(coro)  # type: ignore[arg-type]
        except RuntimeError as e:
            logger.warning("Failed to run %s (no event loop)", description, details=str(e))


async def _disable_tool_by_id(tool_id: UUID, error: Exception) -> None:
    """Disable tool by ID after failure.

    This method directly disables the tool using the Tool Manager API.

    Args:
        tool_id: ID of the tool to disable
        error: The exception that caused the failure

    """
    try:
        async with _get_tool_manager_client() as client:
            error_message = f"Tool execution failed: {error.__class__.__name__}: {error!s}"
            if len(error_message) > MAX_ERROR_MESSAGE_LENGTH:
                error_message = error_message[:497] + "..."

            await client.update_tool_status(
                tool_id=tool_id,
                status=ToolStatus.ERROR,
                refresh_error=error_message,
            )

            logger.info("Successfully auto-disabled failed tool", tool_id=tool_id)

    except Exception:
        logger.exception(
            "Failed to auto-disable tool after execution failure",
            tool_id=tool_id,
            error=f"{error.__class__.__name__}: {error!s}",
        )
