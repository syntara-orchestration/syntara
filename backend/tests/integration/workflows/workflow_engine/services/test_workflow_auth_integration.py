"""Tests for Temporal workflow authorization against an embedded Temporal server.

Verifies that the worker-side auth interceptor rejects unauthorized
workflow submissions and allows authorized ones.
"""

import asyncio
from collections.abc import Callable
from uuid import uuid4

import pytest
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.activities.script_activity import execute_script_activity
from syntara.workflows.workflow_engine.client_interceptor import WorkflowAuthClientInterceptor
from syntara.workflows.workflow_engine.dynamic_workflow import NexusWorkflow
from syntara.workflows.workflow_engine.interceptors.auth_interceptor import WorkflowAuthInterceptor
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService
from syntara.workflows.workflow_engine.workflow_auth import build_auth_header, init_signing_key

TASK_QUEUE = "test-auth-queue"

_TEST_ACTIVITIES: list[Callable[..., object]] = [
    manual_trigger,
    execute_script_activity,
    fetch_workflow_runtime_settings,
]

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

            with pytest.raises(Exception, match="Unauthorized workflow execution"):
                await asyncio.wait_for(handle.result(), timeout=10)

    async def test_schedule_baked_auth_header_accepted(self, temporal_env: WorkflowEnvironment) -> None:
        """A workflow submitted with build_auth_header (schedule path) must execute."""
        init_signing_key()

        workflow_id = f"sched-auth-test-{uuid4()}"
        auth_headers = build_auth_header(workflow_id)

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
                id=workflow_id,
                task_queue=TASK_QUEUE,
                headers=dict(auth_headers.items()),
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
