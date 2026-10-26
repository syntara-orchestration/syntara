"""End-to-end tests for Form Trigger submission validation and workflow input flow."""

from collections.abc import Callable
from http import HTTPStatus
from typing import Any
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import ExecutionCreate, WorkflowCreate, WorkflowRead
from syntara_api_client.models.activity_data import ActivityData
from syntara_api_client.models.activity_data_output_data_type_0 import ActivityDataOutputDataType0
from syntara_api_client.types import Response

from ._helpers import (
    assert_and_get_with_502_skip,
    assert_consumer_completed,
    assert_problem_response,
    wait_for_activity_outputs,
)
from ._workflows import ALL_SUPPORTED_FORM_FIELDS, form_trigger_consumer_workflow

pytestmark = [pytest.mark.e2e]

_FORM_TRIGGER_NAME_PREFIX = "e2e-form-trigger-submission"
_FORM_TRIGGER_DESCRIPTION = "E2E: validate and pass Form Trigger submissions"
_CONSUMER_ENVIRONMENT = {
    "FORM_TEXT": "${form.response_data.required_text}",
    "FORM_COUNT": "${form.response_data.count}",
    "TRIGGER_EMAIL": "${trigger.response_data.contact}",
}
_CONSUMER_CODE = """
import json
import os

print(json.dumps({
    "required_text": os.environ["FORM_TEXT"],
    "count": json.loads(os.environ["FORM_COUNT"]),
    "contact": os.environ["TRIGGER_EMAIL"],
}))
"""
_SIMPLE_FORM_FIELDS = [
    {"type": "text", "value_name": "required_text", "label": "Required text", "required": True},
    {
        "type": "dropdown",
        "value_name": "environment",
        "label": "Environment",
        "required": False,
        "options": {"source": "static", "values": [{"display_label": "Staging", "value": "staging"}]},
    },
    {"type": "number", "value_name": "count", "label": "Count", "required": True},
    {"type": "email", "value_name": "contact", "label": "Contact", "required": True},
]
_VALID_SIMPLE_SUBMISSION: dict[str, Any] = {
    "required_text": "test submission",
    "count": "42",
    "contact": "Bob@Example.COM",
}
_ALL_FIELDS_SUBMISSION: dict[str, Any] = {
    "text_value": "short answer",
    "textarea_value": "longer answer\nwith a second line",
    "number_value": 42,
    "masked_value": "masked-entry",
    "dropdown_value": "blue",
    "multi_select_value": ["red", "blue"],
    "checkbox_value": True,
    "date_value": {"date": "2026-02-14"},
    "email_value": "tester@example.com",
}
_ALL_FIELDS_ENVIRONMENT = {
    "TEXT_VALUE": "${form.response_data.text_value}",
    "TEXTAREA_VALUE": "${form.response_data.textarea_value}",
    "NUMBER_VALUE": "${form.response_data.number_value}",
    "MASKED_VALUE": "${form.response_data.masked_value}",
    "DROPDOWN_VALUE": "${form.response_data.dropdown_value}",
    "MULTI_SELECT_VALUE": "${form.response_data.multi_select_value}",
    "CHECKBOX_VALUE": "${form.response_data.checkbox_value}",
    "DATE_VALUE": "${form.response_data.date_value}",
    "EMAIL_VALUE": "${trigger.response_data.email_value}",
}
_ALL_FIELDS_CONSUMER_CODE = """
import json
import os

print(json.dumps({
    "text_value": os.environ["TEXT_VALUE"],
    "textarea_value": os.environ["TEXTAREA_VALUE"],
    "number_value": json.loads(os.environ["NUMBER_VALUE"]),
    "masked_value": os.environ["MASKED_VALUE"],
    "dropdown_value": os.environ["DROPDOWN_VALUE"],
    "multi_select_value": json.loads(os.environ["MULTI_SELECT_VALUE"]),
    "checkbox_value": json.loads(os.environ["CHECKBOX_VALUE"]),
    "date_value": json.loads(os.environ["DATE_VALUE"]),
    "email_value": os.environ["EMAIL_VALUE"],
}))
"""

WorkflowFactory = Callable[[WorkflowCreate], WorkflowRead]


def _activity_output(activity: ActivityData) -> dict[str, Any]:
    """Return an activity's object-shaped output data."""
    output_data = activity.output_data
    assert isinstance(output_data, ActivityDataOutputDataType0)
    return output_data.to_dict()


def _form_workflow(
    workflow_factory: WorkflowFactory,
    first_project_id: UUID,
    *,
    form_fields: list[dict[str, Any]],
    consumer_code: str,
    consumer_environment: dict[str, str],
) -> WorkflowRead:
    """Create a uniquely named Form Trigger consumer workflow."""
    name = unique_name(_FORM_TRIGGER_NAME_PREFIX)
    return workflow_factory(
        WorkflowCreate(
            name=name,
            description=_FORM_TRIGGER_DESCRIPTION,
            project_id=first_project_id,
            workflow_definition=form_trigger_consumer_workflow(
                name,
                form_fields=form_fields,
                consumer_code=consumer_code,
                consumer_environment=consumer_environment,
            ),
        )
    )


def _start_execution(
    syntara_api: SyntaraApiRegistry,
    workflow: WorkflowRead,
    input_data: dict[str, Any],
) -> Response[Any]:
    """Start a Form Trigger workflow with the provided field values."""
    return syntara_api.executions.create(
        body=ExecutionCreate.from_dict(
            {
                "workflow_id": str(workflow.id),
                "trigger_node_id": "form",
                "input_data": input_data,
            }
        )
    )


def test_coerced_submission_reaches_both_trigger_namespaces(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: WorkflowFactory,
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Form input is coerced before Temporal and resolves by node ID and shared namespace.

    Procedure:
    1. Create a workflow whose consumer reads the Form Trigger by node ID and via ``trigger``.
    2. Submit a numeric string and a mixed-case email address.
    3. Inspect the persisted execution input and downstream script output.

    Expected:
    - The API response and stored execution contain a float and normalized email.
    - The downstream script receives the same cleaned values through both namespaces.
    """
    workflow = _form_workflow(
        workflow_factory,
        first_project_id,
        form_fields=_SIMPLE_FORM_FIELDS,
        consumer_code=_CONSUMER_CODE,
        consumer_environment=_CONSUMER_ENVIRONMENT,
    )

    execution = assert_and_get_with_502_skip(_start_execution(syntara_api, workflow, _VALID_SIMPLE_SUBMISSION))
    execution_id = UUID(str(execution.id))
    form_prompt_execution_cleanup(execution_id)

    assert execution.input_data is not None
    assert execution.input_data.to_dict() == {
        "required_text": "test submission",
        "count": 42.0,
        "contact": "Bob@example.com",
    }
    assert_consumer_completed(syntara_api, execution_id)
    final = wait_for_activity_outputs(syntara_api, execution_id, {"form", "consumer"})
    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    assert _activity_output(activities["form"])["response_data"] == execution.input_data.to_dict()
    downstream = _activity_output(activities["consumer"])["stdout_json"]
    assert downstream == {
        "required_text": "test submission",
        "count": 42.0,
        "contact": "Bob@example.com",
    }
    assert isinstance(downstream["count"], float)


def test_all_supported_form_fields_reach_downstream_consumer(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: WorkflowFactory,
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Every supported Form Trigger field type reaches its consumer with the expected JSON shape."""
    workflow = _form_workflow(
        workflow_factory,
        first_project_id,
        form_fields=ALL_SUPPORTED_FORM_FIELDS,
        consumer_code=_ALL_FIELDS_CONSUMER_CODE,
        consumer_environment=_ALL_FIELDS_ENVIRONMENT,
    )

    execution = assert_and_get_with_502_skip(_start_execution(syntara_api, workflow, _ALL_FIELDS_SUBMISSION))
    execution_id = UUID(str(execution.id))
    form_prompt_execution_cleanup(execution_id)

    assert_consumer_completed(syntara_api, execution_id)
    final = wait_for_activity_outputs(syntara_api, execution_id, {"consumer"})
    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    downstream = _activity_output(activities["consumer"])["stdout_json"]
    expected_downstream = {**_ALL_FIELDS_SUBMISSION, "date_value": "2026-02-14"}
    assert downstream == expected_downstream
    assert isinstance(downstream["number_value"], int)
    assert isinstance(downstream["multi_select_value"], list)
    assert isinstance(downstream["checkbox_value"], bool)
    assert isinstance(downstream["date_value"], str)


def test_invalid_submission_starts_no_execution_then_valid_submission_completes(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: WorkflowFactory,
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Invalid Form Trigger values are rejected without creating an execution."""
    workflow = _form_workflow(
        workflow_factory,
        first_project_id,
        form_fields=_SIMPLE_FORM_FIELDS,
        consumer_code=_CONSUMER_CODE,
        consumer_environment=_CONSUMER_ENVIRONMENT,
    )

    rejected = _start_execution(syntara_api, workflow, {"count": "42", "contact": "bob@example.com"})
    problem = assert_problem_response(
        rejected,
        expected_status=HTTPStatus.UNPROCESSABLE_ENTITY,
        expected_code="FORM_VALIDATION_ERROR",
    )
    assert "required_text: This field is required" in problem["detail"]

    executions = assert_and_get_with_502_skip(
        syntara_api.executions.list(additional_params={"workflow_id": str(workflow.id)}, limit=100)
    )
    assert not executions.resources

    accepted = assert_and_get_with_502_skip(_start_execution(syntara_api, workflow, _VALID_SIMPLE_SUBMISSION))
    execution_id = UUID(str(accepted.id))
    form_prompt_execution_cleanup(execution_id)
    assert_consumer_completed(syntara_api, execution_id)
