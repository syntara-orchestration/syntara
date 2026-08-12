"""Internal activity executor for built-in operations.

Dispatches to registered internal operations (document conversion,
invocation execution) that run directly in the Temporal worker
process via native Temporal activities.

Heavy dependencies (InvocationExecutor, DocumentConversionTask) are
imported lazily inside the dispatch functions to avoid pulling them
into the worker process at startup — eager imports trigger Temporal
sandbox warnings that can interfere with other activities.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any, TypedDict
from uuid import UUID

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

import structlog
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

logger = structlog.stdlib.get_logger(__name__)


class InvocationExecutionInput(TypedDict):
    """Wire format for the Agent Execution builtin workflow input."""

    invocation_id: str
    actor_id: str
    actor_username: str | None
    actor_type: str | None


async def _run_document_conversion(operation_input: dict[str, Any]) -> dict[str, Any]:
    file_id = operation_input.get("file_id")
    if not file_id:
        msg = "document_conversion requires 'file_id'"
        raise ApplicationError(msg, non_retryable=True)

    from syntara.files.document_conversion.tasks import DocumentConversionTask  # noqa: PLC0415

    task = DocumentConversionTask()
    result = await task.convert(UUID(file_id))
    return {"output": {"status": result.name}}


async def _run_invocation_execution(operation_input: InvocationExecutionInput) -> dict[str, Any]:
    invocation_id = operation_input.get("invocation_id")
    if not invocation_id:
        msg = "invocation_execution requires 'invocation_id'"
        raise ApplicationError(msg, non_retryable=True)

    from syntara.agent_orchestrator.executor.invocation_executor import InvocationExecutor  # noqa: PLC0415
    from syntara.audit.emitter import AuditActorContext  # noqa: PLC0415
    from syntara.core.models.principal import PrincipalType  # noqa: PLC0415

    actor_context: AuditActorContext | None = None
    if actor_id := operation_input.get("actor_id"):
        actor_type = operation_input.get("actor_type")
        actor_context = AuditActorContext(
            actor_id=UUID(actor_id),
            actor_username=operation_input.get("actor_username"),
            actor_type=PrincipalType(actor_type) if actor_type else None,
        )

    executor = InvocationExecutor()
    await executor.execute_invocation(UUID(invocation_id), actor_context=actor_context)
    return {"output": {"status": "completed"}}


async def _run_integration_health_check(operation_input: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Run health checks on all integrations due for validation (batch mode)."""
    # Batch mode only: operation_input is reserved for a future single-integration path.
    from syntara.integrations.services.health_check import run_health_checks  # noqa: PLC0415

    result = await run_health_checks()
    return {"output": asdict(result)}


async def _run_integration_resource_discovery(operation_input: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Discover and sync resources for all integrations due for discovery (batch mode)."""
    # Batch mode only: operation_input is reserved for a future single-integration path.
    from syntara.integrations.services.resource_discovery import run_resource_discovery  # noqa: PLC0415

    result = await run_resource_discovery()
    return {"output": asdict(result)}


_DISPATCH: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "document_conversion": _run_document_conversion,
    "invocation_execution": _run_invocation_execution,
    "integration_health_check": _run_integration_health_check,
    "integration_resource_discovery": _run_integration_resource_discovery,
}


@activity.defn(name=ActivityName.INTERNAL_ACTIVITY)
async def execute_internal_activity(
    input_config: dict[str, Any],
    _output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Execute an internal system operation.

    Args:
        input_config: Must contain ``activity`` (operation name) and ``input`` (operation params).
        _output_config: Output mapping (unused, kept for dispatch compatibility).

    """
    operation_name = input_config.get("activity")
    if not operation_name:
        msg = "internal_activity node requires 'activity' in config"
        raise ApplicationError(msg, non_retryable=True)

    handler = _DISPATCH.get(operation_name)
    if handler is None:
        msg = f"Unknown internal activity: {operation_name}"
        raise ApplicationError(msg, non_retryable=True)

    operation_input = input_config.get("input", {})
    logger.info("Executing internal activity", operation=operation_name, input_keys=list(operation_input.keys()))

    result: dict[str, Any] = await handler(operation_input)
    return result
