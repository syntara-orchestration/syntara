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
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from syntara.workflows.workflow_engine.activities.converge import converge
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

_expire_calls: list[tuple[str, str | None]] = []


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
    loop_iteration_path: list[int] | None = None,
    temporal_activity_id: str | None = None,
    prompt: str | None = None,
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
    node_id: str | None = None,
) -> dict[str, Any]:
    """Test expire activity that records calls for assertion."""
    _expire_calls.append((execution_id, node_id))
    return {"expired_count": 1}


@activity.defn(name=ActivityName.APPROVAL)
async def _test_multi_approval_activity(
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
    loop_iteration_path: list[int] | None = None,
    temporal_activity_id: str | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    """Approval activity where only one of two approval nodes ever gets a decision.

    ``approval_slow`` never resolves, simulating the bug scenario where a second
    approval branch is left outstanding when the workflow completes via the
    other (decided) branch.
    """
    if approval_node_id == "approval_slow":
        await asyncio.sleep(3600)
        return {"output": {}}
    return {"output": {"decision": "approved", "decided_by": "tester", "decided_at": "2026-01-01T00:00:00Z"}}


def _create_multi_approval_workflow_yaml() -> dict[str, Any]:
    workflow_yaml = """
schema_version: "2.0.0"
name: multi-approval-completion-test
description: Integration test - other pending approvals expire on workflow completion
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: approval_fast
  type: approval
  parameters:
    name: Fast Approval
    decision_window: 60
- id: approval_slow
  type: approval
  parameters:
    name: Slow Approval
    decision_window: 60
- id: converge_node
  type: converge
  parameters:
    strategy: any
    n_required: 1
- id: post_converge
  type: script
  parameters:
    language: python
    code: "print('done')"
edges:
- from: trigger_manual
  to: approval_fast
- from: trigger_manual
  to: approval_slow
- from: approval_fast
  to: converge_node
  from_port: approved
- from: approval_slow
  to: converge_node
  from_port: approved
- from: converge_node
  to: post_converge
"""
    result: dict[str, Any] = yaml.safe_load(workflow_yaml)
    return result


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
            workflows=[OrchestratorWorkflow],
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
            workflows=[OrchestratorWorkflow],
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

    async def test_other_pending_approval_expired_on_workflow_completion(
        self, temporal_env: WorkflowEnvironment
    ) -> None:
        """A second approval branch left pending is expired once the workflow completes.

        Reproduces the reported bug: two approval nodes converge with an ANY
        strategy, only one is decided, and the workflow completes normally
        while the other approval is still outstanding. It must be expired
        rather than left in "pending" forever, and its underlying Temporal
        activity must be resolved rather than left dangling.
        """
        task_queue = "multi-approval-completion-queue"
        _expire_calls.clear()

        from syntara.workflows.workflow_engine.activities.approval_activity import fail_detached_approval_activity
        from syntara.workflows.workflow_engine.services.activity_sync_registry import (
            get_activity_sync_service,
            set_activity_sync_service,
        )
        from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

        # fail_detached_approval_activity is a local activity invoked by direct function
        # reference from the workflow, so it can't be swapped out via Worker registration
        # like EXPIRE_APPROVAL. Instead, stub the ActivitySyncService's temporal_client so
        # the real activity runs but talks to a mock instead of issuing a real async-activity
        # completion RPC (unsupported by the time-skipping test environment).
        mock_handle = AsyncMock()
        mock_temporal_client = MagicMock()
        mock_temporal_client.get_async_activity_handle.return_value = mock_handle
        mock_sync_service = MagicMock()
        mock_sync_service.temporal_client = mock_temporal_client
        original_sync_service = get_activity_sync_service()
        set_activity_sync_service(mock_sync_service)

        try:
            async with Worker(
                temporal_env.client,
                task_queue=task_queue,
                workflows=[OrchestratorWorkflow],
                activities=[
                    manual_trigger,
                    _test_multi_approval_activity,
                    _test_expire_approval_activity,
                    _test_script_activity,
                    fetch_workflow_runtime_settings,
                    fail_detached_approval_activity,
                    converge,
                ],
            ):
                execution_service = TemporalExecutionService(
                    temporal_client=temporal_env.client,
                    task_queue=task_queue,
                )

                workflow_def = _create_multi_approval_workflow_yaml()

                result = await execution_service.start_workflow(
                    workflow_def=workflow_def,
                    workflow_name="multi-approval-completion-test",
                    trigger_node_id="trigger_manual",
                )

                handle = execution_service.temporal_client.get_workflow_handle(
                    result.temporal_workflow_id, run_id=result.temporal_run_id
                )
                workflow_result = await asyncio.wait_for(handle.result(), timeout=30)

                assert workflow_result["status"] == "completed"
                # The still-pending "approval_slow" branch is swept up by the execution-wide
                # expire call (node_id=None) issued when the workflow reaches completion.
                assert len(_expire_calls) == 1
                called_execution_id, called_node_id = _expire_calls[0]
                assert called_node_id is None
                assert called_execution_id is not None

                # The detached branch's underlying Temporal activity is also resolved,
                # rather than left dangling until its own start_to_close_timeout.
                mock_temporal_client.get_async_activity_handle.assert_called_once()
                handle_call_kwargs = mock_temporal_client.get_async_activity_handle.call_args.kwargs
                assert handle_call_kwargs["workflow_id"] == result.temporal_workflow_id
                assert handle_call_kwargs["activity_id"] == "approval_slow"
                mock_handle.fail.assert_called_once()
        finally:
            set_activity_sync_service(original_sync_service)
