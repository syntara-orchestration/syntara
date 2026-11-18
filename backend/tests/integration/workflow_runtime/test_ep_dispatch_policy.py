"""Verify EP retry and asynchronous completion deadlines with a Temporal server."""

from typing import Any
from uuid import uuid4

import pytest
from temporalio import activity, workflow
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from syntara.workflow_core.graph import ActivityNode
from syntara.workflow_core.models import NodeType
from syntara.workflow_runtime.engines.temporal.dynamic_workflow import OrchestratorWorkflow
from syntara.workflow_runtime.engines.temporal.execution_plane_policy import EP_POLICY_SNAPSHOT_KEY


@workflow.defn
class EPPolicyWorkflow:
    """Exercise the production EP scheduling path without database dependencies."""

    @workflow.run
    async def run(self, mode: str, ep_dispatch_max_retries: int) -> dict[str, Any]:
        orchestrator = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
        orchestrator._runtime_settings = {
            EP_POLICY_SNAPSHOT_KEY: {
                "ep_dispatch_max_retries": ep_dispatch_max_retries,
                "ep_dispatch_initial_backoff_seconds": 0.1,
                "ep_dispatch_max_backoff_seconds": 0.1,
                "ep_work_timeout_seconds": 3,
            }
        }
        orchestrator._active_ep_nodes = set()
        node = ActivityNode("script", NodeType.SCRIPT_BASH, {})
        return await orchestrator._execute_executor_node(node, node.type, {"mode": mode}, None, timeout_seconds=1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "ep_dispatch_max_retries", "expected_attempts", "error_type"),
    [
        ("transient", 2, [1, 2, 3], None),
        ("exhausted", 1, [1, 2], "ExecutionPlaneUnavailable"),
        ("exhausted", 0, [1], "ExecutionPlaneUnavailable"),
        ("terminal", 5, [1], "ScriptExecutionError"),
        ("accepted", 5, [1], "ExecutionPlaneWorkTimeout"),
        ("accepted_after_retry", 5, [1, 2], "ExecutionPlaneWorkTimeout"),
    ],
)
async def test_ep_activity_retry_and_completion_deadline(
    mode: str, ep_dispatch_max_retries: int, expected_attempts: list[int], error_type: str | None
) -> None:
    attempts: list[int] = []

    @activity.defn(name="execute_bash_script_activity")
    async def fake_dispatch(_input_config: dict[str, Any], _output_config: dict[str, str] | None) -> dict[str, Any]:
        attempt = activity.info().attempt
        attempts.append(attempt)
        if mode == "terminal":
            message = "Automation failed"
            raise ApplicationError(message, type="ScriptExecutionError", non_retryable=True)
        if (
            mode == "exhausted"
            or (mode == "transient" and attempt < 3)
            or (mode == "accepted_after_retry" and attempt == 1)
        ):
            message = "EP unavailable"
            raise ApplicationError(message, type="ExecutionPlaneUnavailable")
        if mode in {"accepted", "accepted_after_retry"}:
            activity.raise_complete_async()
        return {"output": {"ok": True}}

    async with await WorkflowEnvironment.start_time_skipping() as env:
        queue = f"ep-policy-{uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[EPPolicyWorkflow],
            activities=[fake_dispatch],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            if error_type is None:
                result = await env.client.execute_workflow(
                    EPPolicyWorkflow.run, args=[mode, ep_dispatch_max_retries], id=str(uuid4()), task_queue=queue
                )
                assert result == {"output": {"ok": True}}
            else:
                with pytest.raises(WorkflowFailureError) as exc_info:
                    await env.client.execute_workflow(
                        EPPolicyWorkflow.run, args=[mode, ep_dispatch_max_retries], id=str(uuid4()), task_queue=queue
                    )
                failure = exc_info.value.cause
                if error_type == "ExecutionPlaneWorkTimeout":
                    assert isinstance(failure, ApplicationError)
                    assert failure.type == error_type
                    assert failure.non_retryable is True
                    assert "3 seconds" in failure.message
                else:
                    assert isinstance(failure, ActivityError)
                    assert isinstance(failure.cause, ApplicationError)
                    assert failure.cause.type == error_type
    assert attempts == expected_attempts
