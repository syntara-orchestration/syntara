"""E2E coverage for enforcing materialized form-prompt option values."""

import json
from collections.abc import Callable
from http import HTTPStatus
from typing import Any, cast
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import poll_execution, poll_for_pending_form_prompt
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import ExecutionCreate, WorkflowCreate, WorkflowRead
from syntara_api_client.models.error_data import ErrorData
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.form_prompt_list_read import FormPromptListRead
from syntara_api_client.models.form_prompt_read import FormPromptRead
from syntara_api_client.models.form_prompt_status import FormPromptStatus
from syntara_api_client.models.form_prompt_submit_request import FormPromptSubmitRequest
from syntara_api_client.models.form_prompt_submit_request_response_data import (
    FormPromptSubmitRequestResponseData,
)
from syntara_api_client.types import Response, UnexpectedResponseException

from ._workflows import ENVIRONMENT_RECORDS, dynamic_option_field, producer_prompt_consumer_workflow

pytestmark = [pytest.mark.e2e]

_PROMPT_POLL_TIMEOUT = 60
_EXECUTION_POLL_TIMEOUT = 90


def _assert_and_get_with_502_skip[ResponseT](response: Response[ResponseT]) -> ResponseT:
    """Get a parsed response, skipping only on a transient Bad Gateway."""
    try:
        return response.assert_and_get()
    except UnexpectedResponseException as exc:
        if exc.status_code == HTTPStatus.BAD_GATEWAY:
            pytest.skip("Backend returned 502 Bad Gateway - transient infrastructure issue")
        raise


def _get_prompt(syntara_api: SyntaraApiRegistry, prompt_id: UUID) -> FormPromptRead:
    return cast(
        "FormPromptRead",
        _assert_and_get_with_502_skip(syntara_api.form_prompts.get(form_prompt_id=prompt_id)),
    )


def _submit(
    syntara_api: SyntaraApiRegistry,
    prompt_id: UUID,
    response_data: dict[str, Any],
) -> Response[ErrorData | FormPromptRead]:
    response = syntara_api.form_prompts.submit(
        form_prompt_id=prompt_id,
        body=FormPromptSubmitRequest(response_data=FormPromptSubmitRequestResponseData.from_dict(response_data)),
    )
    if response.status_code == HTTPStatus.BAD_GATEWAY:
        pytest.skip("Backend returned 502 Bad Gateway - transient infrastructure issue")
    return response


def _start(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    *,
    field_type: str = "dropdown",
    field_name: str = "environment",
) -> tuple[UUID, FormPromptListRead]:
    """Create and start a workflow with dynamic environment options."""
    name = unique_name("e2e-form-prompt-options")
    workflow = workflow_factory(
        WorkflowCreate(
            name=name,
            description="E2E: enforce resolved form prompt options",
            workflow_definition=producer_prompt_consumer_workflow(
                name,
                producer_output={"environments": ENVIRONMENT_RECORDS},
                form_fields=[
                    dynamic_option_field(
                        field_name,
                        "${producer.stdout_json.environments}",
                        field_type=field_type,
                    )
                ],
            ),
            project_id=first_project_id,
        )
    )
    execution = syntara_api.executions.create(
        body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger")
    ).assert_and_get()
    exec_id = UUID(str(execution.id))
    prompt = poll_for_pending_form_prompt(syntara_api, exec_id, timeout=_PROMPT_POLL_TIMEOUT)
    return exec_id, prompt


def _assert_options_resolved(
    syntara_api: SyntaraApiRegistry,
    prompt_id: UUID,
    *,
    field_name: str = "environment",
) -> None:
    """Verify the prompt persisted the producer's materialized options."""
    prompt = _get_prompt(syntara_api, prompt_id)
    definition = prompt.form_definition.to_dict()
    field = next(item for item in definition["fields"] if item["value_name"] == field_name)
    assert field["options"]["source"] == "dynamic_resolved"
    assert field["options"]["values"] == ENVIRONMENT_RECORDS


def _assert_consumer_completed(
    syntara_api: SyntaraApiRegistry,
    exec_id: UUID,
) -> None:
    final = poll_execution(syntara_api, str(exec_id), timeout=_EXECUTION_POLL_TIMEOUT)
    assert final.status == ExecutionStatus.COMPLETED, (
        f"Expected COMPLETED after form submission, got {final.status}: {final.error_details}"
    )
    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    assert "consumer" in activities, f"Consumer activity missing: {list(activities)}"
    assert activities["consumer"].status == "completed"


@pytest.mark.parametrize("bad_value", ["qa", "prod2"])
def test_submit_value_not_in_resolved_options_returns_422(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    bad_value: str,
) -> None:
    """A value outside the persisted option snapshot is rejected.

    Procedure:
    1. Start a workflow and GET its resolved form prompt.
    2. Submit a value that is not among the resolved environment values.

    Expected:
    - The response is 422 with FORM_VALIDATION_ERROR and identifies the field.
    - The error detail does not need to echo the rejected value.
    """
    _, prompt_row = _start(syntara_api, workflow_factory, first_project_id)
    prompt_id = UUID(str(prompt_row.id))
    _assert_options_resolved(syntara_api, prompt_id)

    response = _submit(syntara_api, prompt_id, {"environment": bad_value})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, (
        f"Expected 422 for value outside resolved options, got {response.status_code}"
    )
    problem = json.loads(response.content)
    assert problem["code"] == "FORM_VALIDATION_ERROR"
    assert "environment" in problem["detail"]


def test_prompt_remains_pending_after_rejected_submission(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
) -> None:
    """A rejected submission leaves the prompt live and able to accept valid input.

    Procedure:
    1. Start a workflow and GET its resolved form prompt.
    2. Submit an invalid value and confirm the 422 response.
    3. GET the prompt and execution to verify neither changed state.
    4. Submit a valid value to prove the prompt remains usable.

    Expected:
    - The prompt remains pending with no response metadata after rejection.
    - The execution has not completed the consumer activity.
    - A subsequent valid response completes the workflow.
    """
    exec_id, prompt_row = _start(syntara_api, workflow_factory, first_project_id)
    prompt_id = UUID(str(prompt_row.id))
    _assert_options_resolved(syntara_api, prompt_id)

    rejected = _submit(syntara_api, prompt_id, {"environment": "qa"})
    assert rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    prompt = _get_prompt(syntara_api, prompt_id)
    assert prompt.status == FormPromptStatus.PENDING
    prompt_data = prompt.to_dict()
    assert prompt_data.get("response_data") is None
    assert prompt_data.get("responded_at") is None
    assert prompt_data.get("responded_by") is None

    execution = _assert_and_get_with_502_skip(syntara_api.executions.get(execution_id=exec_id, include="activities"))
    assert execution.status == ExecutionStatus.RUNNING
    activities = {activity.activity_id: activity for activity in (execution.activities or [])}
    assert "consumer" not in activities or activities["consumer"].status != "completed"

    accepted = _submit(syntara_api, prompt_id, {"environment": "dev"})
    assert accepted.status_code == HTTPStatus.OK
    _assert_consumer_completed(syntara_api, exec_id)


def test_submit_valid_resolved_value_succeeds(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
) -> None:
    """A value from the resolved option snapshot is accepted.

    Procedure:
    1. Start a workflow and GET its resolved form prompt.
    2. Submit a valid environment value.
    3. Poll execution to terminal.

    Expected:
    - The submit returns 200, execution completes, and the consumer runs.
    """
    exec_id, prompt_row = _start(syntara_api, workflow_factory, first_project_id)
    prompt_id = UUID(str(prompt_row.id))
    _assert_options_resolved(syntara_api, prompt_id)

    response = _submit(syntara_api, prompt_id, {"environment": "staging"})
    assert response.status_code == HTTPStatus.OK
    _assert_consumer_completed(syntara_api, exec_id)


def test_multi_select_rejects_partially_invalid_selection(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
) -> None:
    """Multi-select validation rejects a mixed valid and invalid selection.

    Procedure:
    1. Start a multi-select prompt and GET its resolved options.
    2. Submit a selection containing one valid and one invalid value.
    3. Start a second workflow and submit a selection containing only valid values.

    Expected:
    - The mixed selection returns 422.
    - The all-valid selection returns 200 and completes the second execution.
    """
    _, first_prompt = _start(
        syntara_api,
        workflow_factory,
        first_project_id,
        field_type="multi_select",
        field_name="environments",
    )
    first_prompt_id = UUID(str(first_prompt.id))
    _assert_options_resolved(syntara_api, first_prompt_id, field_name="environments")

    rejected = _submit(syntara_api, first_prompt_id, {"environments": ["staging", "qa"]})
    assert rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    first_prompt_after_rejection = _get_prompt(syntara_api, first_prompt_id)
    assert first_prompt_after_rejection.status == FormPromptStatus.PENDING

    second_exec_id, second_prompt = _start(
        syntara_api,
        workflow_factory,
        first_project_id,
        field_type="multi_select",
        field_name="environments",
    )
    second_prompt_id = UUID(str(second_prompt.id))
    _assert_options_resolved(syntara_api, second_prompt_id, field_name="environments")

    accepted = _submit(syntara_api, second_prompt_id, {"environments": ["dev", "prod"]})
    assert accepted.status_code == HTTPStatus.OK
    _assert_consumer_completed(syntara_api, second_exec_id)
