"""Integration test for approval node timeout and expiry.

Tests the workflow-level handling of approval node timeout using Temporal's
time-skipping test environment. Uses a test-friendly approval activity that
sleeps past the decision window (instead of raise_complete_async) because the
time-skipping test server does not support async activity completion RPCs.

When the approval activity times out, the workflow must call the expire
activity to batch-expire pending approval requests via the Approvals API.
"""

import asyncio
from typing import Any

import pytest
import yaml
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.dynamic_workflow import NexusWorkflow
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

_expire_calls: list[tuple[str, str]] = []


@activity.defn(name=ActivityName.APPROVAL)
async def _test_approval_activity(
    execution_id: str,
    approval_node_id: str,
    name: str,
    next_step_approved: dict[str, Any] | None,
    workflow_context: dict[str, Any],
    timeout_at: str | None = None,
    next_step_rejected: dict[str, Any] | None = None,
    approver_user_ids: list[str] | None = None,
    approver_group_ids: list[str] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Test approval activity that blocks until Temporal times it out.

    Sleeps long enough for the start_to_close_timeout to fire, simulating
    a decision window expiry without needing raise_complete_async.
    """
    await asyncio.sleep(3600)
    return {"output": {}}


@activity.defn(name=ActivityName.EXPIRE_APPROVAL)
async def _test_expire_approval_activity(
    execution_id: str,
    node_id: str,
) -> dict[str, Any]:
    """Test expire activity that records calls for assertion."""
    _expire_calls.append((execution_id, node_id))
    return {"expired_count": 1}


def _create_approval_workflow_yaml(decision_window: int = 5) -> dict[str, Any]:
    workflow_yaml = f"""
schema_version: "2.0.0"
name: approval-timeout-test
description: Integration test for approval timeout and expiry
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: approval_node
  type: approval
  parameters:
    name: Test Approval
    decision_window: {decision_window}
    fallback_decision: reject
- id: next_step
  type: script
  parameters:
    language: python
    code: "print('approved')"
edges:
- from: trigger_manual
  to: approval_node
- from: approval_node
  to: next_step
  from_port: approved
"""
    result: dict[str, Any] = yaml.safe_load(workflow_yaml)
    return result


@activity.defn(name=ActivityName.SCRIPT)
async def _test_script_activity(
    resolved_parameters: dict[str, Any],
    outputs: dict[str, str] | None = None,
    **kwargs: object,
) -> dict[str, Any]:
    return {"output": {"status": "completed"}}


def _create_approval_cof_workflow_yaml(
    decision_window: int = 5,
    fallback_decision: str = "reject",
) -> dict[str, Any]:
    workflow_yaml = f"""
schema_version: "2.0.0"
name: approval-cof-test
description: Integration test for approval timeout with continue_on_failure
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: approval_node
  type: approval
  parameters:
    name: Test Approval
    decision_window: {decision_window}
    fallback_decision: {fallback_decision}
  settings:
    continue_on_failure: true
- id: approved_step
  type: script
  parameters:
    language: python
    code: "print('approved')"
- id: rejected_step
  type: script
  parameters:
    language: python
    code: "print('rejected')"
edges:
- from: trigger_manual
  to: approval_node
- from: approval_node
  to: approved_step
  from_port: approved
- from: approval_node
  to: rejected_step
  from_port: rejected
"""
    result: dict[str, Any] = yaml.safe_load(workflow_yaml)
    return result


@pytest.mark.integration
@pytest.mark.asyncio
class TestApprovalTimeoutIntegration:
    """Integration tests for approval node timeout triggering expiry."""

    async def test_approval_timeout_triggers_expire_activity(self, temporal_env: WorkflowEnvironment) -> None:
        """When approval times out, expire activity is called with correct args."""
        task_queue = "approval-timeout-queue"
        _expire_calls.clear()

        from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

        async with Worker(
            temporal_env.client,
            task_queue=task_queue,
            workflows=[NexusWorkflow],
            activities=[
                manual_trigger,
                _test_approval_activity,
                _test_expire_approval_activity,
                _test_script_activity,
                fetch_workflow_runtime_settings,
            ],
        ):
            execution_service = TemporalExecutionService(
                temporal_client=temporal_env.client,
                task_queue=task_queue,
            )

            workflow_def = _create_approval_workflow_yaml(decision_window=1)

            result = await execution_service.start_workflow(
                workflow_def=workflow_def,
                workflow_name="approval-timeout-test",
                trigger_node_id="trigger_manual",
            )

            handle = execution_service.temporal_client.get_workflow_handle(
                result.temporal_workflow_id, run_id=result.temporal_run_id
            )
            workflow_result = await asyncio.wait_for(handle.result(), timeout=30)

            assert workflow_result["status"] == "failed"
            assert len(_expire_calls) == 1
            execution_id_called, node_id_called = _expire_calls[0]
            assert node_id_called == "approval_node"
            assert execution_id_called is not None

    @pytest.mark.parametrize("fallback_decision", ["reject", "approve"])
    async def test_approval_timeout_with_cof_routes_via_fallback(
        self, temporal_env: WorkflowEnvironment, fallback_decision: str
    ) -> None:
        """When approval times out with continue_on_failure, workflow continues via fallback port."""
        task_queue = f"approval-cof-{fallback_decision}-queue"
        _expire_calls.clear()

        from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

        async with Worker(
            temporal_env.client,
            task_queue=task_queue,
            workflows=[NexusWorkflow],
            activities=[
                manual_trigger,
                _test_approval_activity,
                _test_expire_approval_activity,
                _test_script_activity,
                fetch_workflow_runtime_settings,
            ],
        ):
            execution_service = TemporalExecutionService(
                temporal_client=temporal_env.client,
                task_queue=task_queue,
            )

            workflow_def = _create_approval_cof_workflow_yaml(
                decision_window=1,
                fallback_decision=fallback_decision,
            )

            result = await execution_service.start_workflow(
                workflow_def=workflow_def,
                workflow_name=f"approval-cof-{fallback_decision}-test",
                trigger_node_id="trigger_manual",
            )

            handle = execution_service.temporal_client.get_workflow_handle(
                result.temporal_workflow_id, run_id=result.temporal_run_id
            )
            workflow_result = await asyncio.wait_for(handle.result(), timeout=30)

            # Workflow completes with errors: approval node failed but CoF absorbed it
            assert workflow_result["status"] == "completed_with_errors"
            # Expire activity should still be called
            assert len(_expire_calls) == 1
            assert _expire_calls[0][1] == "approval_node"
