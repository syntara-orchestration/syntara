"""E2E coverage for Form Trigger retries, repeated submissions, and deleted workflows."""

import json
from collections.abc import Callable
from http import HTTPStatus
from typing import Any
from uuid import UUID

import pytest
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import ExecutionRead, WorkflowCreate, WorkflowRead

from ._helpers import (
    activities_by_id,
    activity_output,
    assert_and_get_with_502_skip,
    assert_consumer_completed,
    assert_no_executions_for_workflow,
    assert_problem_response,
    create_form_trigger_workflow,
    submit_form_trigger,
    submit_form_trigger_and_track,
    wait_for_activity_outputs,
)

pytestmark = [pytest.mark.e2e]

_FORM_FIELDS: list[dict[str, Any]] = [
    {"type": "text", "value_name": "environment", "label": "Environment", "required": True},
    {"type": "number", "value_name": "count", "label": "Count", "required": True},
]
_FORM_INPUTS = {"environment": "prod", "count": 5}
_CONSUMER_ENVIRONMENT = {
    "ENVIRONMENT": "${form.response_data.environment}",
    "COUNT": "${form.response_data.count}",
}
_CONSUMER_CODE = """
import json
import os

print(json.dumps({
    "environment": os.environ["ENVIRONMENT"],
    "count": json.loads(os.environ["COUNT"]),
}))
"""


def _execution_input(execution: ExecutionRead) -> dict[str, Any]:
    """Return the submitted input payload from an execution response."""
    return execution.input_data.to_dict()


def test_retry_reuses_original_form_trigger_inputs(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Retry a completed Form Trigger workflow with the original submission and no new form response."""
    workflow = create_form_trigger_workflow(
        workflow_factory,
        first_project_id,
        name_prefix="e2e-form-trigger-retry",
        description="E2E: retry reuses Form Trigger inputs",
        form_fields=_FORM_FIELDS,
        consumer_code=_CONSUMER_CODE,
        consumer_environment=_CONSUMER_ENVIRONMENT,
    )
    original = submit_form_trigger_and_track(
        syntara_api,
        workflow,
        _FORM_INPUTS,
        form_execution_cleanup,
    )
    original_id = UUID(str(original.id))
    assert _execution_input(original) == _FORM_INPUTS

    original_final = assert_consumer_completed(syntara_api, original_id)
    original_with_outputs = wait_for_activity_outputs(syntara_api, original_id, {"form", "consumer"})
    original_activities = activities_by_id(original_with_outputs)
    original_form_response = activity_output(original_activities["form"])["response_data"]
    original_consumer_output = activity_output(original_activities["consumer"])["stdout_json"]
    assert original_form_response == _FORM_INPUTS
    assert original_consumer_output == _FORM_INPUTS
    assert str(original_final.status) == "completed"

    retry_response = syntara_api.executions.retry(execution_id=original_id)
    assert retry_response.status_code in {HTTPStatus.OK, HTTPStatus.CREATED}, (
        f"Expected 200 OK or 201 Created, got {retry_response.status_code}: {retry_response.content!r}"
    )
    # The generated client currently models 201. Parse the response body directly so
    # this test also accepts a valid 200 response from a server version that uses it.
    retried = ExecutionRead.from_dict(json.loads(retry_response.content))
    retried_id = UUID(str(retried.id))
    form_execution_cleanup(retried_id)

    assert retried.retried_from_execution_id == original_id
    assert _execution_input(retried) == _execution_input(original)

    retried_final = assert_consumer_completed(syntara_api, retried_id)
    retried_with_outputs = wait_for_activity_outputs(syntara_api, retried_id, {"form", "consumer"})
    retried_activities = activities_by_id(retried_with_outputs)
    retried_form_response = activity_output(retried_activities["form"])["response_data"]
    retried_consumer_output = activity_output(retried_activities["consumer"])["stdout_json"]

    assert str(retried_final.status) == "completed"
    assert retried_form_response == original_form_response == _FORM_INPUTS
    assert retried_consumer_output == original_consumer_output == _FORM_INPUTS


def test_repeated_submission_creates_distinct_completed_executions(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Posting the same valid Form Trigger submission twice starts two executions."""
    workflow = create_form_trigger_workflow(
        workflow_factory,
        first_project_id,
        name_prefix="e2e-form-trigger-repeat-submission",
        description="E2E: repeated Form Trigger submissions create separate executions",
        form_fields=_FORM_FIELDS,
        consumer_code=_CONSUMER_CODE,
        consumer_environment=_CONSUMER_ENVIRONMENT,
    )
    workflow_id = UUID(str(workflow.id))

    first = submit_form_trigger_and_track(syntara_api, workflow, _FORM_INPUTS, form_execution_cleanup)
    second = submit_form_trigger_and_track(syntara_api, workflow, _FORM_INPUTS, form_execution_cleanup)
    first_id = UUID(str(first.id))
    second_id = UUID(str(second.id))

    assert first_id != second_id
    assert _execution_input(first) == _FORM_INPUTS
    assert _execution_input(second) == _FORM_INPUTS

    for execution_id in (first_id, second_id):
        completed = assert_consumer_completed(syntara_api, execution_id)
        assert _execution_input(completed) == _FORM_INPUTS
        final = wait_for_activity_outputs(syntara_api, execution_id, {"form", "consumer"})
        activities = activities_by_id(final)
        assert activity_output(activities["form"])["response_data"] == _FORM_INPUTS
        assert activity_output(activities["consumer"])["stdout_json"] == _FORM_INPUTS

    executions = assert_and_get_with_502_skip(
        syntara_api.executions.list(additional_params={"workflow_id": str(workflow_id)}, limit=100)
    )
    assert executions.resources is not None
    assert {UUID(str(execution.id)) for execution in executions.resources} == {first_id, second_id}


def test_submission_after_workflow_deletion_returns_workflow_not_found(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
) -> None:
    """A Form Trigger submission endpoint rejects requests after its workflow is deleted."""
    workflow = create_form_trigger_workflow(
        workflow_factory,
        first_project_id,
        name_prefix="e2e-form-trigger-deleted-workflow",
        description="E2E: reject Form Trigger submission after workflow deletion",
        form_fields=_FORM_FIELDS,
    )
    workflow_id = UUID(str(workflow.id))

    delete_response = syntara_api.workflows.delete(workflow_id=workflow_id)
    assert delete_response.status_code == HTTPStatus.NO_CONTENT

    submission_response = submit_form_trigger(syntara_api, workflow, _FORM_INPUTS)
    problem = assert_problem_response(
        submission_response,
        expected_status=HTTPStatus.NOT_FOUND,
        expected_code="WORKFLOW_NOT_FOUND",
    )
    assert problem["title"] == "Workflow Not Found"
    assert problem["detail"] == "The requested workflow was not found"

    assert_no_executions_for_workflow(syntara_api, workflow_id)
