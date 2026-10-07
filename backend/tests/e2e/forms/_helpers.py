"""Shared API and workflow helpers for the form-prompt E2E tests."""

from collections.abc import Callable, Mapping
from http import HTTPStatus
from typing import Any, cast
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import poll_execution, poll_for_pending_form_prompt
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import (
    ExecutionCreate,
    ExecutionRead,
    FormPromptListRead,
    FormPromptRead,
    FormPromptSubmitRequest,
    FormPromptSubmitRequestResponseData,
    WorkflowCreate,
    WorkflowRead,
)
from syntara_api_client.models.error_data import ErrorData
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.types import Response, UnexpectedResponseException

from ._workflows import producer_prompt_consumer_workflow

PROMPT_POLL_TIMEOUT = 60
EXECUTION_POLL_TIMEOUT = 90


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


def create_form_prompt_execution(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    *,
    workflow_name_prefix: str,
    description: str,
    producer_output: Mapping[str, object],
    form_fields: list[dict[str, Any]],
    continue_on_failure: bool = False,
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
                continue_on_failure=continue_on_failure,
            ),
            project_id=first_project_id,
        )
    )
    execution = syntara_api.executions.create(
        body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger")
    ).assert_and_get()
    return UUID(str(execution.id))


def start_pending_form_prompt(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    *,
    workflow_name_prefix: str,
    description: str,
    producer_output: Mapping[str, object],
    form_fields: list[dict[str, Any]],
    continue_on_failure: bool = False,
) -> tuple[UUID, FormPromptListRead]:
    """Start a workflow and wait until its form prompt is pending."""
    exec_id = create_form_prompt_execution(
        syntara_api,
        workflow_factory,
        first_project_id,
        workflow_name_prefix=workflow_name_prefix,
        description=description,
        producer_output=producer_output,
        form_fields=form_fields,
        continue_on_failure=continue_on_failure,
    )
    prompt = poll_for_pending_form_prompt(syntara_api, exec_id, timeout=PROMPT_POLL_TIMEOUT)
    return exec_id, prompt
