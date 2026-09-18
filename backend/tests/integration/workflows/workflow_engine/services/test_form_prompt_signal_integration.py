"""Integration test for form_prompt async completion.

Tests the workflow-level handling of form_prompt responses using Temporal's
test environment. A form prompt suspends via Temporal async activity completion
(``activity.raise_complete_async()``); the Forms API later resolves it through
``TemporalExecutionService.complete_async_activity``. These tests drive that same
path with a stand-in activity so no Forms API call is made.
"""

import asyncio
from typing import Any
from uuid import uuid4

import pytest
import yaml
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from syntara.workflows.workflow_engine.activities.approver_resolution_activity import resolve_approvers_activity
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

# Activity IDs of the form prompts the workflow has suspended on, in scheduling order.
_pending_activity_ids: list[str] = []

_RESULT_TIMEOUT_S = 60


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
    """Stand-in for create_form_prompt_activity: suspends without calling the Forms API."""
    _pending_activity_ids.append(activity.info().activity_id)
    activity.raise_complete_async()


@activity.defn(name=ActivityName.SCRIPT)
async def _test_script_activity(
    resolved_parameters: dict[str, Any],
    outputs: dict[str, str] | None = None,
    **kwargs: object,
) -> dict[str, Any]:
    return {"output": {"status": "completed"}}


async def _wait_for_pending_prompt(index: int = 0) -> str:
    """Wait until the workflow has suspended on its ``index``-th form prompt."""
    for _ in range(300):
        if len(_pending_activity_ids) > index:
            return _pending_activity_ids[index]
        await asyncio.sleep(0.1)
    msg = "Form prompt activity never started"
    raise AssertionError(msg)


def _create_form_prompt_workflow_yaml(fallback_behavior: str = "fail") -> dict[str, Any]:
    """Create workflow with form_prompt for async-completion testing."""
    workflow_yaml = f"""
schema_version: "2.0.0"
name: form-prompt-signal-test
description: Integration test for form_prompt async completion
triggers:
- id: trigger_manual
  type: manual_trigger
nodes:
- id: form1
  type: form_prompt
  parameters:
    name: Test Form
    response_window: 300
    fallback_behavior: {fallback_behavior}
    form_definition:
      fields:
      - value_name: email
        type: text
        label: Email
- id: process_step
  type: script
  parameters:
    language: python
    code: "print('processing')"
edges:
- from: trigger_manual
  to: form1
- from: form1
  to: process_step
  from_port: submitted
"""
    result: dict[str, Any] = yaml.safe_load(workflow_yaml)
    return result


@pytest.mark.integration
@pytest.mark.asyncio
class TestFormPromptSignalIntegration:
    """Integration tests for resolving a form_prompt node via async activity completion."""

    async def _run(
        self,
        temporal_env: WorkflowEnvironment,
        task_queue: str,
        workflow_def: dict[str, Any],
        output: dict[str, Any],
    ) -> dict[str, Any]:
        """Start the workflow, resolve its form prompt with ``output``, return the result."""
        _pending_activity_ids.clear()

        async with Worker(
            temporal_env.client,
            task_queue=task_queue,
            workflows=[OrchestratorWorkflow],
            activities=[
                resolve_approvers_activity,
                manual_trigger,
                _test_form_prompt_activity,
                _test_script_activity,
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
                include_node_results=True,
            )

            activity_id = await _wait_for_pending_prompt()
            await execution_service.complete_async_activity(
                temporal_workflow_id=result.temporal_workflow_id,
                activity_id=activity_id,
                result={"output": output},
            )

            handle = temporal_env.client.get_workflow_handle(result.temporal_workflow_id, run_id=result.temporal_run_id)
            wf_result: dict[str, Any] = await asyncio.wait_for(handle.result(), timeout=_RESULT_TIMEOUT_S)
            return wf_result

    async def test_form_submission_completes_workflow(self, temporal_env: WorkflowEnvironment) -> None:
        """Completing the form_prompt activity with a submission continues the workflow."""
        wf_result = await self._run(
            temporal_env,
            task_queue="form-prompt-signal-queue",
            workflow_def=_create_form_prompt_workflow_yaml(),
            output={
                "outcome": "submitted",
                "response_data": {"email": "test@example.com"},
                "responded_by": str(uuid4()),
                "responded_at": "2026-04-10T12:00:00Z",
                "prompt_id": str(uuid4()),
            },
        )

        assert wf_result["status"] == "completed"

        form_output = wf_result["activity_outputs"]["form1"]
        assert form_output["outcome"] == "submitted"
        assert form_output["response_data"]["email"] == "test@example.com"

        # The submitted port was taken
        assert "process_step" in wf_result["completed_activities"]

    async def test_expired_outcome_fails_the_node(self, temporal_env: WorkflowEnvironment) -> None:
        """Only 'submitted' may arrive via async completion; 'expired' fails the node.

        Expiry is produced by the Temporal activity timeout, not by a response, so an
        externally delivered "expired" outcome is rejected even when
        fallback_behavior=fallback.
        """
        wf_result = await self._run(
            temporal_env,
            task_queue="form-prompt-signal-expire-queue",
            workflow_def=_create_form_prompt_workflow_yaml(fallback_behavior="fallback"),
            output={
                "outcome": "expired",
                "response_data": None,
                "responded_by": "system",
                "responded_at": "2026-04-10T12:00:00Z",
            },
        )

        assert wf_result["status"] == "failed"
        assert "Invalid form prompt outcome" in wf_result["failed_activities"]["form1"]
        assert "process_step" not in wf_result["completed_activities"]

    async def test_cancelled_outcome_fails_the_node(self, temporal_env: WorkflowEnvironment) -> None:
        """A 'cancelled' outcome delivered via async completion fails the node."""
        wf_result = await self._run(
            temporal_env,
            task_queue="form-prompt-signal-cancel-queue",
            workflow_def=_create_form_prompt_workflow_yaml(),
            output={
                "outcome": "cancelled",
                "response_data": None,
                "responded_by": "admin",
                "responded_at": "2026-04-10T12:00:00Z",
            },
        )

        assert wf_result["status"] == "failed"
        assert "Invalid form prompt outcome" in wf_result["failed_activities"]["form1"]
        assert "process_step" not in wf_result["completed_activities"]

    async def test_activity_failure_propagates_to_the_node(self, temporal_env: WorkflowEnvironment) -> None:
        """Failing the async activity (e.g. detached prompt) fails the form_prompt node."""
        _pending_activity_ids.clear()
        task_queue = "form-prompt-signal-fail-queue"

        async with Worker(
            temporal_env.client,
            task_queue=task_queue,
            workflows=[OrchestratorWorkflow],
            activities=[
                resolve_approvers_activity,
                manual_trigger,
                _test_form_prompt_activity,
                _test_script_activity,
                fetch_workflow_runtime_settings,
            ],
        ):
            execution_service = TemporalExecutionService(
                temporal_client=temporal_env.client,
                task_queue=task_queue,
            )

            result = await execution_service.start_workflow(
                workflow_def=_create_form_prompt_workflow_yaml(),
                workflow_name="form-prompt-test",
                trigger_node_id="trigger_manual",
                include_node_results=True,
            )

            activity_id = await _wait_for_pending_prompt()
            await execution_service.fail_async_activity(
                temporal_workflow_id=result.temporal_workflow_id,
                activity_id=activity_id,
                error=ApplicationError("form prompt cancelled", type="FormPromptCancelled", non_retryable=True),
            )

            handle = temporal_env.client.get_workflow_handle(result.temporal_workflow_id, run_id=result.temporal_run_id)
            wf_result = await asyncio.wait_for(handle.result(), timeout=_RESULT_TIMEOUT_S)

        assert wf_result["status"] == "failed"
        assert "form1" in wf_result["failed_activities"]
        assert "process_step" not in wf_result["completed_activities"]
