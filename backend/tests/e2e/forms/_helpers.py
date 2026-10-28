"""Shared API and workflow helpers for form-prompt and Form Trigger E2E tests."""

import json
import time
from collections.abc import Callable, Collection, Mapping
from http import HTTPStatus
from typing import Any, Literal, cast
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import (
    TERMINAL_STATUSES,
    _retry_api_call,
    poll_execution,
    poll_for_pending_form_prompt,
)
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import (
    ExecutionCreate,
    ExecutionRead,
    FormPromptListRead,
    FormPromptRead,
    FormPromptStatus,
    FormPromptSubmitRequest,
    FormPromptSubmitRequestResponseData,
    WorkflowCreate,
    WorkflowRead,
)
from syntara_api_client.models.activity_data import ActivityData
from syntara_api_client.models.activity_data_output_data_type_0 import ActivityDataOutputDataType0
from syntara_api_client.models.error_data import ErrorData
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.types import Response, UnexpectedResponseException, Unset

from ._workflows import (
    DEFAULT_CONSUMER_CODE,
    form_trigger_consumer_workflow,
    producer_prompt_consumer_workflow,
)

PROMPT_POLL_TIMEOUT = 60
EXECUTION_POLL_TIMEOUT = 90
ACTIVITY_OUTPUT_POLL_TIMEOUT = 30
# Cancellation is accepted before Temporal and the activity monitor reach terminal state.
CANCEL_POLL_TIMEOUT = 120
FORM_TRIGGER_NODE_ID = "form"
CONSUMER_NODE_ID = "consumer"


def activity_output(activity: ActivityData) -> dict[str, Any]:
    """Return an activity's object-shaped output data."""
    output_data = activity.output_data
    assert isinstance(output_data, ActivityDataOutputDataType0)
    return output_data.to_dict()


def activities_by_id(execution: ExecutionRead) -> dict[str, ActivityData]:
    """Index an execution's activities by activity_id."""
    return {activity.activity_id: activity for activity in (execution.activities or [])}


def create_form_trigger_workflow(
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    *,
    name_prefix: str,
    description: str,
    form_fields: list[dict[str, Any]],
    consumer_code: str = DEFAULT_CONSUMER_CODE,
    consumer_environment: Mapping[str, str] | None = None,
) -> WorkflowRead:
    """Create a uniquely named Form Trigger → script workflow."""
    name = unique_name(name_prefix)
    return workflow_factory(
        WorkflowCreate(
            name=name,
            description=description,
            project_id=first_project_id,
            workflow_definition=form_trigger_consumer_workflow(
                name,
                form_fields=form_fields,
                consumer_code=consumer_code,
                consumer_environment=consumer_environment,
            ),
        )
    )


def submit_form_trigger(
    syntara_api: SyntaraApiRegistry,
    workflow: WorkflowRead,
    input_data: dict[str, Any],
) -> Response[Any]:
    """POST a Form Trigger submission, skipping only on a transient Bad Gateway."""
    response = syntara_api.executions.create(
        body=ExecutionCreate.from_dict(
            {
                "workflow_id": str(workflow.id),
                "trigger_node_id": FORM_TRIGGER_NODE_ID,
                "input_data": input_data,
            }
        )
    )
    if response.status_code == HTTPStatus.BAD_GATEWAY:
        pytest.skip("Backend returned 502 Bad Gateway - transient infrastructure issue")
    return response


def submit_form_trigger_and_track(
    syntara_api: SyntaraApiRegistry,
    workflow: WorkflowRead,
    input_data: dict[str, Any],
    track_execution: Callable[[UUID], None],
) -> ExecutionRead:
    """Submit valid data, assert 201, and register the execution for cleanup."""
    response = submit_form_trigger(syntara_api, workflow, input_data)
    assert response.status_code == HTTPStatus.CREATED, (
        f"Expected 201 Created, got {response.status_code}: {response.content!r}"
    )
    execution = cast("ExecutionRead", assert_and_get_with_502_skip(response))
    track_execution(UUID(str(execution.id)))
    return execution


def assert_form_validation_error(
    response: Response[Any],
    *,
    expected_fields: Collection[str],
    expected_details: Collection[str] = (),
) -> dict[str, Any]:
    """Assert a 422 FORM_VALIDATION_ERROR naming each field, and return the problem."""
    problem = assert_problem_response(
        response,
        expected_status=HTTPStatus.UNPROCESSABLE_ENTITY,
        expected_code="FORM_VALIDATION_ERROR",
    )
    detail = problem["detail"]
    for field in expected_fields:
        assert f"{field}: " in detail, f"Expected field {field!r} in validation detail: {detail!r}"
    for expected_detail in expected_details:
        assert expected_detail in detail, f"Expected {expected_detail!r} in validation detail: {detail!r}"
    return problem


def assert_no_executions_for_workflow(syntara_api: SyntaraApiRegistry, workflow_id: UUID) -> None:
    """A rejected Form Trigger submission must leave the workflow with no executions."""
    executions = assert_and_get_with_502_skip(
        syntara_api.executions.list(additional_params={"workflow_id": str(workflow_id)}, limit=100)
    )
    assert not executions.resources, f"Rejected submission created executions: {executions.resources!r}"


def assert_consumer_completed(syntara_api: SyntaraApiRegistry, exec_id: UUID) -> ExecutionRead:
    """Wait for the workflow to finish and assert its submitted consumer ran."""
    final = poll_execution(syntara_api, str(exec_id), timeout=EXECUTION_POLL_TIMEOUT)
    assert final.status == ExecutionStatus.COMPLETED, (
        f"Expected COMPLETED after form submission, got {final.status}: {final.error_details}"
    )
    activities = activities_by_id(final)
    assert CONSUMER_NODE_ID in activities, f"Consumer activity missing: {list(activities)}"
    assert activities[CONSUMER_NODE_ID].status == "completed"
    return final


def cancel_form_execution(syntara_api: SyntaraApiRegistry, exec_id: UUID) -> None:
    """Cancel a still-active form execution and wait for its terminal state."""
    execution = _retry_api_call(lambda: syntara_api.executions.get(execution_id=exec_id)).assert_and_get()
    if execution.status in TERMINAL_STATUSES:
        return

    response = _retry_api_call(lambda: syntara_api.executions.cancel(execution_id=exec_id))
    if response.status_code == HTTPStatus.ACCEPTED:
        poll_execution(syntara_api, str(exec_id), timeout=CANCEL_POLL_TIMEOUT)
        return
    if response.status_code == HTTPStatus.CONFLICT:
        # The workflow may have completed between the status read and cancel request.
        execution = _retry_api_call(lambda: syntara_api.executions.get(execution_id=exec_id)).assert_and_get()
        if execution.status in TERMINAL_STATUSES:
            return
    response.assert_and_get()


def assert_and_get_with_502_skip[ResponseT](response: Response[ResponseT]) -> ResponseT:
    """Parse a response, skipping only on a transient Bad Gateway."""
    try:
        return response.assert_and_get()
    except UnexpectedResponseException as exc:
        if exc.status_code == HTTPStatus.BAD_GATEWAY:
            pytest.skip("Backend returned 502 Bad Gateway - transient infrastructure issue")
        raise


def wait_for_activity_outputs(
    syntara_api: SyntaraApiRegistry,
    exec_id: UUID,
    activity_ids: Collection[str],
    *,
    timeout: int = ACTIVITY_OUTPUT_POLL_TIMEOUT,
) -> ExecutionRead:
    """Poll an execution until the requested activities expose output data."""
    deadline = time.monotonic() + timeout
    missing = set(activity_ids)
    while time.monotonic() < deadline:
        execution = cast(
            "ExecutionRead",
            assert_and_get_with_502_skip(syntara_api.executions.get(execution_id=exec_id, include="activities")),
        )
        activities = {activity.activity_id: activity for activity in (execution.activities or [])}
        missing = {
            activity_id
            for activity_id in activity_ids
            if (activity := activities.get(activity_id)) is None
            or activity.output_data is None
            or isinstance(activity.output_data, Unset)
        }
        if not missing:
            return execution
        time.sleep(1)

    pytest.fail(f"Execution {exec_id} did not expose output data for activities: {sorted(missing)} within {timeout}s")


def assert_problem_response(
    response: Response[Any],
    *,
    expected_status: HTTPStatus,
    expected_code: str,
) -> dict[str, Any]:
    """Return RFC 9457 problem details after checking status and code.

    Error responses intentionally use the raw body because the generated API
    client parses problem extensions differently across endpoint schemas.
    """
    if response.status_code == HTTPStatus.BAD_GATEWAY:
        pytest.skip("Backend returned 502 Bad Gateway - transient infrastructure issue")

    assert response.status_code == expected_status, (
        f"Expected {expected_status.value} {expected_status.phrase}, got {response.status_code}: {response.content!r}"
    )
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("application/problem+json"), (
        f"Expected application/problem+json, got {content_type!r}"
    )

    problem = cast("dict[str, Any]", json.loads(response.content))
    assert problem["code"] == expected_code, f"Expected code {expected_code}, got {problem}"
    return problem


def assert_definition_invalid(response: Response[Any]) -> dict[str, Any]:
    """Assert an RFC 9457 workflow-definition validation problem and return it."""
    problem = assert_problem_response(
        response,
        expected_status=HTTPStatus.UNPROCESSABLE_ENTITY,
        expected_code="WORKFLOW_DEFINITION_INVALID",
    )
    assert problem["type"]
    assert problem["title"] == "Workflow Definition Invalid"
    assert problem["detail"]
    assert problem["retryable"] is False
    assert problem["instance"]

    validation_result = problem["validation_result"]
    assert validation_result["is_valid"] is False
    assert validation_result["error_count"] >= 1
    assert validation_result["findings"]
    assert any(finding.get("node_id") == "prompt" for finding in validation_result["findings"])
    return problem


def get_form_prompt(syntara_api: SyntaraApiRegistry, prompt_id: UUID) -> FormPromptRead:
    """GET a form prompt, skipping only on a transient Bad Gateway."""
    return cast(
        "FormPromptRead",
        assert_and_get_with_502_skip(syntara_api.form_prompts.get(form_prompt_id=prompt_id)),
    )


def wait_for_form_prompt_status(
    syntara_api: SyntaraApiRegistry,
    prompt_id: UUID,
    expected_status: FormPromptStatus,
    *,
    timeout: int = CANCEL_POLL_TIMEOUT,
) -> FormPromptRead:
    """Poll until a form prompt reaches the expected status."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        prompt = get_form_prompt(syntara_api, prompt_id)
        if prompt.status == expected_status:
            return prompt
        time.sleep(1)

    pytest.fail(f"Form prompt {prompt_id} did not reach {expected_status} within {timeout}s")


def assert_responders_configured(
    prompt: FormPromptRead,
    *,
    expected_users: list[str] | None = None,
    expected_groups: list[str] | None = None,
) -> None:
    """Guard against silently dropped responder names.

    The resolver filters out usernames and group names it cannot resolve, so a
    typo could leave the prompt unrestricted and invert negative assertions.
    """
    assert isinstance(prompt.responder_users, list), "Form prompt response omitted responder_users"
    assert isinstance(prompt.responder_groups, list), "Form prompt response omitted responder_groups"
    assert sorted(user.username for user in prompt.responder_users) == sorted(expected_users or [])
    assert sorted(group.name for group in prompt.responder_groups) == sorted(expected_groups or [])


def submit_form_prompt(
    syntara_api: SyntaraApiRegistry,
    prompt_id: UUID,
    response_data: dict[str, Any],
) -> Response[ErrorData | FormPromptRead]:
    """Submit prompt data, skipping only on a transient Bad Gateway."""
    response = syntara_api.form_prompts.submit(
        form_prompt_id=prompt_id,
        body=FormPromptSubmitRequest(response_data=FormPromptSubmitRequestResponseData.from_dict(response_data)),
    )
    if response.status_code == HTTPStatus.BAD_GATEWAY:
        pytest.skip("Backend returned 502 Bad Gateway - transient infrastructure issue")
    return response


def assert_forbidden(response: Response[Any], *, expected_code: str) -> None:
    """Assert an RFC 9457 403 carrying a specific error code."""
    assert response.status_code == HTTPStatus.FORBIDDEN, (
        f"Expected 403, got {response.status_code}: {response.content!r}"
    )
    problem = json.loads(response.content)
    assert problem["code"] == expected_code, f"Expected code {expected_code}, got {problem}"


def assert_prompt_not_consumed(
    syntara_api: SyntaraApiRegistry,
    exec_id: UUID,
    prompt_id: UUID,
) -> None:
    """A rejected submission must leave the prompt live and workflow paused."""
    prompt = get_form_prompt(syntara_api, prompt_id)
    assert prompt.status == FormPromptStatus.PENDING
    assert not prompt.response_data
    assert not prompt.responded_by

    execution = assert_and_get_with_502_skip(syntara_api.executions.get(execution_id=exec_id, include="activities"))
    assert execution.status not in TERMINAL_STATUSES, (
        f"Execution must not advance on a rejected submission; got {execution.status}"
    )
    activities = activities_by_id(execution)
    assert activities.get(CONSUMER_NODE_ID) is None or activities[CONSUMER_NODE_ID].status != "completed"


def wait_for_form_prompt_paused(
    syntara_api: SyntaraApiRegistry,
    exec_id: UUID,
    *,
    prompt_node_id: str = "prompt",
    timeout: int = 60,
) -> ExecutionRead:
    """Wait until the execution is paused on the form-prompt activity."""
    for _ in range(timeout):
        execution = assert_and_get_with_502_skip(syntara_api.executions.get(execution_id=exec_id, include="activities"))
        activities = {activity.activity_id: activity for activity in (execution.activities or [])}
        prompt_activity = activities.get(prompt_node_id)
        if execution.status == ExecutionStatus.PAUSED and prompt_activity is not None:
            assert prompt_activity.status == "waiting", (
                f"Expected {prompt_node_id} activity waiting, got {prompt_activity.status}"
            )
            return execution
        if execution.status in TERMINAL_STATUSES:
            pytest.fail(f"Execution became terminal before {prompt_node_id} paused: {execution.status}")
        time.sleep(1)

    pytest.fail(f"Execution {exec_id} did not pause on {prompt_node_id} within {timeout}s")


def create_form_prompt_execution(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    *,
    workflow_name_prefix: str,
    description: str,
    track_execution: Callable[[UUID], None],
    producer_output: Mapping[str, object],
    form_fields: list[dict[str, Any]],
    consumer_code: str = DEFAULT_CONSUMER_CODE,
    consumer_environment: Mapping[str, str] | None = None,
    continue_on_failure: bool = False,
    response_window: int = 600,
    submit_label: str | None = None,
    fallback_decision: Literal["submit", "fallback"] | None = None,
    capture_form_prompt_result: bool = False,
    responder_users: list[str] | None = None,
    responder_groups: list[str] | None = None,
) -> UUID:
    """Create and start a workflow containing a form prompt, returning its execution ID."""
    name = unique_name(workflow_name_prefix)
    workflow = workflow_factory(
        WorkflowCreate(
            name=name,
            description=description,
            workflow_definition=producer_prompt_consumer_workflow(
                name,
                producer_output=producer_output,
                form_fields=form_fields,
                consumer_code=consumer_code,
                consumer_environment=consumer_environment,
                continue_on_failure=continue_on_failure,
                response_window=response_window,
                submit_label=submit_label,
                fallback_decision=fallback_decision,
                capture_form_prompt_result=capture_form_prompt_result,
                responder_users=responder_users,
                responder_groups=responder_groups,
            ),
            project_id=first_project_id,
        )
    )
    execution = cast(
        "ExecutionRead",
        assert_and_get_with_502_skip(
            syntara_api.executions.create(body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger"))
        ),
    )
    exec_id = UUID(str(execution.id))
    track_execution(exec_id)
    return exec_id


def start_pending_form_prompt(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    *,
    workflow_name_prefix: str,
    description: str,
    track_execution: Callable[[UUID], None],
    producer_output: Mapping[str, object],
    form_fields: list[dict[str, Any]],
    consumer_code: str = DEFAULT_CONSUMER_CODE,
    consumer_environment: Mapping[str, str] | None = None,
    continue_on_failure: bool = False,
    response_window: int = 600,
    submit_label: str | None = None,
    fallback_decision: Literal["submit", "fallback"] | None = None,
    capture_form_prompt_result: bool = False,
    responder_users: list[str] | None = None,
    responder_groups: list[str] | None = None,
) -> tuple[UUID, FormPromptListRead]:
    """Start a workflow and wait until its form prompt is pending."""
    exec_id = create_form_prompt_execution(
        syntara_api,
        workflow_factory,
        first_project_id,
        workflow_name_prefix=workflow_name_prefix,
        description=description,
        track_execution=track_execution,
        producer_output=producer_output,
        form_fields=form_fields,
        consumer_code=consumer_code,
        consumer_environment=consumer_environment,
        continue_on_failure=continue_on_failure,
        response_window=response_window,
        submit_label=submit_label,
        fallback_decision=fallback_decision,
        capture_form_prompt_result=capture_form_prompt_result,
        responder_users=responder_users,
        responder_groups=responder_groups,
    )
    prompt = poll_for_pending_form_prompt(syntara_api, exec_id, timeout=PROMPT_POLL_TIMEOUT)
    return exec_id, prompt
