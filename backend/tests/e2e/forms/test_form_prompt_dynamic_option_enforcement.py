"""E2E coverage for enforcing materialized form-prompt option values."""

import json
from collections.abc import Callable
from http import HTTPStatus
from uuid import UUID

import pytest
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import WorkflowCreate, WorkflowRead
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.form_prompt_list_read import FormPromptListRead
from syntara_api_client.models.form_prompt_status import FormPromptStatus

from ._helpers import (
    assert_and_get_with_502_skip,
    assert_consumer_completed,
    get_form_prompt,
    start_pending_form_prompt,
    submit_form_prompt,
)
from ._workflows import ENVIRONMENT_RECORDS, dynamic_option_field

pytestmark = [pytest.mark.e2e]


def _start(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    track_execution: Callable[[UUID], None],
    *,
    field_type: str = "dropdown",
    field_name: str = "environment",
    response_window: int = 600,
) -> tuple[UUID, FormPromptListRead]:
    """Create and start a workflow with dynamic environment options."""
    return start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        first_project_id,
        workflow_name_prefix="e2e-form-prompt-options",
        description="E2E: enforce resolved form prompt options",
        track_execution=track_execution,
        producer_output={"environments": ENVIRONMENT_RECORDS},
        form_fields=[
            dynamic_option_field(
                field_name,
                "${producer.stdout_json.environments}",
                field_type=field_type,
            )
        ],
        response_window=response_window,
    )


def _assert_options_resolved(
    syntara_api: SyntaraApiRegistry,
    prompt_id: UUID,
    *,
    field_name: str = "environment",
) -> None:
    """Verify the prompt persisted the producer's materialized options."""
    prompt = get_form_prompt(syntara_api, prompt_id)
    definition = prompt.form_definition.to_dict()
    field = next(item for item in definition["fields"] if item["value_name"] == field_name)
    assert field["options"]["source"] == "dynamic_resolved"
    assert field["options"]["values"] == ENVIRONMENT_RECORDS


@pytest.mark.parametrize("bad_value", ["qa", "prod2"])
def test_submit_value_not_in_resolved_options_returns_422(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
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
    _, prompt_row = _start(
        syntara_api,
        workflow_factory,
        first_project_id,
        form_prompt_execution_cleanup,
        response_window=30,
    )
    prompt_id = UUID(str(prompt_row.id))
    _assert_options_resolved(syntara_api, prompt_id)

    response = submit_form_prompt(syntara_api, prompt_id, {"environment": bad_value})
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
    form_prompt_execution_cleanup: Callable[[UUID], None],
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
    exec_id, prompt_row = _start(
        syntara_api,
        workflow_factory,
        first_project_id,
        form_prompt_execution_cleanup,
    )
    prompt_id = UUID(str(prompt_row.id))
    _assert_options_resolved(syntara_api, prompt_id)

    rejected = submit_form_prompt(syntara_api, prompt_id, {"environment": "qa"})
    assert rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    prompt = get_form_prompt(syntara_api, prompt_id)
    assert prompt.status == FormPromptStatus.PENDING
    prompt_data = prompt.to_dict()
    assert prompt_data.get("response_data") is None
    assert prompt_data.get("responded_at") is None
    assert prompt_data.get("responded_by") is None

    execution = assert_and_get_with_502_skip(syntara_api.executions.get(execution_id=exec_id, include="activities"))
    assert execution.status == ExecutionStatus.RUNNING
    activities = {activity.activity_id: activity for activity in (execution.activities or [])}
    assert "consumer" not in activities or activities["consumer"].status != "completed"

    accepted = submit_form_prompt(syntara_api, prompt_id, {"environment": "dev"})
    assert accepted.status_code == HTTPStatus.OK
    assert_consumer_completed(syntara_api, exec_id)


def test_submit_valid_resolved_value_succeeds(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """A value from the resolved option snapshot is accepted.

    Procedure:
    1. Start a workflow and GET its resolved form prompt.
    2. Submit a valid environment value.
    3. Poll execution to terminal.

    Expected:
    - The submit returns 200, execution completes, and the consumer runs.
    """
    exec_id, prompt_row = _start(
        syntara_api,
        workflow_factory,
        first_project_id,
        form_prompt_execution_cleanup,
    )
    prompt_id = UUID(str(prompt_row.id))
    _assert_options_resolved(syntara_api, prompt_id)

    response = submit_form_prompt(syntara_api, prompt_id, {"environment": "staging"})
    assert response.status_code == HTTPStatus.OK
    assert_consumer_completed(syntara_api, exec_id)


def test_multi_select_rejects_partially_invalid_selection(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
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
        form_prompt_execution_cleanup,
        field_type="multi_select",
        field_name="environments",
        response_window=30,
    )
    first_prompt_id = UUID(str(first_prompt.id))
    _assert_options_resolved(syntara_api, first_prompt_id, field_name="environments")

    rejected = submit_form_prompt(syntara_api, first_prompt_id, {"environments": ["staging", "qa"]})
    assert rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    first_prompt_after_rejection = get_form_prompt(syntara_api, first_prompt_id)
    assert first_prompt_after_rejection.status == FormPromptStatus.PENDING

    second_exec_id, second_prompt = _start(
        syntara_api,
        workflow_factory,
        first_project_id,
        form_prompt_execution_cleanup,
        field_type="multi_select",
        field_name="environments",
    )
    second_prompt_id = UUID(str(second_prompt.id))
    _assert_options_resolved(syntara_api, second_prompt_id, field_name="environments")

    accepted = submit_form_prompt(syntara_api, second_prompt_id, {"environments": ["dev", "prod"]})
    assert accepted.status_code == HTTPStatus.OK
    assert_consumer_completed(syntara_api, second_exec_id)
