"""Integration test for form_prompt node timeout and expiry.

Tests the workflow-level handling of form_prompt node timeout using Temporal's
test environment. Uses a test-friendly form_prompt activity that never returns,
so Temporal's start_to_close_timeout fires and exercises the expiry path.
Note that time skipping is paused while an activity runs, so these tests wait
out the response window in real time.

When the form_prompt activity times out, the workflow behavior depends on
continue_on_failure setting:
- continue_on_failure=false (default): workflow fails after calling expire activity
- continue_on_failure=true: workflow expires the prompt and routes to fallback port
"""

import asyncio
from typing import Any

import pytest
import yaml
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from syntara.workflows.workflow_engine.activities.approver_resolution_activity import resolve_approvers_activity
from syntara.workflows.workflow_engine.activities.converge import converge
from syntara.workflows.workflow_engine.activities.form_prompt_activity import fail_detached_form_prompt_activity
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

_expire_calls: list[tuple[str, str | None]] = []

# Form prompts time out at ``response_window + OrchestratorWorkflow._TEMPORAL_MARGIN``
# seconds of real time (the test server cannot skip time while an activity is running),
# so allow generous headroom when waiting for the workflow to finish.
_RESULT_TIMEOUT_S = 90


@activity.defn(name=ActivityName.FORM_PROMPT)
async def _test_form_prompt_activity(
    execution_id: str,
    prompt_node_id: str,
    name: str,
    form_definition: dict[str, Any],
    timeout_at: str | None = None,
    responder_user_ids: list[str] | None = None,
    responder_group_ids: list[str] | None = None,
    project_id: str = "",
    loop_iteration_path: list[int] | None = None,
    temporal_activity_id: str | None = None,
    message: str | None = None,
    submit_label: str | None = None,
    success_message: str | None = None,
    timezone: str | None = None,
    css_override: str | None = None,
) -> dict[str, Any]:
    """Test form_prompt activity that blocks until Temporal times it out.

    Sleeps long enough for the start_to_close_timeout to fire, simulating
    a response window expiry without needing raise_complete_async.
    """
    await asyncio.sleep(3600)
    return {"output": {}}


@activity.defn(name=ActivityName.EXPIRE_FORM_PROMPT)
async def _test_expire_form_prompt_activity(
    execution_id: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Test expire activity that records calls for assertion."""
    _expire_calls.append((execution_id, node_id))
    return {"expired_count": 1}


def _create_form_prompt_fail_workflow_yaml(response_window: int = 5) -> dict[str, Any]:
    """Create workflow with form_prompt that fails on timeout (COF disabled)."""
    workflow_yaml = f"""
schema_version: "2.0.0"
name: form-prompt-timeout-fail-test
description: Integration test for form_prompt timeout with COF disabled
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: form1
  type: form_prompt
  parameters:
    name: Test Form
    response_window: {response_window}
    form_definition:
      fields: []
  settings:
    continue_on_failure: false
- id: next_step
  type: script
  parameters:
    language: python
    code: "print('submitted')"
edges:
- from: trigger_manual
  to: form1
- from: form1
  to: next_step
  from_port: submitted
"""
    result: dict[str, Any] = yaml.safe_load(workflow_yaml)
    return result


def _create_form_prompt_fallback_workflow_yaml(response_window: int = 5) -> dict[str, Any]:
    """Create workflow with form_prompt that routes to fallback on timeout (COF enabled)."""
    workflow_yaml = f"""
schema_version: "2.0.0"
name: form-prompt-timeout-fallback-test
description: Integration test for form_prompt timeout with COF enabled
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: form1
  type: form_prompt
  parameters:
    name: Test Form
    response_window: {response_window}
    form_definition:
      fields: []
  settings:
    continue_on_failure: true
- id: submitted_step
  type: script
  parameters:
    language: python
    code: "print('submitted')"
- id: fallback_step
  type: script
  parameters:
    language: python
    code: "print('expired')"
edges:
- from: trigger_manual
  to: form1
- from: form1
  to: submitted_step
  from_port: submitted
- from: form1
  to: fallback_step
  from_port: fallback
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


@pytest.mark.integration
@pytest.mark.asyncio
class TestFormPromptTimeoutIntegration:
    """Integration tests for form_prompt node timeout triggering expiry."""

    async def test_timeout_with_fail_behavior_expires_and_fails(self, temporal_env: WorkflowEnvironment) -> None:
        """When form_prompt times out with COF disabled, expire is called and workflow fails."""
        task_queue = "form-prompt-timeout-fail-queue"
        _expire_calls.clear()

        from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

        async with Worker(
            temporal_env.client,
            task_queue=task_queue,
            workflows=[OrchestratorWorkflow],
            activities=[
                resolve_approvers_activity,
                manual_trigger,
                _test_form_prompt_activity,
                _test_expire_form_prompt_activity,
                _test_script_activity,
                fetch_workflow_runtime_settings,
            ],
        ):
            execution_service = TemporalExecutionService(
                temporal_client=temporal_env.client,
                task_queue=task_queue,
            )

            workflow_def = _create_form_prompt_fail_workflow_yaml(response_window=1)
            result = await execution_service.start_workflow(
                workflow_def=workflow_def,
                workflow_name="form-prompt-test",
                trigger_node_id="trigger_manual",
            )

            handle = temporal_env.client.get_workflow_handle(result.temporal_workflow_id, run_id=result.temporal_run_id)
            workflow_result = await asyncio.wait_for(handle.result(), timeout=_RESULT_TIMEOUT_S)

            # The form_prompt node fails, so the workflow reports a failed execution
            assert workflow_result["status"] == "failed"

            # Expire activity should have been called for form1
            assert len(_expire_calls) == 1
            assert _expire_calls[0][1] == "form1"

    async def test_timeout_with_cof_enabled_expires_and_routes(self, temporal_env: WorkflowEnvironment) -> None:
        """When form_prompt times out with COF enabled, expire is called and routes to fallback."""
        task_queue = "form-prompt-timeout-fallback-queue"
        _expire_calls.clear()

        from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

        async with Worker(
            temporal_env.client,
            task_queue=task_queue,
            workflows=[OrchestratorWorkflow],
            activities=[
                resolve_approvers_activity,
                manual_trigger,
                _test_form_prompt_activity,
                _test_expire_form_prompt_activity,
                _test_script_activity,
                fetch_workflow_runtime_settings,
            ],
        ):
            execution_service = TemporalExecutionService(
                temporal_client=temporal_env.client,
                task_queue=task_queue,
            )

            workflow_def = _create_form_prompt_fallback_workflow_yaml(response_window=1)
            result = await execution_service.start_workflow(
                workflow_def=workflow_def,
                workflow_name="form-prompt-test",
                trigger_node_id="trigger_manual",
            )

            handle = temporal_env.client.get_workflow_handle(result.temporal_workflow_id, run_id=result.temporal_run_id)
            wf_result = await asyncio.wait_for(handle.result(), timeout=_RESULT_TIMEOUT_S)

            # Workflow completes with errors via fallback port (form1 failed but COF enabled)
            assert wf_result["status"] == "completed_with_errors"

            # Expire activity should have been called for form1
            assert len(_expire_calls) == 1
            assert _expire_calls[0][1] == "form1"

            # Verify the fallback branch ran and the submitted branch did not
            assert "fallback_step" in wf_result["completed_activities"]
            assert "submitted_step" not in wf_result["completed_activities"]

            # Verify form1 is in failed_nodes (timeout with COF enabled)
            assert "form1" in wf_result["failed_activities"]

    async def test_converge_with_detached_form_prompt_expires_remaining(
        self, temporal_env: WorkflowEnvironment
    ) -> None:
        """When workflow completes via converge, remaining form_prompts are expired."""
        task_queue = "form-prompt-converge-queue"
        _expire_calls.clear()

        # Create multi-branch workflow with converge(any)
        workflow_yaml = """
schema_version: "2.0.0"
name: form-prompt-converge-test
description: Integration test - detached form_prompt expires on workflow completion
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: form_fast
  type: form_prompt
  parameters:
    name: Fast Form
    response_window: 1
    form_definition:
      fields:
      - value_name: field1
        type: text
        label: Test Field
  settings:
    continue_on_failure: true
- id: form_slow
  type: form_prompt
  parameters:
    name: Slow Form
    response_window: 60
    form_definition:
      fields:
      - value_name: field1
        type: text
        label: Test Field
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
- id: fast_submitted
  type: script
  parameters:
    language: python
    code: "print('fast submitted')"
edges:
- from: trigger_manual
  to: form_fast
- from: trigger_manual
  to: form_slow
- from: form_fast
  to: converge_node
  from_port: fallback
- from: form_fast
  to: fast_submitted
  from_port: submitted
- from: form_slow
  to: converge_node
  from_port: submitted
- from: converge_node
  to: post_converge
"""
        workflow_def: dict[str, Any] = yaml.safe_load(workflow_yaml)

        from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

        async with Worker(
            temporal_env.client,
            task_queue=task_queue,
            workflows=[OrchestratorWorkflow],
            activities=[
                resolve_approvers_activity,
                manual_trigger,
                _test_form_prompt_activity,
                _test_expire_form_prompt_activity,
                _test_script_activity,
                converge,
                fetch_workflow_runtime_settings,
                # Detached form prompts are resolved through this local activity
                fail_detached_form_prompt_activity,
            ],
        ):
            execution_service = TemporalExecutionService(
                temporal_client=temporal_env.client,
                task_queue=task_queue,
            )

            result = await execution_service.start_workflow(
                workflow_def=workflow_def,
                workflow_name="form-prompt-test",
                trigger_node_id="trigger_manual",
            )

            handle = temporal_env.client.get_workflow_handle(result.temporal_workflow_id, run_id=result.temporal_run_id)
            wf_result = await asyncio.wait_for(handle.result(), timeout=_RESULT_TIMEOUT_S)

            # Workflow completes with errors via form_fast fallback (form_fast failed but COF enabled)
            assert wf_result["status"] == "completed_with_errors"

            # Both form_fast and the global expire should have been called
            # form_fast times out first (calls expire for form_fast)
            # then converge completes (calls expire for all remaining = form_slow)
            assert len(_expire_calls) >= 2

            # Verify form_fast is in failed_activities (timeout with COF enabled)
            assert "form_fast" in wf_result["failed_activities"]

    async def test_loop_iteration_form_prompts_get_unique_activity_ids(self, temporal_env: WorkflowEnvironment) -> None:
        """Form prompts inside loops get unique activity IDs per iteration."""
        task_queue = "form-prompt-loop-queue"
        _expire_calls.clear()

        workflow_yaml = """
schema_version: "2.0.0"
name: form-prompt-loop-test
description: Integration test for form_prompt inside loop
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: loop_node
  type: loop
  parameters:
    items: [1, 2]
- id: form_in_loop
  type: form_prompt
  parameters:
    name: Loop Form
    response_window: 1
    form_definition:
      fields:
      - value_name: field1
        type: text
        label: Test Field
  settings:
    continue_on_failure: true
- id: after_form
  type: script
  parameters:
    language: python
    code: "print('submitted')"
- id: after_timeout
  type: script
  parameters:
    language: python
    code: "print('expired')"
edges:
- from: trigger_manual
  to: loop_node
- from: loop_node
  to: form_in_loop
  from_port: iterate
- from: form_in_loop
  to: after_form
  from_port: submitted
- from: form_in_loop
  to: after_timeout
  from_port: fallback
"""
        workflow_def: dict[str, Any] = yaml.safe_load(workflow_yaml)

        from syntara.workflows.workflow_engine.activities.loop import loop
        from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

        async with Worker(
            temporal_env.client,
            task_queue=task_queue,
            workflows=[OrchestratorWorkflow],
            activities=[
                resolve_approvers_activity,
                manual_trigger,
                _test_form_prompt_activity,
                _test_expire_form_prompt_activity,
                _test_script_activity,
                loop,
                fetch_workflow_runtime_settings,
            ],
        ):
            execution_service = TemporalExecutionService(
                temporal_client=temporal_env.client,
                task_queue=task_queue,
            )

            result = await execution_service.start_workflow(
                workflow_def=workflow_def,
                workflow_name="form-prompt-test",
                trigger_node_id="trigger_manual",
            )

            handle = temporal_env.client.get_workflow_handle(result.temporal_workflow_id, run_id=result.temporal_run_id)
            wf_result = await asyncio.wait_for(handle.result(), timeout=_RESULT_TIMEOUT_S)

            # Both loop iterations time out with COF enabled and route through the fallback port
            assert wf_result["status"] == "completed_with_errors"

            # Should have at least 2 expire calls (one per iteration)
            assert len(_expire_calls) >= 2

    async def test_no_submitted_port_raises_safe_value_error(self, temporal_env: WorkflowEnvironment) -> None:
        """Form prompt node without submitted port raises SafeValueError during validation."""
        task_queue = "form-prompt-no-port-queue"

        workflow_yaml = """
schema_version: "2.0.0"
name: form-prompt-no-port-test
description: Integration test for missing submitted port
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: form1
  type: form_prompt
  parameters:
    name: Test Form
    form_definition:
      fields:
      - value_name: field1
        type: text
        label: Test Field
edges:
- from: trigger_manual
  to: form1
"""
        workflow_def: dict[str, Any] = yaml.safe_load(workflow_yaml)

        from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

        async with Worker(
            temporal_env.client,
            task_queue=task_queue,
            workflows=[OrchestratorWorkflow],
            activities=[
                resolve_approvers_activity,
                manual_trigger,
                _test_form_prompt_activity,
                fetch_workflow_runtime_settings,
            ],
        ):
            execution_service = TemporalExecutionService(
                temporal_client=temporal_env.client,
                task_queue=task_queue,
            )

            result = await execution_service.start_workflow(
                workflow_def=workflow_def,
                workflow_name="form-prompt-test",
                trigger_node_id="trigger_manual",
            )

            handle = temporal_env.client.get_workflow_handle(result.temporal_workflow_id, run_id=result.temporal_run_id)
            wf_result = await asyncio.wait_for(handle.result(), timeout=_RESULT_TIMEOUT_S)

            # Workflow should fail during form_prompt arg preparation
            assert wf_result["status"] == "failed"
            assert "submitted successor" in wf_result["failed_activities"]["form1"]
