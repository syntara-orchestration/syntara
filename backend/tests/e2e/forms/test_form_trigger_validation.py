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
    DEFAULT_CONSUMER_CODE,
    REQUIRED_AND_OPTIONAL_FIELDS,
    SCALAR_TYPE_FIELDS,
    SINGLE_NUMBER_FIELD,
)

pytestmark = [pytest.mark.e2e]

_NAME_PREFIX = "e2e-form-trigger-validation"
_DESCRIPTION = "E2E: validate Form Trigger submissions"
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


def test_missing_required_fields_are_rejected_then_valid_submission_runs(
    syntara_api: SyntaraApiRegistry,
    form_trigger_workflow: FormTriggerWorkflowBuilder,
    form_execution_cleanup: Callable[[UUID], None],
) -> None:
    """Missing required values fail together; optional fields may be omitted.

    Procedure:
    1. Submit empty values for the required text and email fields.
    2. Verify both required errors and confirm no execution was created.
    3. Submit valid required values while omitting the optional number.

    Expected:
    - The invalid request returns 422 with both required fields identified.
    - The valid request completes with no optional_number key in response_data.
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
def test_type_mismatches_are_rejected(
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


def test_numeric_and_boolean_strings_are_coerced_and_reach_the_consumer(
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


def test_extra_fields_are_rejected_then_defined_fields_submit_cleanly(
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
