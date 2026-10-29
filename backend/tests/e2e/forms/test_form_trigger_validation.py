"""E2E coverage for Form Trigger input validation and coercion.

These tests pin the backend behavior: validation problems return 422, numeric and
boolean strings are coerced, and unknown fields are rejected.
"""

from collections.abc import Callable, Mapping
from typing import Any, Protocol
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
from ._workflows import (
    ALL_SUPPORTED_FORM_FIELDS,
    DEFAULT_CONSUMER_CODE,
    REQUIRED_AND_OPTIONAL_FIELDS,
    SCALAR_TYPE_FIELDS,
    SINGLE_NUMBER_FIELD,
)

pytestmark = [pytest.mark.e2e]

_NAME_PREFIX = "e2e-form-trigger-validation"
_DESCRIPTION = "E2E: validate Form Trigger submissions"
_ALL_FIELDS_SUBMISSION: dict[str, Any] = {
    "text_value": "short answer",
    "textarea_value": "longer answer\nwith a second line",
    "number_value": 42,
    "masked_value": "masked-entry",
    "dropdown_value": "blue",
    "multi_select_value": ["red", "blue"],
    "checkbox_value": True,
    "date_value": {"date": "2026-02-14"},
    "email_value": "Bob@Example.COM",
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
    "date_value": os.environ["DATE_VALUE"],
    "email_value": os.environ["EMAIL_VALUE"],
}))
"""

_SCALAR_CONSUMER_ENVIRONMENT = {
    "NUMBER_VALUE": "${form.response_data.number_value}",
    "BOOLEAN_VALUE": "${form.response_data.boolean_value}",
    "STRING_VALUE": "${form.response_data.string_value}",
}
_SCALAR_CONSUMER_CODE = """
import json
import os

print(json.dumps({
    "number_value": json.loads(os.environ["NUMBER_VALUE"]),
    "boolean_value": json.loads(os.environ["BOOLEAN_VALUE"]),
    "string_value": os.environ["STRING_VALUE"],
}))
"""
_SINGLE_NUMBER_CONSUMER_ENVIRONMENT = {"FORM_X": "${form.response_data.x}"}
_SINGLE_NUMBER_CONSUMER_CODE = """
import json
import os

print(json.dumps({"x": json.loads(os.environ["FORM_X"])}))
"""


class FormTriggerWorkflowBuilder(Protocol):
    """Typed callable for constructing the workflows used by this module."""

    def __call__(
        self,
        form_fields: list[dict[str, Any]],
        *,
        consumer_code: str = DEFAULT_CONSUMER_CODE,
        consumer_environment: Mapping[str, str] | None = None,
    ) -> WorkflowRead: ...


@pytest.fixture
def form_trigger_workflow(
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
) -> FormTriggerWorkflowBuilder:
    """Build a Form Trigger workflow for this module with the given fields."""

    def _build(
        form_fields: list[dict[str, Any]],
        *,
        consumer_code: str = DEFAULT_CONSUMER_CODE,
        consumer_environment: Mapping[str, str] | None = None,
    ) -> WorkflowRead:
        return create_form_trigger_workflow(
            workflow_factory,
            first_project_id,
            name_prefix=_NAME_PREFIX,
            description=_DESCRIPTION,
            form_fields=form_fields,
            consumer_code=consumer_code,
            consumer_environment=consumer_environment,
        )

    return _build


def test_all_supported_form_fields_reach_downstream_consumer(
    syntara_api: SyntaraApiRegistry,
    form_trigger_workflow: FormTriggerWorkflowBuilder,
    form_execution_cleanup: Callable[[UUID], None],
) -> None:
    """All supported Form Trigger field types retain their expected JSON shape.

    Procedure:
    1. Create a workflow with all supported Form Trigger field types.
    2. Submit a valid value for every field, including a mixed-case email address.
    3. Inspect persisted input, trigger output, and consumer output.

    Expected:
    - Every field value is present and has the expected JSON type at each hop.
    - The email domain is normalized in stored input and downstream output.
    """
    workflow = form_trigger_workflow(
        ALL_SUPPORTED_FORM_FIELDS,
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
    expected_values = {
        **_ALL_FIELDS_SUBMISSION,
        "date_value": "2026-02-14",
        "email_value": "Bob@example.com",
    }
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


def test_required_field_errors_allow_valid_submission(
    syntara_api: SyntaraApiRegistry,
    form_trigger_workflow: FormTriggerWorkflowBuilder,
    form_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Missing required values fail together; omitted optional numeric fields resolve to null.

    Procedure:
    1. Submit empty values for the required text and email fields.
    2. Verify both required errors and confirm no execution was created.
    3. Submit valid required values while omitting the optional number.

    Expected:
    - The invalid request returns 422 with both required fields identified.
    - The valid request completes with ``optional_number`` set to ``None`` in response_data.
    """
    workflow = form_trigger_workflow(REQUIRED_AND_OPTIONAL_FIELDS)

    rejected = submit_form_trigger(
        syntara_api,
        workflow,
        {"required_text": "", "required_email": None, "optional_number": 7},
    )
    assert_form_validation_error(
        rejected,
        expected_fields={"required_text", "required_email"},
        expected_details={"This field is required"},
    )
    assert_no_executions_for_workflow(syntara_api, UUID(str(workflow.id)))

    accepted = submit_form_trigger_and_track(
        syntara_api,
        workflow,
        {"required_text": "provided", "required_email": "tester@example.com"},
        form_execution_cleanup,
    )
    execution_id = UUID(str(accepted.id))
    assert_consumer_completed(syntara_api, execution_id)
    final = wait_for_activity_outputs(syntara_api, execution_id, {"form", "consumer"})
    activities = activities_by_id(final)
    assert activity_output(activities["form"])["response_data"] == {
        "required_text": "provided",
        "required_email": "tester@example.com",
        "optional_number": None,
    }


@pytest.mark.parametrize(
    ("bad_field", "bad_value", "expected_detail"),
    [
        pytest.param("number_value", "abc", "Must be a valid number string", id="non-numeric-string-for-number"),
        pytest.param(
            "number_value",
            True,
            "Boolean values are not accepted as numbers",
            id="boolean-for-number",
        ),
        pytest.param(
            "boolean_value",
            "maybe",
            "Must be a boolean value",
            id="non-boolean-string-for-boolean",
        ),
        pytest.param("string_value", 42, "Must be a string, got int", id="number-for-string"),
    ],
)
def test_invalid_field_values_are_rejected(
    syntara_api: SyntaraApiRegistry,
    form_trigger_workflow: FormTriggerWorkflowBuilder,
    bad_field: str,
    bad_value: object,
    expected_detail: str,
) -> None:
    """Reject values that cannot be coerced to their Form Trigger field type.

    Procedure:
    1. Create a workflow with required number, checkbox, and text fields.
    2. Replace one otherwise-valid value with a type or format mismatch.
    3. Submit the values and check the field-specific validation problem.

    Expected:
    - The API returns 422 FORM_VALIDATION_ERROR for each mismatch.
    - No execution is created for a rejected submission.
    """
    workflow = form_trigger_workflow(SCALAR_TYPE_FIELDS)
    input_data: dict[str, Any] = {
        "number_value": 42,
        "boolean_value": True,
        "string_value": "hello",
    }
    input_data[bad_field] = bad_value

    rejected = submit_form_trigger(syntara_api, workflow, input_data)
    assert_form_validation_error(
        rejected,
        expected_fields={bad_field},
        expected_details={expected_detail},
    )
    assert_no_executions_for_workflow(syntara_api, UUID(str(workflow.id)))


def test_numeric_and_boolean_strings_are_coerced_and_reach_consumer(
    syntara_api: SyntaraApiRegistry,
    form_trigger_workflow: FormTriggerWorkflowBuilder,
    form_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Numeric and boolean strings are coerced and accepted by the backend.

    Procedure:
    1. Submit numeric and boolean values as strings.
    2. Inspect persisted input, trigger output, and consumer output.

    Expected:
    - The request succeeds with 201 and values are normalized to float and bool.
    - The consumer receives the same normalized data.
    """
    workflow = form_trigger_workflow(
        SCALAR_TYPE_FIELDS,
        consumer_code=_SCALAR_CONSUMER_CODE,
        consumer_environment=_SCALAR_CONSUMER_ENVIRONMENT,
    )
    execution = submit_form_trigger_and_track(
        syntara_api,
        workflow,
        {"number_value": "42", "boolean_value": "true", "string_value": "hello"},
        form_execution_cleanup,
    )
    expected_values = {"number_value": 42.0, "boolean_value": True, "string_value": "hello"}
    assert execution.input_data is not None
    execution_input = execution.input_data.to_dict()
    assert execution_input == expected_values
    assert type(execution_input["number_value"]) is float
    assert isinstance(execution_input["boolean_value"], bool)

    execution_id = UUID(str(execution.id))
    assert_consumer_completed(syntara_api, execution_id)
    final = wait_for_activity_outputs(syntara_api, execution_id, {"form", "consumer"})
    activities = activities_by_id(final)
    form_response_data = activity_output(activities["form"])["response_data"]
    downstream = activity_output(activities["consumer"])["stdout_json"]
    assert form_response_data == expected_values
    assert downstream == expected_values
    assert type(form_response_data["number_value"]) is float
    assert type(downstream["number_value"]) is float
    assert isinstance(form_response_data["boolean_value"], bool)
    assert isinstance(downstream["boolean_value"], bool)


def test_unknown_fields_are_rejected_then_defined_fields_are_accepted(
    syntara_api: SyntaraApiRegistry,
    form_trigger_workflow: FormTriggerWorkflowBuilder,
    form_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Unknown field names are rejected while defined fields still submit cleanly.

    Procedure:
    1. Submit a defined number and one unknown key.
    2. Verify the unknown field is rejected and no execution is created.
    3. Submit only the defined field and inspect the trigger and consumer outputs.

    Expected:
    - The invalid request returns 422 and identifies the unknown key.
    - The valid request completes with only the defined value.
    """
    workflow = form_trigger_workflow(
        SINGLE_NUMBER_FIELD,
        consumer_code=_SINGLE_NUMBER_CONSUMER_CODE,
        consumer_environment=_SINGLE_NUMBER_CONSUMER_ENVIRONMENT,
    )
    rejected = submit_form_trigger(syntara_api, workflow, {"x": 42, "y": 3})
    assert_form_validation_error(
        rejected,
        expected_fields={"y"},
        expected_details={"Unknown field"},
    )
    assert_no_executions_for_workflow(syntara_api, UUID(str(workflow.id)))

    execution = submit_form_trigger_and_track(
        syntara_api,
        workflow,
        {"x": 42},
        form_execution_cleanup,
    )
    execution_id = UUID(str(execution.id))
    assert_consumer_completed(syntara_api, execution_id)
    final = wait_for_activity_outputs(syntara_api, execution_id, {"form", "consumer"})
    activities = activities_by_id(final)
    assert activity_output(activities["form"])["response_data"] == {"x": 42}
    assert activity_output(activities["consumer"])["stdout_json"] == {"x": 42}
