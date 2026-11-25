"""Dispatch a prepared AO agent invocation to its isolated SDK workload."""

# Temporal ApplicationError messages are intentionally user-facing and typed.
# ruff: noqa: TRY003, EM101, EM102

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import structlog
from execution_plane_client.commands.bulk_work import WorkItemSelector
from execution_plane_client.commands.work import ResolvedExecution, WorkExecute, WorkloadInvocation
from execution_plane_client.models.work_item import WorkItemStatus
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError
from sqlmodel import col, select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.agent_orchestrator.agents.generic_agent import _default_task_agent_prompt
from syntara.agent_orchestrator.agents.orchestrator_agent import OrchestratorAgent
from syntara.agent_orchestrator.audit.agent_execution import AgentExecutionEvent, AgentExecutionStatus
from syntara.agent_orchestrator.models.agent_state import AgentStateFactory
from syntara.agent_orchestrator.services.streaming_service import get_invocation_stream_id
from syntara.agent_orchestrator.utils.context_helpers import extract_execution_id, extract_request_id
from syntara.agent_orchestrator.utils.token_usage import aggregate_token_usage
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.cache.stream import StreamClient
from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.execution_plane.client import (
    EP_AUDIENCE,
    EP_CLIENT_ID,
    ExecutionPlaneHttpClient,
    ExecutionPlaneRejectedError,
    ExecutionPlaneUnavailableError,
)
from syntara.execution_plane.registry.repository import (
    execution_plane_plugin_input_schema,
    execution_plane_plugin_supports_revision,
    get_execution_plane_plugin,
)
from syntara.execution_plane.utils import execution_plane_work_item_id
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.types import MetricType
from syntara.settings.cache.settings_cache import get_runtime_settings
from syntara.workflows.models.execution import Execution

logger = structlog.stdlib.get_logger(__name__)
_PLUGIN_NAME = "agent-runtime"
_STEP_IDENTITY = "syntara.agent-runtime.agent-runtime"
_MAX_MODEL_CALLS = 8


def _work_item_error(status: str, result: object) -> ApplicationError | None:
    """Translate terminal EP outcomes into non-retryable workflow failures."""
    if status not in {
        WorkItemStatus.FAILED.value,
        WorkItemStatus.CANCELLED.value,
        WorkItemStatus.RECONCILIATION_REQUIRED.value,
    }:
        return None

    value = result if isinstance(result, dict) else {}
    error_message = str(value.get("error", "Agent Runtime workload failed"))
    if status == WorkItemStatus.RECONCILIATION_REQUIRED.value:
        return ApplicationError(
            error_message,
            value,
            type="AgentRuntimeOutcomeUnknown",
            non_retryable=True,
        )

    error_type = str(value.get("error_type", "AgentRuntimeWorkFailed"))
    return ApplicationError(error_message, value, type=error_type, non_retryable=True)


if TYPE_CHECKING:
    from uuid import UUID

    from syntara.agent_orchestrator.models.context_data import InvocationContextData
    from syntara.agent_orchestrator.models.invocation import Invocation
    from syntara.agent_orchestrator.services.orchestration_service import OrchestrationService
    from syntara.audit.emitter import AuditActorContext


def container_runtime_enabled(ctx: InvocationContextData) -> bool:
    """Select the container backend only for workflow-backed invocations."""
    return bool(get_settings().agent_runtime_enabled and ctx.activity_id and extract_execution_id(ctx))


async def execute_container_agent(  # noqa: C901, PLR0912, PLR0915 -- preserves orchestration result, audit, and callback contracts.
    invocation: Invocation,
    orchestration: OrchestrationService,
    ctx: InvocationContextData,
    actor_context: AuditActorContext,
    response_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    """Prepare AO-owned context/tools, run one workload, and signal its result."""
    execution_id = extract_execution_id(ctx)
    if execution_id is None or not ctx.activity_id:
        raise ApplicationError("Agent Runtime requires a workflow activity context", non_retryable=True)

    initial_state = AgentStateFactory.create_initial_state(
        prompt=invocation.prompt,
        session_id=invocation.session_id,
        invocation_id=invocation.id,
        metadata=ctx.to_state_dict(),
        actor_context=actor_context,
        execution_id=execution_id,
        request_id=extract_request_id(ctx),
        response_schema=response_schema,
    )
    prepared_state = await OrchestratorAgent(orchestration.context_manager).execute(initial_state)
    tools = await orchestration._get_tools(  # noqa: SLF001 -- reuse AO's existing per-invocation tool authorization.
        invocation.session_id,
        invocation.id,
        execution_id=execution_id,
        request_id=extract_request_id(ctx),
        activity_id=ctx.activity_id,
        activity_name=ctx.activity_name,
    )
    tool_inputs: list[dict[str, Any]] = []
    for tool in tools:
        metadata = getattr(tool, "metadata", None) or {}
        handle = metadata.get("tool_id")
        if not isinstance(handle, str) or not handle:
            raise ApplicationError(
                "AO could not identify a selected MCP tool", type="AgentToolConfigError", non_retryable=True
            )
        args_schema = getattr(tool, "args_schema", None)
        schema_factory = getattr(args_schema, "model_json_schema", None)
        if callable(schema_factory):
            schema = schema_factory()
        elif isinstance(args_schema, dict):
            schema = args_schema
        else:
            schema = {"type": "object", "properties": {}}
        tool_inputs.append(
            {"handle": handle, "name": tool.name, "description": tool.description or "", "input_schema": schema}
        )

    runtime_settings = get_runtime_settings()
    system_prompt = await runtime_settings.get_str(
        "agentic.task_agent_system_prompt", default=_default_task_agent_prompt()
    )
    inputs = {
        "contract_version": 1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prepared_state["prompt"]},
        ],
        "tools": tool_inputs,
        "response_schema": response_schema,
        "max_model_calls": _MAX_MODEL_CALLS,
    }
    agent_started = asyncio.get_running_loop().time()
    AuditEventDispatcher.dispatch(
        AgentExecutionEvent(
            agent_type="generic_agent",
            session_id=invocation.session_id,
            invocation_id=invocation.id,
            execution_id=execution_id,
            request_id=extract_request_id(ctx),
            status=AgentExecutionStatus.STARTED,
        )
    )
    try:
        result = await _submit_and_wait(invocation, ctx, inputs)
        output = result.get("output")
        if not isinstance(output, dict) or not isinstance(output.get("content"), (str, dict)):
            message = "Agent Runtime returned an invalid result"
            raise ApplicationError(  # noqa: TRY301 -- invalid workload output is terminal and audited below.
                message, type="AgentRuntimeProtocolError", non_retryable=True
            )
    except Exception as error:
        duration_ms = (asyncio.get_running_loop().time() - agent_started) * 1000
        AuditEventDispatcher.dispatch(
            AgentExecutionEvent(
                agent_type="generic_agent",
                session_id=invocation.session_id,
                invocation_id=invocation.id,
                execution_id=execution_id,
                request_id=extract_request_id(ctx),
                status=AgentExecutionStatus.FAILED,
                error_type=type(error).__name__,
            )
        )
        get_metrics_recorder().record(
            MetricType.AGENT_INVOCATION_DURATION,
            duration_ms,
            unit="ms",
            labels={"agent_type": "GenericAgent", "invocation_id": str(invocation.id), "status": "error"},
        )
        raise
    duration_ms = (asyncio.get_running_loop().time() - agent_started) * 1000
    AuditEventDispatcher.dispatch(
        AgentExecutionEvent(
            agent_type="generic_agent",
            session_id=invocation.session_id,
            invocation_id=invocation.id,
            execution_id=execution_id,
            request_id=extract_request_id(ctx),
            status=AgentExecutionStatus.COMPLETED,
        )
    )
    get_metrics_recorder().record(
        MetricType.AGENT_INVOCATION_DURATION,
        duration_ms,
        unit="ms",
        labels={"agent_type": "GenericAgent", "invocation_id": str(invocation.id), "status": "success"},
    )

    trace_steps = output.get("tool_trace")
    if not isinstance(trace_steps, list):
        trace_steps = []
    now = datetime.now(UTC).isoformat()
    trace = [
        {**step, "timestamp": step.get("timestamp", now)}
        for step in trace_steps
        if isinstance(step, dict) and isinstance(step.get("type"), str)
    ]
    trace.append(
        {
            "type": "final_answer",
            "timestamp": now,
            "content": str(output["content"])[:5_000],
        }
    )
    usage_log = output.get("llm_token_usage_log")
    if not isinstance(usage_log, list):
        usage_log = []
    tools_used = output.get("tools_used")
    if not isinstance(tools_used, list):
        tools_used = []

    model_name = orchestration._get_model_name()  # noqa: SLF001 -- use the model metadata AO already exposes internally.
    response_metadata = output.get("response_metadata")
    if not isinstance(response_metadata, dict):
        response_metadata = {}
    result_dict: dict[str, Any] = {
        "type": "answer",
        "content": output["content"],
        "response_metadata": {
            **response_metadata,
            "source": "container",
            "model": model_name,
            "orchestration": "agent-runtime",
        },
        "structured_output_metadata": output.get("structured_output_metadata"),
        "agent_trace": {
            "model": model_name,
            "total_tokens": 0,
            "total_duration_ms": int(output.get("total_duration_ms", 0)),
            "steps": trace,
        },
        "tools_used": tools_used,
        "tool_calls": [],
        "llm_token_usage_log": usage_log,
    }
    if tools_used:
        result_dict["used_tools"] = [
            {"name": name, "count": tools_used.count(name)} for name in dict.fromkeys(tools_used)
        ]
    context_package = prepared_state.get("context_package")
    if context_package is not None:
        result_dict["grounding_score"] = context_package.get("grounding_score")
        result_dict["context_enhancement"] = {
            "turn_id": context_package.get("package_id"),
            "citations": context_package.get("citations", []),
            "context_applied": context_package.get("context_applied", True),
        }
    _prompt_tokens, _completion_tokens, total_tokens, _details = aggregate_token_usage(
        [entry for entry in usage_log if isinstance(entry, dict)]
    )
    result_dict["tokens_used"] = total_tokens
    result_dict["agent_trace"]["total_tokens"] = total_tokens
    result_dict["tool_calls"] = [
        {"tool_name": step.get("tool_name"), "status": step.get("status", "success")}
        for step in trace
        if step.get("type") == "tool_result"
    ]

    prepared_state["result"] = result_dict
    prepared_state["messages"] = []
    stream_id = get_invocation_stream_id(invocation.id)
    result_dict["response_metadata"]["stream_id"] = stream_id
    async with StreamClient() as stream_client:
        await orchestration._publish_completion_event(  # noqa: SLF001 -- preserve AO's established stream event shape.
            invocation.id, stream_id, stream_client
        )
    await orchestration._handle_completion_callback(  # noqa: SLF001 -- preserve the existing Temporal callback contract.
        prepared_state, invocation.id, ctx, signal_result=result_dict
    )
    return result_dict


async def _submit_and_wait(  # noqa: C901, PLR0912, PLR0915 -- keeps submit, recovery, polling, cancellation, and timeout handling together.
    invocation: Invocation, ctx: InvocationContextData, inputs: dict[str, Any]
) -> dict[str, Any]:
    """Submit one stable WorkExecute and poll its terminal outcome."""
    execution_id = extract_execution_id(ctx)
    if execution_id is None or not ctx.activity_id:
        raise ApplicationError("Agent Runtime requires an activity identity", non_retryable=True)
    work_item_id = execution_plane_work_item_id(execution_id, ctx.activity_id)
    settings = get_settings()
    timeout_seconds = max(1, int(ctx.timeout_seconds or 300))
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    async with AsyncSessionLocal() as session:
        plugin = await get_execution_plane_plugin(session, _PLUGIN_NAME)
        if plugin is None or plugin.step_identity != _STEP_IDENTITY:
            raise ApplicationError(
                "Agent Runtime Action is not registered in AO", type="AgentRuntimeConfigError", non_retryable=True
            )
        image = plugin.image_reference
        try:
            resolved_execution_model = ResolvedExecution.model_validate(plugin.resolved_execution)
        except PydanticValidationError as error:
            raise ApplicationError(
                "Agent Runtime compiled binding is missing or inconsistent in AO",
                type="AgentRuntimeConfigError",
                non_retryable=True,
            ) from error
        resolved_bindings = resolved_execution_model.bindings
        if (
            len(resolved_bindings) != 1
            or resolved_bindings[0].step_identity != plugin.step_identity
            or not execution_plane_plugin_supports_revision(plugin, resolved_bindings[0].step_revision_id)
        ):
            raise ApplicationError(
                "Agent Runtime compiled binding is missing or inconsistent in AO",
                type="AgentRuntimeConfigError",
                non_retryable=True,
            )
        step_revision_id = resolved_bindings[0].step_revision_id
        try:
            Draft202012Validator(execution_plane_plugin_input_schema(plugin)).validate(inputs)
        except (ValueError, JsonSchemaValidationError) as error:
            raise ApplicationError(
                f"Agent Runtime input is invalid: {error}", type="AgentRuntimeConfigError", non_retryable=True
            ) from None

    runtime_context = await _runtime_context(execution_id, invocation.id)
    required_invocation_fields = {"host_operations", "resolved_execution"}
    if not required_invocation_fields.issubset(WorkloadInvocation.model_fields):
        raise ApplicationError(
            "Agent Runtime requires an execution-plane-client build with host operations and resolved execution",
            type="AgentRuntimeConfigError",
            non_retryable=True,
        )
    invocation_payload = WorkloadInvocation(
        step_revision_id=step_revision_id,
        inputs=inputs,
        host_operations=["agent.model.turn", "agent.mcp.call"],
        resolved_execution=resolved_execution_model,
        timeout_seconds=timeout_seconds,
    )
    command = WorkExecute(
        work_item_id=work_item_id,
        runtime_context=runtime_context,
        invocation=invocation_payload,
        image=image,
    ).to_message(source_id=EP_CLIENT_ID, destination_id=EP_AUDIENCE, client_id=EP_CLIENT_ID)

    try:
        async with ExecutionPlaneHttpClient(
            timeout=min(settings.ep_request_timeout_seconds, timeout_seconds)
        ) as client:
            try:
                receipt = await client.submit_command(command)
                if (
                    receipt.resource is None
                    or receipt.resource.kind != "work_item"
                    or receipt.resource.resource_id != work_item_id
                ):
                    raise ApplicationError(
                        "Execution Plane returned an invalid work receipt",
                        type="AgentRuntimeProtocolError",
                        non_retryable=True,
                    )
            except ExecutionPlaneRejectedError as rejection:
                if rejection.status_code != HTTPStatus.CONFLICT:
                    raise
            while asyncio.get_running_loop().time() < deadline:
                work = await client.get_work_item(work_item_id=work_item_id)
                status = str(work.get("status", ""))
                if status == WorkItemStatus.COMPLETED.value:
                    value = work.get("result")
                    return value if isinstance(value, dict) else {}
                work_item_error = _work_item_error(status, work.get("result"))
                if work_item_error is not None:
                    raise work_item_error
                activity.heartbeat({"agent_runtime_work_item_id": str(work_item_id), "status": status})
                await asyncio.sleep(min(1.0, max(0.0, deadline - asyncio.get_running_loop().time())))
            with suppress(Exception):
                await client.cancel_work_items(selector=WorkItemSelector(work_item_ids=[work_item_id]))
            raise ApplicationError(
                "Agent Runtime exceeded the step timeout", type="AgentRuntimeTimeout", non_retryable=True
            )
    except ExecutionPlaneUnavailableError as error:
        raise ApplicationError(
            "Execution Plane is unavailable", type="ExecutionPlaneUnavailable", non_retryable=True
        ) from error
    except asyncio.CancelledError:
        with suppress(Exception):
            async with ExecutionPlaneHttpClient(timeout=settings.ep_request_timeout_seconds) as client:
                await client.cancel_work_items(selector=WorkItemSelector(work_item_ids=[work_item_id]))
        raise


async def _runtime_context(execution_id: UUID, invocation_id: UUID) -> dict[str, object]:
    """Attach trusted non-secret correlation values to the EP work item."""
    async with AsyncSessionLocal() as session:
        row = (
            await session.exec(
                select(Execution.project_id, Execution.workflow_id).where(col(Execution.id) == execution_id)
            )
        ).first()
    if row is None:
        raise ApplicationError(
            "Workflow execution no longer exists", type="AgentRuntimeContextError", non_retryable=True
        )
    return {
        "execution_id": str(execution_id),
        "project_id": str(row[0]),
        "workflow_id": str(row[1]),
        "agent_invocation_id": str(invocation_id),
    }
