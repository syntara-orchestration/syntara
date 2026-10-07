"""E2E coverage for invalid values resolved into form-prompt templates.

Execution polling has a fixed timeout, so a malformed template fails the test
instead of leaving it waiting indefinitely.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e.helpers import poll_execution
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import WorkflowCreate, WorkflowRead
from syntara_api_client.models.execution_status import ExecutionStatus

from ._helpers import EXECUTION_POLL_TIMEOUT, assert_and_get_with_502_skip, create_form_prompt_execution
from ._workflows import dynamic_option_field

if TYPE_CHECKING:
    from syntara_api_client.models.activity_data import ActivityData

pytestmark = [pytest.mark.e2e]


def _start(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    track_execution: Callable[[UUID], None],
    *,
    producer_output: dict[str, object],
    form_fields: list[dict[str, Any]],
    continue_on_failure: bool = False,
) -> UUID:
    """Create and start a workflow with the requested producer and form fields."""
    return create_form_prompt_execution(
        syntara_api,
        workflow_factory,
        first_project_id,
        workflow_name_prefix="e2e-form-prompt-type-mismatch",
        description="E2E: reject incompatible form prompt template values",
        track_execution=track_execution,
        producer_output=producer_output,
        form_fields=form_fields,
        continue_on_failure=continue_on_failure,
    )


def _assert_no_prompt_row(syntara_api: SyntaraApiRegistry, exec_id: UUID) -> None:
    """Verify failed template resolution did not persist a form prompt."""
    listed = assert_and_get_with_502_skip(syntara_api.form_prompts.list(execution_id=exec_id, limit=5))
    assert not listed.resources, (
        f"No form prompt row should be persisted when template resolution fails; found {len(listed.resources)}"
    )


def _assert_prompt_node_failed(
    syntara_api: SyntaraApiRegistry,
    exec_id: UUID,
    *,
    expect_in_error: str,
    expect_field_name: str | None = "environment",
) -> None:
    """Assert the form_prompt node fails before any prompt row is created."""
    final = poll_execution(syntara_api, str(exec_id), timeout=EXECUTION_POLL_TIMEOUT)
    assert final.status == ExecutionStatus.FAILED, (
        f"Expected FAILED on template type mismatch, got {final.status}: {final.error_details}"
    )

    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    assert "prompt" in activities, f"'prompt' activity missing: {list(activities)}"
    node = activities["prompt"]
    assert node.status == "failed", f"prompt node should be failed, got {node.status}"
    assert isinstance(node.error_details, str), "prompt node should include failure details"
    assert expect_in_error in node.error_details, (
        f"error_details should contain {expect_in_error!r}. Got: {node.error_details!r}"
    )
    if expect_field_name is not None:
        assert expect_field_name in node.error_details, (
            f"error_details should identify {expect_field_name!r}. Got: {node.error_details!r}"
        )

    _assert_no_prompt_row(syntara_api, exec_id)


@pytest.mark.parametrize(
    ("producer_output", "expression", "expect_in_error", "expect_field_name"),
    [
        ({"environments": "production"}, "${producer.stdout_json.environments}", "expected a list", "environment"),
        ({"environments": None}, "${producer.stdout_json.environments}", "expected a list", "environment"),
        ({"environments": {"dev": True}}, "${producer.stdout_json.environments}", "expected a list", "environment"),
        (
            {"environments": ["dev", "staging"]},
            "${producer.stdout_json.environments}",
            "must be an object with label key",
            "environment",
        ),
        (
            {"data": {}},
            "${producer.stdout_json.data.environments}",
            "not found",
            None,
        ),
    ],
    ids=[
        "string-for-array",
        "null-for-array",
        "object-for-array",
        "scalar-elements",
        "missing-nested-property",
    ],
)
def test_invalid_dynamic_options_fail_before_prompt_creation(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
    producer_output: dict[str, object],
    expression: str,
    expect_in_error: str,
    expect_field_name: str | None,
) -> None:
    """Invalid dynamic option values fail the prompt node without persisting it.

    Procedure:
    1. Create a producer that emits the parametrized value.
    2. Resolve that value into a dropdown's dynamic options.
    3. Poll execution to terminal and inspect the failed node.

    Expected:
    - Execution and prompt node fail with the corresponding validation detail.
    - No form prompt row is created.
    """
    exec_id = _start(
        syntara_api,
        workflow_factory,
        first_project_id,
        form_prompt_execution_cleanup,
        producer_output=producer_output,
        form_fields=[dynamic_option_field("environment", expression)],
    )

    _assert_prompt_node_failed(
        syntara_api,
        exec_id,
        expect_in_error=expect_in_error,
        expect_field_name=expect_field_name,
    )


def test_array_default_on_text_field_fails_definition_validation(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """An array resolved into a text default fails final form validation.

    Procedure:
    1. Create a producer that emits an array for a text field's default.
    2. Start the workflow and poll execution to terminal.
    3. Inspect the failed prompt node and form-prompt list.

    Expected:
    - The prompt node fails with an error naming the version field.
    - No form prompt row is created.
    """
    exec_id = _start(
        syntara_api,
        workflow_factory,
        first_project_id,
        form_prompt_execution_cleanup,
        producer_output={"env": ["dev", "prod"]},
        form_fields=[
            {
                "type": "text",
                "value_name": "version",
                "label": "Version",
                "required": True,
                "default": "${producer.stdout_json.env}",
            }
        ],
    )

    _assert_prompt_node_failed(
        syntara_api,
        exec_id,
        expect_in_error="version",
        expect_field_name="version",
    )


def test_type_mismatch_with_continue_on_failure_routes_to_fallback(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """A failed prompt node routes to the fallback when continuation is enabled.

    Procedure:
    1. Create a producer whose output is a string instead of an option array.
    2. Enable continue_on_failure and connect a fallback script.
    3. Poll execution to terminal and inspect the activity records.

    Expected:
    - Execution completes with errors and the fallback handler completes.
    - The prompt node fails with the option-resolution error.
    - No form prompt row is created.
    """
    exec_id = _start(
        syntara_api,
        workflow_factory,
        first_project_id,
        form_prompt_execution_cleanup,
        producer_output={"environments": "production"},
        form_fields=[dynamic_option_field("environment", "${producer.stdout_json.environments}")],
        continue_on_failure=True,
    )
    final = poll_execution(syntara_api, str(exec_id), timeout=EXECUTION_POLL_TIMEOUT)
    assert final.status == ExecutionStatus.COMPLETED_WITH_ERRORS, (
        f"Expected COMPLETED_WITH_ERRORS, got {final.status}: {final.error_details}"
    )

    activities: dict[str, ActivityData] = {activity.activity_id: activity for activity in (final.activities or [])}
    assert "fallback_handler" in activities, f"Fallback activity missing from activities: {list(activities)}"
    assert activities["fallback_handler"].status == "completed"
    assert "prompt" in activities, f"'prompt' activity missing: {list(activities)}"
    prompt_activity = activities["prompt"]
    assert prompt_activity.status == "failed"
    assert isinstance(prompt_activity.error_details, str)
    assert "expected a list" in prompt_activity.error_details
    assert "environment" in prompt_activity.error_details

    _assert_no_prompt_row(syntara_api, exec_id)
