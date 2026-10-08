"""E2E coverage for form-prompt field submission and validation."""

import json
from collections.abc import Callable
from http import HTTPStatus
from typing import Any
from uuid import UUID

import pytest
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import WorkflowCreate, WorkflowRead
from syntara_api_client.models.activity_data import ActivityData
from syntara_api_client.models.activity_data_output_data_type_0 import ActivityDataOutputDataType0
from syntara_api_client.models.error_data import ErrorData
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.form_prompt_read import FormPromptRead
from syntara_api_client.models.form_prompt_status import FormPromptStatus
from syntara_api_client.types import Response

from ._helpers import (
    assert_consumer_completed,
    get_form_prompt,
    start_pending_form_prompt,
    submit_form_prompt,
    wait_for_activity_outputs,
)

pytestmark = [pytest.mark.e2e]

_FORM_PROMPT_WORKFLOW_NAME_PREFIX = "e2e-form-prompt-field-validation"
_FORM_PROMPT_WORKFLOW_DESCRIPTION = "E2E: validate form prompt field types and submissions"

_ALL_FIELDS = [
    {"type": "text", "value_name": "text_value", "label": "Text", "required": True},
    {"type": "textarea", "value_name": "textarea_value", "label": "Textarea", "required": True},
    {"type": "number", "value_name": "number_value", "label": "Number", "required": True},
    {"type": "masked_text", "value_name": "masked_value", "label": "Masked text", "required": True},
    {
        "type": "dropdown",
        "value_name": "dropdown_value",
        "label": "Dropdown",
        "required": True,
        "options": {
            "source": "static",
            "values": [
                {"display_label": "Blue", "value": "blue"},
                {"display_label": "Green", "value": "green"},
            ],
        },
    },
    {
        "type": "multi_select",
        "value_name": "multi_select_value",
        "label": "Multi-select",
        "required": True,
        "options": {
            "source": "static",
            "values": [
                {"display_label": "Red", "value": "red"},
                {"display_label": "Blue", "value": "blue"},
            ],
        },
    },
    {"type": "checkbox", "value_name": "checkbox_value", "label": "Checkbox", "required": True},
    {"type": "date", "value_name": "date_value", "label": "Date", "required": True},
    {"type": "email", "value_name": "email_value", "label": "Email", "required": True},
]

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
    "TEXT_VALUE": "${prompt.response_data.text_value}",
    "TEXTAREA_VALUE": "${prompt.response_data.textarea_value}",
    "NUMBER_VALUE": "${prompt.response_data.number_value}",
    "MASKED_VALUE": "${prompt.response_data.masked_value}",
    "DROPDOWN_VALUE": "${prompt.response_data.dropdown_value}",
    "MULTI_SELECT_VALUE": "${prompt.response_data.multi_select_value}",
    "CHECKBOX_VALUE": "${prompt.response_data.checkbox_value}",
    "DATE_VALUE": "${prompt.response_data.date_value}",
    "EMAIL_VALUE": "${prompt.response_data.email_value}",
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


def _assert_validation_error(
    response: Response[ErrorData | FormPromptRead],
    *,
    field_name: str,
    expected_detail: str | None = None,
) -> None:
    """Assert the API returns a field-specific form validation problem."""
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, (
        f"Expected 422 for invalid form response, got {response.status_code}"
    )
    problem = json.loads(response.content)
    assert problem["code"] == "FORM_VALIDATION_ERROR"
    assert field_name in problem["detail"]
    if expected_detail is not None:
        assert expected_detail in problem["detail"]


def _activity_output(activity: ActivityData) -> dict[str, Any]:
    """Extract an activity's object-shaped output data."""
    output_data = activity.output_data
    assert isinstance(output_data, ActivityDataOutputDataType0)
    return output_data.to_dict()


def test_all_supported_field_types_resume_and_flow_to_consumer(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """All form fields retain their values and types after submission.

    Procedure:
    1. Start a workflow with text, textarea, number, masked text, dropdown,
       multi-select, checkbox, date, and email fields.
    2. Wait for the form prompt, then submit a valid value for every field.
    3. Inspect the prompt and downstream script activity outputs.

    Expected:
    - The form-prompt submission returns 200 and resumes the workflow.
    - Every field reaches the consumer with its submitted JSON type preserved.
    """
    execution_id, prompt = start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        first_project_id,
        workflow_name_prefix=_FORM_PROMPT_WORKFLOW_NAME_PREFIX,
        description=_FORM_PROMPT_WORKFLOW_DESCRIPTION,
        track_execution=form_prompt_execution_cleanup,
        producer_output={},
        form_fields=_ALL_FIELDS,
        consumer_code=_ALL_FIELDS_CONSUMER_CODE,
        consumer_environment=_ALL_FIELDS_ENVIRONMENT,
    )
    prompt_id = UUID(str(prompt.id))

    response = submit_form_prompt(syntara_api, prompt_id, _ALL_FIELDS_SUBMISSION)
    assert response.status_code == HTTPStatus.OK

    assert_consumer_completed(syntara_api, execution_id)
    final = wait_for_activity_outputs(syntara_api, execution_id, {"prompt", "consumer"})
    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    prompt_output = _activity_output(activities["prompt"])
    consumer_output = _activity_output(activities["consumer"])

    assert prompt_output["response_data"] == _ALL_FIELDS_SUBMISSION
    downstream_values = consumer_output["stdout_json"]
    assert downstream_values == _ALL_FIELDS_SUBMISSION
    assert isinstance(downstream_values["number_value"], int)
    assert isinstance(downstream_values["multi_select_value"], list)
    assert isinstance(downstream_values["checkbox_value"], bool)
    assert isinstance(downstream_values["date_value"], dict)


def test_required_field_error_leaves_prompt_available_for_valid_response(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """A missing required value is rejected, while an optional number may be omitted."""
    execution_id, prompt = start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        first_project_id,
        workflow_name_prefix=_FORM_PROMPT_WORKFLOW_NAME_PREFIX,
        description=_FORM_PROMPT_WORKFLOW_DESCRIPTION,
        track_execution=form_prompt_execution_cleanup,
        producer_output={},
        form_fields=[
            {"type": "text", "value_name": "required_text", "label": "Required text", "required": True},
            {"type": "number", "value_name": "optional_number", "label": "Optional number", "required": False},
        ],
    )
    prompt_id = UUID(str(prompt.id))

    rejected = submit_form_prompt(syntara_api, prompt_id, {"required_text": ""})
    _assert_validation_error(rejected, field_name="required_text", expected_detail="required")
    assert get_form_prompt(syntara_api, prompt_id).status == FormPromptStatus.PENDING

    accepted = submit_form_prompt(syntara_api, prompt_id, {"required_text": "provided"})
    assert accepted.status_code == HTTPStatus.OK

    assert_consumer_completed(syntara_api, execution_id)
    final = wait_for_activity_outputs(syntara_api, execution_id, {"prompt"})
    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    prompt_output = _activity_output(activities["prompt"])
    assert prompt_output["response_data"] == {"required_text": "provided"}


def test_unparseable_number_string_is_rejected(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """A string that cannot represent a number is rejected for a number field."""
    _, prompt = start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        first_project_id,
        workflow_name_prefix=_FORM_PROMPT_WORKFLOW_NAME_PREFIX,
        description=_FORM_PROMPT_WORKFLOW_DESCRIPTION,
        track_execution=form_prompt_execution_cleanup,
        producer_output={},
        form_fields=[
            {"type": "number", "value_name": "number_value", "label": "Number", "required": True},
            {"type": "checkbox", "value_name": "boolean_value", "label": "Boolean", "required": True},
            {"type": "text", "value_name": "string_value", "label": "String", "required": True},
        ],
    )
    prompt_id = UUID(str(prompt.id))

    response = submit_form_prompt(
        syntara_api,
        prompt_id,
        {"number_value": "abc", "boolean_value": True, "string_value": "hello"},
    )
    _assert_validation_error(response, field_name="number_value", expected_detail="number")
    assert get_form_prompt(syntara_api, prompt_id).status == FormPromptStatus.PENDING


def test_numeric_and_boolean_strings_are_coerced_and_flow_downstream(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Numeric and boolean strings are normalized before downstream execution."""
    execution_id, prompt = start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        first_project_id,
        workflow_name_prefix=_FORM_PROMPT_WORKFLOW_NAME_PREFIX,
        description=_FORM_PROMPT_WORKFLOW_DESCRIPTION,
        track_execution=form_prompt_execution_cleanup,
        producer_output={},
        form_fields=[
            {"type": "number", "value_name": "number_value", "label": "Number", "required": True},
            {"type": "checkbox", "value_name": "boolean_value", "label": "Boolean", "required": True},
            {"type": "text", "value_name": "string_value", "label": "String", "required": True},
        ],
        consumer_code=(
            "import json, os\n"
            "print(json.dumps({"
            "'number_value': json.loads(os.environ['NUMBER_VALUE']), "
            "'boolean_value': json.loads(os.environ['BOOLEAN_VALUE'])"
            "}))"
        ),
        consumer_environment={
            "NUMBER_VALUE": "${prompt.response_data.number_value}",
            "BOOLEAN_VALUE": "${prompt.response_data.boolean_value}",
        },
    )
    prompt_id = UUID(str(prompt.id))

    response = submit_form_prompt(
        syntara_api,
        prompt_id,
        {"number_value": "42", "boolean_value": "true", "string_value": "hello"},
    )
    assert response.status_code == HTTPStatus.OK

    assert_consumer_completed(syntara_api, execution_id)
    final = wait_for_activity_outputs(syntara_api, execution_id, {"prompt", "consumer"})
    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    prompt_output = _activity_output(activities["prompt"])
    consumer_output = _activity_output(activities["consumer"])
    normalized = prompt_output["response_data"]
    assert normalized == {"number_value": 42.0, "boolean_value": True, "string_value": "hello"}
    assert isinstance(normalized["number_value"], float)
    assert normalized["boolean_value"] is True
    assert consumer_output["stdout_json"] == {"number_value": 42.0, "boolean_value": True}


def test_native_number_boolean_and_string_types_are_accepted(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Native JSON types are accepted and the form prompt resumes the workflow."""
    execution_id, prompt = start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        first_project_id,
        workflow_name_prefix=_FORM_PROMPT_WORKFLOW_NAME_PREFIX,
        description=_FORM_PROMPT_WORKFLOW_DESCRIPTION,
        track_execution=form_prompt_execution_cleanup,
        producer_output={},
        form_fields=[
            {"type": "number", "value_name": "number_value", "label": "Number", "required": True},
            {"type": "checkbox", "value_name": "boolean_value", "label": "Boolean", "required": True},
            {"type": "text", "value_name": "string_value", "label": "String", "required": True},
        ],
    )
    prompt_id = UUID(str(prompt.id))

    response = submit_form_prompt(
        syntara_api,
        prompt_id,
        {"number_value": 42, "boolean_value": True, "string_value": "hello"},
    )
    assert response.status_code == HTTPStatus.OK
    assert_consumer_completed(syntara_api, execution_id)


def test_extra_fields_are_rejected_and_defined_fields_can_be_submitted(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Unknown keys are rejected, and a later valid response still resumes work."""
    execution_id, prompt = start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        first_project_id,
        workflow_name_prefix=_FORM_PROMPT_WORKFLOW_NAME_PREFIX,
        description=_FORM_PROMPT_WORKFLOW_DESCRIPTION,
        track_execution=form_prompt_execution_cleanup,
        producer_output={},
        form_fields=[{"type": "number", "value_name": "x", "label": "X", "required": True}],
        consumer_code='import json, os\nprint(json.dumps({"x": int(os.environ["X"])}))',
        consumer_environment={"X": "${prompt.response_data.x}"},
    )
    prompt_id = UUID(str(prompt.id))

    rejected = submit_form_prompt(syntara_api, prompt_id, {"x": 42, "y": 3})
    _assert_validation_error(rejected, field_name="y", expected_detail="Unknown field")
    assert get_form_prompt(syntara_api, prompt_id).status == FormPromptStatus.PENDING

    accepted = submit_form_prompt(syntara_api, prompt_id, {"x": 42})
    assert accepted.status_code == HTTPStatus.OK
    assert_consumer_completed(syntara_api, execution_id)
    final = wait_for_activity_outputs(syntara_api, execution_id, {"prompt", "consumer"})
    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    prompt_output = _activity_output(activities["prompt"])
    consumer_output = _activity_output(activities["consumer"])
    assert prompt_output["response_data"] == {"x": 42}
    assert consumer_output["stdout_json"] == {"x": 42}
    assert final.status == ExecutionStatus.COMPLETED
