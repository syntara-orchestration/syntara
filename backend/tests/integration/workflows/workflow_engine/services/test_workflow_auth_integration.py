"""Tests for Temporal workflow authorization against an embedded Temporal server.

Verifies that the worker-side auth interceptor rejects unauthorized
workflow submissions and allows authorized ones.
"""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from temporalio import activity
from temporalio.client import (
    Client,
    Interceptor,
    OutboundInterceptor,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleIntervalSpec,
    ScheduleSpec,
    StartWorkflowInput,
)
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from syntara.workflows.utils.schedule_parser import build_schedule_execution_workflow_id
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.activities.script_activity import execute_script_activity
from syntara.workflows.workflow_engine.client_interceptor import WorkflowAuthClientInterceptor
from syntara.workflows.workflow_engine.dynamic_workflow import NexusWorkflow
from syntara.workflows.workflow_engine.interceptors.auth_interceptor import WorkflowAuthInterceptor
from syntara.workflows.workflow_engine.scheduled_launcher import ScheduledWorkflowLauncher
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService
from syntara.workflows.workflow_engine.workflow_auth import build_auth_header, init_signing_key

TASK_QUEUE = "test-auth-queue"


class _FixedHeaderInterceptor(Interceptor):
    """Test interceptor that injects pre-built auth headers (simulates the schedule path)."""

    def __init__(self, headers: dict[str, Any]) -> None:
        self._headers = headers

    def intercept_client(self, next: OutboundInterceptor) -> OutboundInterceptor:  # noqa: A002
        headers = self._headers

        class _Outbound(OutboundInterceptor):
            async def start_workflow(self, input: StartWorkflowInput) -> Any:  # noqa: A002, ANN401
                merged = dict(input.headers)
                merged.update(headers)
                input.headers = merged
                return await super().start_workflow(input)

        return _Outbound(next)


_TEST_ACTIVITIES: list[Callable[..., object]] = [
    manual_trigger,
    execute_script_activity,
    fetch_workflow_runtime_settings,
]

_SCHEDULE_TEST_ACTIVITIES: list[Callable[..., object]] = list(_TEST_ACTIVITIES)


@activity.defn(name="setup_scheduled_execution")
async def stub_setup_scheduled_execution(workflow_id_str: str, trigger_node_id: str) -> dict[str, Any]:
    """Stub DB setup for schedule launcher integration tests."""
    execution_id = str(uuid4())
    return {
        "execution_id": execution_id,
        "temporal_workflow_id": f"sched-child-{execution_id}",
        "workflow_definition": SIMPLE_WORKFLOW,
        "input_data": {},
        "task_queue": TASK_QUEUE,
        "workflow_metadata": TEST_WORKFLOW_METADATA,
    }


_SCHEDULE_TEST_ACTIVITIES.append(stub_setup_scheduled_execution)

SIMPLE_WORKFLOW = {
    "schema_version": "2.0.0",
    "name": "auth-test",
    "triggers": [{"id": "trigger_manual", "type": "manual_trigger"}],
    "nodes": [
        {
            "id": "task1",
            "type": "script",
            "parameters": {"language": "bash", "code": "echo ok"},
            "settings": {"timeout": 1},
        },
    ],
    "edges": [{"from": "trigger_manual", "to": "task1"}],
}

TEST_WORKFLOW_METADATA = {
    "workflow_context": {"workflow": {"project_id": str(uuid4())}},
}


@pytest.mark.asyncio
class TestWorkflowAuthIntegration:
    """End-to-end auth interceptor tests against an embedded Temporal server."""

    async def test_unauthorized_workflow_rejected(self, temporal_env: WorkflowEnvironment) -> None:
        """A workflow submitted without HMAC header must be rejected."""
        init_signing_key()

        async with Worker(
            temporal_env.client,
            task_queue=TASK_QUEUE,
            workflows=[NexusWorkflow],
            activities=_TEST_ACTIVITIES,
            interceptors=[WorkflowAuthInterceptor()],
        ):
            handle = await temporal_env.client.start_workflow(
                "orchestrator_workflow",
                args=[
                    SIMPLE_WORKFLOW,
                    str(uuid4()),
                    "trigger_manual",
                    {},
                    False,
                    None,
                    None,
                    None,
                    TEST_WORKFLOW_METADATA,
                ],
                id=f"unauth-test-{uuid4()}",
                task_queue=TASK_QUEUE,
            )

            with pytest.raises(Exception, match="Workflow execution failed") as exc_info:
                await asyncio.wait_for(handle.result(), timeout=10)
            assert "Unauthorized" in str(exc_info.value.__cause__)

    async def test_create_schedule_fire_accepted_with_timestamp_suffix(
        self,
        temporal_env: WorkflowEnvironment,
    ) -> None:
        """A real Temporal Schedule fire must pass auth when the workflow ID has a time suffix."""
        init_signing_key()

        wf_id = str(uuid4())
        trigger_id = "trigger_manual"
        exec_id = build_schedule_execution_workflow_id(wf_id, trigger_id)
        launcher_args: list[str] = [wf_id, trigger_id]
        action = ScheduleActionStartWorkflow(
            "scheduled_workflow_launcher",
            args=launcher_args,
            id=exec_id,
            task_queue=TASK_QUEUE,
        )
        action.headers = build_auth_header(exec_id, "scheduled_workflow_launcher", launcher_args)

        schedule_id = f"auth-sched-test-{uuid4()}"
        schedule_handle = await temporal_env.client.create_schedule(
            schedule_id,
            Schedule(
                action=action,
                spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(seconds=1))]),
            ),
        )

        try:
            async with Worker(
                temporal_env.client,
                task_queue=TASK_QUEUE,
                workflows=[ScheduledWorkflowLauncher, NexusWorkflow],
                activities=_SCHEDULE_TEST_ACTIVITIES,
                interceptors=[WorkflowAuthInterceptor()],
            ):
                fired_workflow_id: str | None = None
                for _ in range(60):
                    desc = await schedule_handle.describe()
                    if desc.info.recent_actions:
                        fired_workflow_id = desc.info.recent_actions[-1].action.workflow_id
                        break
                    await asyncio.sleep(1)

                assert fired_workflow_id is not None, "schedule did not fire within timeout"
                assert fired_workflow_id.startswith(f"{exec_id}-"), (
                    f"expected Temporal timestamp suffix on {fired_workflow_id}"
                )

                launcher_handle = temporal_env.client.get_workflow_handle(fired_workflow_id)
                launcher_result = await asyncio.wait_for(launcher_handle.result(), timeout=60)
                assert "execution_id" in launcher_result
        finally:
            await schedule_handle.delete()

    async def test_schedule_baked_auth_header_accepted(self, temporal_env: WorkflowEnvironment) -> None:
        """A workflow submitted with build_auth_header (schedule path) must execute."""
        init_signing_key()

        workflow_id = f"sched-auth-test-{uuid4()}"
        workflow_args: list[object] = [
            SIMPLE_WORKFLOW,
            str(uuid4()),
            "trigger_manual",
            {},
            False,
            None,
            None,
            None,
            TEST_WORKFLOW_METADATA,
        ]
        auth_headers = build_auth_header(workflow_id, "orchestrator_workflow", workflow_args)

        header_client = await Client.connect(
            temporal_env.client.service_client.config.target_host,
            namespace=temporal_env.client.namespace,
            interceptors=[_FixedHeaderInterceptor(auth_headers)],
        )

        async with Worker(
            temporal_env.client,
            task_queue=TASK_QUEUE,
            workflows=[NexusWorkflow],
            activities=_TEST_ACTIVITIES,
            interceptors=[WorkflowAuthInterceptor()],
        ):
            handle = await header_client.start_workflow(
                "orchestrator_workflow",
                args=workflow_args,
                id=workflow_id,
                task_queue=TASK_QUEUE,
            )

            workflow_result = await asyncio.wait_for(handle.result(), timeout=30)
            assert workflow_result["status"] == "completed"

    async def test_authorized_workflow_succeeds(self, temporal_env: WorkflowEnvironment) -> None:
        """A workflow submitted with valid HMAC header must execute."""
        init_signing_key()

        authed_client = await Client.connect(
            temporal_env.client.service_client.config.target_host,
            namespace=temporal_env.client.namespace,
            interceptors=[WorkflowAuthClientInterceptor()],
        )

        async with Worker(
            temporal_env.client,
            task_queue=TASK_QUEUE,
            workflows=[NexusWorkflow],
            activities=_TEST_ACTIVITIES,
            interceptors=[WorkflowAuthInterceptor()],
        ):
            service = TemporalExecutionService(
                temporal_client=authed_client,
                task_queue=TASK_QUEUE,
            )

            result = await service.start_workflow(
                workflow_def=SIMPLE_WORKFLOW,
                workflow_name="auth-test",
                trigger_node_id="trigger_manual",
                workflow_metadata=TEST_WORKFLOW_METADATA,
            )

            handle = authed_client.get_workflow_handle(result.temporal_workflow_id, run_id=result.temporal_run_id)
            workflow_result = await asyncio.wait_for(handle.result(), timeout=30)
            assert workflow_result["status"] == "completed"
