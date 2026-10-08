"""E2E coverage for form-prompt timeouts, option resolution, and form-service activity failures."""

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e.helpers import poll_execution
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import (
    ExecutionRead,
    ExecutionStatus,
    FormPromptRead,
    FormPromptStatus,
    WorkflowCreate,
    WorkflowRead,
)
from syntara_api_client.models.activity_data_output_data_type_0 import ActivityDataOutputDataType0

from syntara.core.constants import FieldLimits

from ._helpers import (
    EXECUTION_POLL_TIMEOUT,
    assert_and_get_with_502_skip,
    create_form_prompt_execution,
    get_form_prompt,
    start_pending_form_prompt,
)
from ._workflows import dynamic_option_field

if TYPE_CHECKING:
    from syntara_api_client.models.activity_data import ActivityData

pytestmark = [pytest.mark.e2e]

_DEFAULT_SENTINEL = "DEFAULT_MUST_NOT_PROPAGATE"
_DEFAULT_TEXT_FIELD: dict[str, Any] = {
    "type": "text",
    "value_name": "reason",
    "label": "Reason",
    "required": True,
    "default": _DEFAULT_SENTINEL,
}

_FAILURE_CASES = [
    pytest.param(
        "timeout",
        False,
        None,
        ExecutionStatus.FAILED,
        "none",
        "did not finish within",
        id="timeout-cof-disabled",
    ),
    pytest.param(
        "timeout",
        True,
        "submit",
        ExecutionStatus.COMPLETED_WITH_ERRORS,
        "submitted",
        "did not finish within",
        id="timeout-cof-submit",
    ),
    pytest.param(
        "timeout",
        True,
        "fallback",
        ExecutionStatus.COMPLETED_WITH_ERRORS,
        "fallback",
        "did not finish within",
        id="timeout-cof-fallback",
    ),
    pytest.param(
        "invalid_dynamic_options",
        True,
        "submit",
        ExecutionStatus.COMPLETED_WITH_ERRORS,
        "submitted",
        "expected a list",
        id="invalid-options-cof-submit",
    ),
    pytest.param(
        "form_api_validation",
        False,
        None,
        ExecutionStatus.FAILED,
        "none",
        "HTTP 422",
        id="form-api-422-cof-disabled",
    ),
    pytest.param(
        "form_api_validation",
        True,
        "submit",
        ExecutionStatus.COMPLETED_WITH_ERRORS,
        "submitted",
        "HTTP 422",
        id="form-api-422-cof-submit",
    ),
    pytest.param(
        "form_api_validation",
        True,
        "fallback",
        ExecutionStatus.COMPLETED_WITH_ERRORS,
        "fallback",
        "HTTP 422",
        id="form-api-422-cof-fallback",
    ),
]


def _activities_by_id(final: ExecutionRead) -> dict[str, "ActivityData"]:
    """Index execution activities for readable branch assertions."""
    return {activity.activity_id: activity for activity in (final.activities or [])}


def _assert_failed_prompt_activity(
    final: ExecutionRead,
    *,
    expected_error_fragment: str,
    expect_field_name: str | None = None,
) -> "ActivityData":
    """Assert that the execution API records the form prompt failure and its cause."""
    activities = _activities_by_id(final)
    assert "prompt" in activities, f"'prompt' activity missing: {list(activities)}"
    prompt_activity = activities["prompt"]
    assert prompt_activity.status == "failed", f"Expected failed prompt node, got {prompt_activity.status}"
    assert isinstance(prompt_activity.error_details, str), "Failed prompt activity must include error details"
    assert expected_error_fragment in prompt_activity.error_details, (
        f"Expected prompt error to include {expected_error_fragment!r}; got {prompt_activity.error_details!r}"
    )
    if expect_field_name is not None:
        assert expect_field_name in prompt_activity.error_details, (
            f"Expected prompt error to name {expect_field_name!r}; got {prompt_activity.error_details!r}"
        )
    return prompt_activity


def _assert_route_not_taken(activities: dict[str, "ActivityData"], activity_id: str) -> None:
    """Require unselected route nodes to be absent or explicitly skipped/cancelled."""
    activity = activities.get(activity_id)
    assert activity is None or activity.status in {"skipped", "cancelled"}, (
        f"Unselected route node {activity_id!r} should be absent, skipped, or cancelled; got {activity.status}"
    )


def _assert_selected_route(final: ExecutionRead, *, expected_route: Literal["none", "submitted", "fallback"]) -> None:
    """Assert that only the selected form prompt successor route completed."""
    activities = _activities_by_id(final)
    if expected_route == "none":
        for activity_id in ("consumer", "fallback_handler"):
            _assert_route_not_taken(activities, activity_id)
    elif expected_route == "submitted":
        assert activities.get("consumer") is not None, f"Submitted consumer missing: {list(activities)}"
        assert activities["consumer"].status == "completed"
        _assert_route_not_taken(activities, "fallback_handler")
    else:
        assert activities.get("fallback_handler") is not None, f"Fallback handler missing: {list(activities)}"
        assert activities["fallback_handler"].status == "completed"
        _assert_route_not_taken(activities, "consumer")


def _assert_downstream_received_no_defaults(
    final: ExecutionRead,
    *,
    expected_route: Literal["submitted", "fallback"],
) -> None:
    """Inspect the selected script's captured form-prompt namespace for response data."""
    activities = _activities_by_id(final)
    capture_node_id = "consumer" if expected_route == "submitted" else "fallback_handler"
    capture_activity = activities[capture_node_id]
    assert isinstance(capture_activity.output_data, ActivityDataOutputDataType0), (
        f"{capture_node_id} did not expose output data: {capture_activity.output_data!r}"
    )
    output = capture_activity.output_data.to_dict()
    captured_prompt = output.get("stdout_json")
    assert isinstance(captured_prompt, dict), f"Expected JSON form-prompt capture, got {captured_prompt!r}"
    assert captured_prompt.get("status") == "failed", (
        f"Downstream capture should preserve failed form-prompt status: {captured_prompt!r}"
    )
    response_data = captured_prompt.get("response_data")
    assert response_data is None or response_data == {}, (
        f"A failed form prompt without a response must not provide response_data: {response_data!r}"
    )
    assert _DEFAULT_SENTINEL not in json.dumps(captured_prompt), (
        f"Form field default leaked into downstream input: {captured_prompt!r}"
    )


def _assert_default_is_configured(prompt: FormPromptRead) -> None:
    """Ensure the timeout test actually created a form with a default value."""
    form_definition = prompt.form_definition.to_dict()
    fields = form_definition.get("fields", [])
    reason_field = next((field for field in fields if field.get("value_name") == "reason"), None)
    assert reason_field is not None, f"Defaulted reason field missing: {fields!r}"
    assert reason_field.get("default") == _DEFAULT_SENTINEL


def _assert_no_prompt_row(syntara_api: SyntaraApiRegistry, exec_id: UUID) -> None:
    """Verify a pre-creation form prompt failure did not persist a form prompt."""
    listed = assert_and_get_with_502_skip(syntara_api.form_prompts.list(execution_id=exec_id, limit=5))
    assert not listed.resources, f"Expected no form prompt row, found {len(listed.resources)}"


def _start_failure_case(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    track_execution: Callable[[UUID], None],
    *,
    failure_kind: Literal["timeout", "invalid_dynamic_options", "form_api_validation"],
    continue_on_failure: bool,
    fallback_decision: Literal["submit", "fallback"] | None,
) -> tuple[UUID, UUID | None]:
    """Create the selected failure workflow and return its execution and optional prompt IDs."""
    form_fields = [dict(_DEFAULT_TEXT_FIELD)]
    producer_output: dict[str, object] = {}
    submit_label: str | None = None
    if failure_kind == "invalid_dynamic_options":
        producer_output = {"environments": "production"}
        form_fields.append(dynamic_option_field("environment", "${producer.stdout_json.environments}"))
    elif failure_kind == "form_api_validation":
        producer_output = {"submit_label": "x" * (FieldLimits.FORM_SUBMIT_LABEL_MAX_LENGTH + 1)}
        submit_label = "${producer.stdout_json.submit_label}"

    workflow_name_prefix = f"e2e-form-prompt-failure-{failure_kind}"
    description = "E2E: form prompt failure and continue-on-failure routing"
    if failure_kind == "timeout":
        exec_id, prompt_row = start_pending_form_prompt(
            syntara_api,
            workflow_factory,
            first_project_id,
            workflow_name_prefix=workflow_name_prefix,
            description=description,
            track_execution=track_execution,
            producer_output=producer_output,
            form_fields=form_fields,
            continue_on_failure=continue_on_failure,
            response_window=1,
            submit_label=submit_label,
            fallback_decision=fallback_decision,
            capture_form_prompt_result=continue_on_failure,
        )
        prompt_id = UUID(str(prompt_row.id))
        _assert_default_is_configured(get_form_prompt(syntara_api, prompt_id))
        return exec_id, prompt_id

    exec_id = create_form_prompt_execution(
        syntara_api,
        workflow_factory,
        first_project_id,
        workflow_name_prefix=workflow_name_prefix,
        description=description,
        track_execution=track_execution,
        producer_output=producer_output,
        form_fields=form_fields,
        continue_on_failure=continue_on_failure,
        submit_label=submit_label,
        fallback_decision=fallback_decision,
        capture_form_prompt_result=continue_on_failure,
    )
    return exec_id, None


@pytest.mark.parametrize(
    (
        "failure_kind",
        "continue_on_failure",
        "fallback_decision",
        "expected_execution_status",
        "expected_route",
        "expected_error_fragment",
    ),
    _FAILURE_CASES,
)
def test_form_prompt_failures_follow_continue_on_failure_routing(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
    *,
    failure_kind: Literal["timeout", "invalid_dynamic_options", "form_api_validation"],
    continue_on_failure: bool,
    fallback_decision: Literal["submit", "fallback"] | None,
    expected_execution_status: ExecutionStatus,
    expected_route: Literal["none", "submitted", "fallback"],
    expected_error_fragment: str,
) -> None:
    """Cover timeout, option-resolution, and form-service failures with applicable settings.

    Timeout cases wait for a pending form prompt and intentionally do not submit a
    response. Invalid dynamic options fail before the form activity is scheduled.
    An overlong resolved submit label is rejected by the Forms API during the
    Temporal form-creation activity. Existing type-mismatch E2E cases cover
    invalid dynamic options with continue-on-failure disabled and fallback
    routing; this matrix adds the uncovered submitted route.
    """
    exec_id, prompt_id = _start_failure_case(
        syntara_api,
        workflow_factory,
        first_project_id,
        form_prompt_execution_cleanup,
        failure_kind=failure_kind,
        continue_on_failure=continue_on_failure,
        fallback_decision=fallback_decision,
    )

    final = poll_execution(syntara_api, str(exec_id), timeout=EXECUTION_POLL_TIMEOUT)
    assert final.status == expected_execution_status, (
        f"Expected {expected_execution_status} for {failure_kind}, got {final.status}: {final.error_details}"
    )
    prompt_activity = _assert_failed_prompt_activity(
        final,
        expected_error_fragment=expected_error_fragment,
        expect_field_name="environment" if failure_kind == "invalid_dynamic_options" else None,
    )
    _assert_selected_route(final, expected_route=expected_route)

    if prompt_id is not None:
        prompt = get_form_prompt(syntara_api, prompt_id)
        assert prompt.status == FormPromptStatus.EXPIRED
        assert not prompt.response_data, f"Timed-out form prompt unexpectedly has response data: {prompt.response_data}"
    else:
        _assert_no_prompt_row(syntara_api, exec_id)

    if continue_on_failure:
        assert fallback_decision is not None
        route: Literal["submitted", "fallback"] = "submitted" if fallback_decision == "submit" else "fallback"
        _assert_downstream_received_no_defaults(final, expected_route=route)
    else:
        assert prompt_activity.status == "failed"
