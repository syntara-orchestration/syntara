"""End-to-end tests for Form Trigger submission validation and workflow input flow."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import WorkflowCreate, WorkflowRead

from ._helpers import (
    activities_by_id,
    activity_output,
    assert_consumer_completed,
    assert_form_validation_error,
    assert_no_executions_for_workflow,
    create_form_trigger_workflow,
    submit_form_trigger,
    submit_form_trigger_and_track,
    wait_for_activity_outputs,
)
from ._workflows import ALL_SUPPORTED_FORM_FIELDS

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
_ALL_FIELDS_EXPECTED_TYPES: dict[str, type[Any]] = {
    "text_value": str,
    "textarea_value": str,
    "number_value": int,
    "masked_value": str,
    "dropdown_value": str,
    "multi_select_value": list,
    "checkbox_value": bool,
    "date_value": str,
    "email_value": str,
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


def test_coerced_submission_reaches_both_trigger_namespaces(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: WorkflowFactory,
    first_project_id: UUID,
    form_execution_cleanup: Callable[[UUID], None],
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
    workflow = create_form_trigger_workflow(
        workflow_factory,
        first_project_id,
        name_prefix=_FORM_TRIGGER_NAME_PREFIX,
        description=_FORM_TRIGGER_DESCRIPTION,
        form_fields=_SIMPLE_FORM_FIELDS,
        consumer_code=_CONSUMER_CODE,
        consumer_environment=_CONSUMER_ENVIRONMENT,
    )
    execution = submit_form_trigger_and_track(
        syntara_api,
        workflow,
        _VALID_SIMPLE_SUBMISSION,
        form_execution_cleanup,
    )
    execution_id = UUID(str(execution.id))

    assert execution.input_data is not None
    execution_input = execution.input_data.to_dict()
    assert execution_input == {
        "required_text": "test submission",
        "count": 42.0,
        "contact": "Bob@example.com",
    }
    assert type(execution_input["count"]) is float
    assert_consumer_completed(syntara_api, execution_id)
    final = wait_for_activity_outputs(syntara_api, execution_id, {"form", "consumer"})
    activities = activities_by_id(final)
    form_response_data = activity_output(activities["form"])["response_data"]
    assert form_response_data == execution_input
    assert type(form_response_data["count"]) is float
    downstream = activity_output(activities["consumer"])["stdout_json"]
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
    form_execution_cleanup: Callable[[UUID], None],
) -> None:
    """All supported Form Trigger field types retain their expected JSON shape.

    Procedure:
    1. Create a workflow with all supported Form Trigger field types.
    2. Submit a valid value for every field.
    3. Inspect persisted input, trigger output, and consumer output.

    Expected:
    - Every field value is present and has the expected JSON type at each hop.
    """
    workflow = create_form_trigger_workflow(
        workflow_factory,
        first_project_id,
        name_prefix=_FORM_TRIGGER_NAME_PREFIX,
        description=_FORM_TRIGGER_DESCRIPTION,
        form_fields=ALL_SUPPORTED_FORM_FIELDS,
        consumer_code=_ALL_FIELDS_CONSUMER_CODE,
        consumer_environment=_ALL_FIELDS_ENVIRONMENT,
    )
    execution = submit_form_trigger_and_track(
        syntara_api,
        workflow,
        _ALL_FIELDS_SUBMISSION,
        form_execution_cleanup,
    )
    execution_id = UUID(str(execution.id))
    expected_values = {**_ALL_FIELDS_SUBMISSION, "date_value": "2026-02-14"}
    assert execution.input_data is not None
    execution_input = execution.input_data.to_dict()
    assert execution_input == expected_values

    assert_consumer_completed(syntara_api, execution_id)
    final = wait_for_activity_outputs(syntara_api, execution_id, {"form", "consumer"})
    activities = activities_by_id(final)
    form_response_data = activity_output(activities["form"])["response_data"]
    assert form_response_data == expected_values
    downstream = activity_output(activities["consumer"])["stdout_json"]
    assert downstream == expected_values
    for values in (execution_input, form_response_data, downstream):
        for field_name, expected_type in _ALL_FIELDS_EXPECTED_TYPES.items():
            assert type(values[field_name]) is expected_type, (
                f"Expected {field_name} to have type {expected_type.__name__}, got {type(values[field_name]).__name__}"
            )


def test_invalid_submission_starts_no_execution_then_valid_submission_completes(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: WorkflowFactory,
    first_project_id: UUID,
    form_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Invalid Form Trigger values are rejected without creating an execution."""
    workflow = create_form_trigger_workflow(
        workflow_factory,
        first_project_id,
        name_prefix=_FORM_TRIGGER_NAME_PREFIX,
        description=_FORM_TRIGGER_DESCRIPTION,
        form_fields=_SIMPLE_FORM_FIELDS,
        consumer_code=_CONSUMER_CODE,
        consumer_environment=_CONSUMER_ENVIRONMENT,
    )

    rejected = submit_form_trigger(
        syntara_api,
        workflow,
        {"count": "42", "contact": "bob@example.com"},
    )
    assert_form_validation_error(
        rejected,
        expected_fields={"required_text"},
        expected_details={"This field is required"},
    )
    assert_no_executions_for_workflow(syntara_api, UUID(str(workflow.id)))

    accepted = submit_form_trigger_and_track(
        syntara_api,
        workflow,
        _VALID_SIMPLE_SUBMISSION,
        form_execution_cleanup,
    )
    assert_consumer_completed(syntara_api, UUID(str(accepted.id)))
