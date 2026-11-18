"""Dispatch accepts commands; only EP callbacks resolve script activities."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Self, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from execution_plane_client.commands.control import CompletionStatus
from execution_plane_client.commands.results import TransportReceipt
from execution_plane_client.protocol import MessageEnvelope, ResourceReference
from temporalio import activity, workflow
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from syntara.execution_plane.client import ExecutionPlaneRejectedError, ExecutionPlaneUnavailableError
from syntara.execution_plane.commands import completion
from syntara.execution_plane.commands.completion import CompletionCommandHandler
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.workflow_core.models import ActivityName, NodeType
from syntara.workflow_runtime.engines.temporal.activities.ep import ep_dispatch_activity as dispatch
from syntara.workflow_runtime.engines.temporal.execution_plane_policy import build_ep_retry_policy
from syntara.workflow_runtime.engines.temporal.services.temporal_execution_service import TemporalExecutionService


@workflow.defn
class ScriptCallbackWorkflow:
    """Keep the actual script activity open until the callback arrives."""

    @workflow.run
    async def run(self, execution_id: str) -> dict[str, Any]:
        return cast(
            "dict[str, Any]",
            await workflow.execute_activity(
                ActivityName.SCRIPT_BASH,
                args=[{"code": ":"}, None, execution_id],
                activity_id="script",
                schedule_to_close_timeout=timedelta(seconds=10),
                retry_policy=build_ep_retry_policy({"ep_dispatch_initial_backoff_seconds": 1}),
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["accepted", "duplicate", "lost_response"])
@pytest.mark.parametrize("outcome", [CompletionStatus.COMPLETED, CompletionStatus.FAILED])
async def test_script_result_is_delivered_only_by_callback(
    mode: str, outcome: CompletionStatus, monkeypatch: pytest.MonkeyPatch
) -> None:
    submitted = asyncio.Event()
    messages: list[MessageEnvelope] = []

    class ReceiptOnlyClient:
        def __init__(self, *, timeout: float) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_: object) -> None:
            pass

        async def submit_command(self, message: MessageEnvelope) -> TransportReceipt:
            messages.append(message)
            if mode == "lost_response" and activity.info().attempt == 1:
                raise ExecutionPlaneUnavailableError
            submitted.set()
            if mode in {"duplicate", "lost_response"}:
                raise ExecutionPlaneRejectedError(status_code=409)
            return TransportReceipt(
                message_id=message.message_id,
                resource=ResourceReference(
                    kind="work_item", resource_id=UUID(str(message.command.payload["work_item_id"]))
                ),
            )

    monkeypatch.setattr(dispatch, "ExecutionPlaneHttpClient", ReceiptOnlyClient)
    monkeypatch.setattr(dispatch, "AsyncSessionLocal", MagicMock(return_value=AsyncMock()))
    monkeypatch.setattr(dispatch, "_work_runtime_context", AsyncMock(return_value={}))
    plugin = SimpleNamespace(
        name="script-bash",
        image_reference="example/script:test",
        step_identity="syntara.script-bash.script-bash",
        manifest={
            "spec": {
                "input": {
                    "kind": "inline",
                    "value": {"type": "object", "required": ["code"], "properties": {"code": {"type": "string"}}},
                },
                "output": {
                    "kind": "inline",
                    "value": {"type": "object", "required": ["stdout"], "properties": {"stdout": {"type": "string"}}},
                },
            }
        },
    )
    monkeypatch.setattr(dispatch, "get_execution_plane_plugin", AsyncMock(return_value=plugin))
    monkeypatch.setattr(completion, "get_execution_plane_plugin_by_node_type", AsyncMock(return_value=plugin))
    monkeypatch.setattr(
        dispatch,
        "get_settings",
        lambda: SimpleNamespace(script_nodes_enabled=True, ep_request_timeout_seconds=10, ep_api_url="https://ep.test"),
    )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        queue = str(uuid4())
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[ScriptCallbackWorkflow],
            activities=[dispatch.execute_bash_script_activity],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            with env.auto_time_skipping_disabled():
                handle = await env.client.start_workflow(
                    ScriptCallbackWorkflow.run, str(uuid4()), id=str(uuid4()), task_queue=queue
                )
                await asyncio.wait_for(submitted.wait(), timeout=5)
                session = AsyncMock()
                session.exec.return_value = MagicMock()
                session.exec.return_value.first.return_value = (handle.id, "script", NodeType.SCRIPT_BASH)
                result: dict[str, Any] = (
                    {"output": {"stdout": "callback"}}
                    if outcome == CompletionStatus.COMPLETED
                    else {"error": "automation failed", "error_type": "ScriptExecutionError"}
                )
                await CompletionCommandHandler()._complete_activity(
                    context=AOCommandContext(session, TemporalExecutionService(env.client, queue)),
                    work_id=UUID(str(messages[0].command.payload["work_item_id"])),
                    status=outcome,
                    result=result,
                )
                if outcome == CompletionStatus.COMPLETED:
                    assert await asyncio.wait_for(handle.result(), timeout=5) == result
                else:
                    with pytest.raises(WorkflowFailureError) as exc_info:
                        await asyncio.wait_for(handle.result(), timeout=5)
                    assert isinstance(exc_info.value.cause, ActivityError)
                    assert isinstance(exc_info.value.cause.cause, ApplicationError)
                    assert exc_info.value.cause.cause.type == "ScriptExecutionError"
                    assert exc_info.value.cause.cause.non_retryable is True
                assert len(messages) == (2 if mode == "lost_response" else 1)
                assert all(message.command.payload == messages[0].command.payload for message in messages)
