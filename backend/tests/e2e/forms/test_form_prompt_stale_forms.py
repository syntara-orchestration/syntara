"""E2E coverage for form prompt retry, stale, and cancelled submissions."""

import json
from collections.abc import Callable
from http import HTTPStatus
from typing import Any, cast
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e.helpers import poll_execution, poll_for_pending_form_prompt
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import (
    ExecutionRead,
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowRead,
    WorkflowReadWithVersion,
    WorkflowUpdate,
)
from syntara_api_client.models.activity_data_output_data_type_0 import ActivityDataOutputDataType0
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.form_prompt_status import FormPromptStatus

from ._helpers import (
    CANCEL_POLL_TIMEOUT,
    assert_and_get_with_502_skip,
    assert_consumer_completed,
    get_form_prompt,
    start_pending_form_prompt,
    submit_form_prompt,
    wait_for_activity_outputs,
    wait_for_form_prompt_paused,
    wait_for_form_prompt_status,
)

pytestmark = [pytest.mark.e2e]

_FORM_FIELDS: list[dict[str, Any]] = [
    {"type": "text", "value_name": "answer", "label": "Answer", "required": True},
]


def _assert_prompt_activity_response(
    syntara_api: SyntaraApiRegistry,
    execution: ExecutionRead,
    expected_response: dict[str, str],
) -> None:
    """Check the workflow activity recorded the exact submitted response."""
    execution = wait_for_activity_outputs(syntara_api, UUID(str(execution.id)), {"prompt"})
    activities = {activity.activity_id: activity for activity in (execution.activities or [])}
    prompt_activity = activities["prompt"]
    assert isinstance(prompt_activity.output_data, ActivityDataOutputDataType0)
    assert prompt_activity.output_data.to_dict()["response_data"] == expected_response


def test_retry_waits_for_new_form_prompt_response(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Retrying a completed run creates a pending form prompt with no old answer."""
    execution_id, prompt_row = start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        first_project_id,
        track_execution=form_prompt_execution_cleanup,
        workflow_name_prefix="e2e-form-prompt-retry",
        description="E2E: form prompt lifecycle behavior",
        producer_output={"ready": True},
        form_fields=_FORM_FIELDS,
        response_window=600,
    )
    wait_for_form_prompt_paused(syntara_api, execution_id)
    prompt_id = UUID(str(prompt_row.id))
    first_response = {"answer": "first answer"}

    submitted = submit_form_prompt(syntara_api, prompt_id, first_response)
    assert submitted.status_code == HTTPStatus.OK
    original_final = assert_consumer_completed(syntara_api, execution_id)
    _assert_prompt_activity_response(syntara_api, original_final, first_response)

    retry_response = syntara_api.executions.retry(execution_id=execution_id)
    assert retry_response.status_code == HTTPStatus.CREATED
    retried = retry_response.assert_and_get()
    retried_execution_id = UUID(str(retried.id))
    form_prompt_execution_cleanup(retried_execution_id)
    assert retried.retried_from_execution_id == execution_id

    retried_prompt_row = poll_for_pending_form_prompt(syntara_api, retried_execution_id)
    retried_prompt_id = UUID(str(retried_prompt_row.id))
    wait_for_form_prompt_paused(syntara_api, retried_execution_id)

    assert retried_prompt_id != prompt_id
    retried_prompt = get_form_prompt(syntara_api, retried_prompt_id)
    assert retried_prompt.status == FormPromptStatus.PENDING
    assert retried_prompt.to_dict().get("response_data") is None

    retried_response = {"answer": "new answer"}
    accepted = submit_form_prompt(syntara_api, retried_prompt_id, retried_response)
    assert accepted.status_code == HTTPStatus.OK
    retried_final = assert_consumer_completed(syntara_api, retried_execution_id)
    _assert_prompt_activity_response(syntara_api, retried_final, retried_response)

    original_prompt = get_form_prompt(syntara_api, prompt_id)
    assert original_prompt.to_dict().get("response_data") == first_response


def test_submission_uses_execution_version_after_node_is_removed_from_current_version(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """A running execution keeps using its version after a later edit removes the prompt node."""
    execution_id, prompt_row = start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        first_project_id,
        track_execution=form_prompt_execution_cleanup,
        workflow_name_prefix="e2e-form-prompt-deleted-node",
        description="E2E: form prompt lifecycle behavior",
        producer_output={"ready": True},
        form_fields=_FORM_FIELDS,
        response_window=600,
    )
    wait_for_form_prompt_paused(syntara_api, execution_id)
    prompt_id = UUID(str(prompt_row.id))

    execution = assert_and_get_with_502_skip(syntara_api.executions.get(execution_id=execution_id))
    workflow = cast(
        "WorkflowReadWithVersion",
        assert_and_get_with_502_skip(syntara_api.workflows.get(workflow_id=execution.workflow_id)),
    )
    definition = workflow.version.workflow_definition.to_dict()
    removed_node_ids = {"prompt", "consumer"}
    definition["nodes"] = [node for node in definition["nodes"] if node["id"] not in removed_node_ids]
    definition["edges"] = [
        edge
        for edge in definition["edges"]
        if edge["from"] not in removed_node_ids and edge["to"] not in removed_node_ids
    ]
    update_response = syntara_api.workflows.update(
        workflow_id=workflow.id,
        body=WorkflowUpdate(
            workflow_definition=WorkflowDefinition.from_dict(definition),
            change_description="Remove the form prompt node",
        ),
    )
    assert update_response.status_code == HTTPStatus.OK
    updated_workflow = cast("WorkflowReadWithVersion", assert_and_get_with_502_skip(update_response))
    assert updated_workflow.current_version > workflow.current_version
    updated_nodes = updated_workflow.version.workflow_definition.to_dict()["nodes"]
    assert all(node["id"] not in removed_node_ids for node in updated_nodes)
    existing_prompt = wait_for_form_prompt_status(syntara_api, prompt_id, FormPromptStatus.PENDING)
    assert existing_prompt.execution_id == execution_id

    submitted_response = {"answer": "valid for execution version"}
    response = submit_form_prompt(syntara_api, prompt_id, submitted_response)
    assert response.status_code == HTTPStatus.OK

    prompt_after_submission = get_form_prompt(syntara_api, prompt_id)
    assert prompt_after_submission.status == FormPromptStatus.SUBMITTED
    assert prompt_after_submission.to_dict().get("response_data") == submitted_response

    final_execution = assert_consumer_completed(syntara_api, execution_id)
    assert final_execution.workflow_version_id == execution.workflow_version_id
    _assert_prompt_activity_response(syntara_api, final_execution, submitted_response)


def test_submission_to_prompt_is_rejected_after_execution_is_cancelled(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Cancelling the execution cancels its prompt and rejects a later response."""
    execution_id, prompt_row = start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        first_project_id,
        track_execution=form_prompt_execution_cleanup,
        workflow_name_prefix="e2e-form-prompt-cancelled-submission",
        description="E2E: reject form prompt submission after execution cancellation",
        producer_output={"ready": True},
        form_fields=_FORM_FIELDS,
        response_window=600,
    )
    wait_for_form_prompt_paused(syntara_api, execution_id)
    prompt_id = UUID(str(prompt_row.id))

    cancel_response = syntara_api.executions.cancel(execution_id=execution_id)
    assert cancel_response.status_code == HTTPStatus.ACCEPTED

    cancelled_execution = poll_execution(syntara_api, str(execution_id), timeout=CANCEL_POLL_TIMEOUT)
    assert cancelled_execution.status == ExecutionStatus.CANCELLED
    activities = {activity.activity_id: activity for activity in (cancelled_execution.activities or [])}
    if "consumer" in activities:
        assert str(activities["consumer"].status) != "completed"

    cancelled_prompt = wait_for_form_prompt_status(syntara_api, prompt_id, FormPromptStatus.CANCELLED)
    assert cancelled_prompt.to_dict().get("response_data") is None

    late_response = submit_form_prompt(syntara_api, prompt_id, {"answer": "too late"})
    assert late_response.status_code == HTTPStatus.CONFLICT
    problem = json.loads(late_response.content)
    assert problem["code"] == "FORM_CANCELLED"
    assert "cancelled" in problem["detail"].lower()

    prompt_after_submission = get_form_prompt(syntara_api, prompt_id)
    assert prompt_after_submission.status == FormPromptStatus.CANCELLED
    assert prompt_after_submission.to_dict().get("response_data") is None

    execution_after_submission = assert_and_get_with_502_skip(syntara_api.executions.get(execution_id=execution_id))
    assert execution_after_submission.status == ExecutionStatus.CANCELLED


def test_duplicate_submission_does_not_change_form_prompt_response(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Only the first response can be stored for a form prompt."""
    execution_id, prompt_row = start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        first_project_id,
        track_execution=form_prompt_execution_cleanup,
        workflow_name_prefix="e2e-form-prompt-duplicate",
        description="E2E: form prompt lifecycle behavior",
        producer_output={"ready": True},
        form_fields=_FORM_FIELDS,
        response_window=600,
    )
    wait_for_form_prompt_paused(syntara_api, execution_id)
    prompt_id = UUID(str(prompt_row.id))
    first_response = {"answer": "accepted answer"}

    first_submission = submit_form_prompt(syntara_api, prompt_id, first_response)
    assert first_submission.status_code == HTTPStatus.OK
    final_execution = assert_consumer_completed(syntara_api, execution_id)

    duplicate = submit_form_prompt(syntara_api, prompt_id, {"answer": "duplicate answer"})
    assert duplicate.status_code == HTTPStatus.CONFLICT
    problem = json.loads(duplicate.content)
    assert problem["code"] == "FORM_ALREADY_RESPONDED"

    prompt_after_duplicate = get_form_prompt(syntara_api, prompt_id)
    assert prompt_after_duplicate.status == FormPromptStatus.SUBMITTED
    assert prompt_after_duplicate.to_dict().get("response_data") == first_response
    _assert_prompt_activity_response(syntara_api, final_execution, first_response)

    execution_after_duplicate = assert_and_get_with_502_skip(syntara_api.executions.get(execution_id=execution_id))
    assert execution_after_duplicate.status == ExecutionStatus.COMPLETED
