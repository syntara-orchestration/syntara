"""Shared API and workflow helpers for the form-prompt E2E tests."""

import json
import time
from collections.abc import Callable, Mapping
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
from syntara_api_client.models.error_data import ErrorData
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.types import Response, UnexpectedResponseException

from ._workflows import DEFAULT_CONSUMER_CODE, producer_prompt_consumer_workflow

PROMPT_POLL_TIMEOUT = 60
EXECUTION_POLL_TIMEOUT = 90
# Cancellation is accepted before Temporal and the activity monitor reach terminal state.
CANCEL_POLL_TIMEOUT = 120


def assert_consumer_completed(syntara_api: SyntaraApiRegistry, exec_id: UUID) -> ExecutionRead:
    """Wait for the workflow to finish and assert its submitted consumer ran."""
    final = poll_execution(syntara_api, str(exec_id), timeout=EXECUTION_POLL_TIMEOUT)
    assert final.status == ExecutionStatus.COMPLETED, (
        f"Expected COMPLETED after form submission, got {final.status}: {final.error_details}"
    )
    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    assert "consumer" in activities, f"Consumer activity missing: {list(activities)}"
    assert activities["consumer"].status == "completed"
    return final


def cancel_form_prompt_execution(syntara_api: SyntaraApiRegistry, exec_id: UUID) -> None:
    """Cancel a still-active form-prompt execution and wait for its terminal state."""
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


def get_form_prompt(syntara_api: SyntaraApiRegistry, prompt_id: UUID) -> FormPromptRead:
    """GET a form prompt, skipping only on a transient Bad Gateway."""
    return cast(
        "FormPromptRead",
        assert_and_get_with_502_skip(syntara_api.form_prompts.get(form_prompt_id=prompt_id)),
    )


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
    activities = {activity.activity_id: activity for activity in (execution.activities or [])}
    assert activities.get("consumer") is None or activities["consumer"].status != "completed"


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
        fallback_decision=fallback_decision,
        capture_form_prompt_result=capture_form_prompt_result,
        responder_users=responder_users,
        responder_groups=responder_groups,
    )
    prompt = poll_for_pending_form_prompt(syntara_api, exec_id, timeout=PROMPT_POLL_TIMEOUT)
    return exec_id, prompt
