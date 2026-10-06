"""E2E coverage for resolving form-prompt templates from workflow output."""

import json
from collections.abc import Callable
from http import HTTPStatus
from typing import cast
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import poll_execution, poll_for_pending_form_prompt
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import ExecutionCreate, WorkflowCreate, WorkflowRead
from syntara_api_client.models.activity_data_output_data_type_0 import ActivityDataOutputDataType0
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.form_prompt_list_read import FormPromptListRead
from syntara_api_client.models.form_prompt_read import FormPromptRead
from syntara_api_client.models.form_prompt_status import FormPromptStatus
from syntara_api_client.models.form_prompt_submit_request import FormPromptSubmitRequest
from syntara_api_client.models.form_prompt_submit_request_response_data import (
    FormPromptSubmitRequestResponseData,
)
from syntara_api_client.types import Response, UnexpectedResponseException

from ._workflows import ENVIRONMENT_RECORDS, dynamic_option_field, producer_prompt_consumer_workflow

pytestmark = [pytest.mark.e2e]

_PROMPT_POLL_TIMEOUT = 60
_EXECUTION_POLL_TIMEOUT = 90

_PRODUCER_OUTPUT = {"environments": ENVIRONMENT_RECORDS, "default_version": "v1.2.3"}


def _assert_and_get_with_502_skip[ResponseT](response: Response[ResponseT]) -> ResponseT:
    """Get a parsed response, skipping only on a transient Bad Gateway."""
    try:
        return response.assert_and_get()
    except UnexpectedResponseException as exc:
        if exc.status_code == HTTPStatus.BAD_GATEWAY:
            pytest.skip("Backend returned 502 Bad Gateway - transient infrastructure issue")
        raise


def _start(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
) -> tuple[UUID, FormPromptListRead]:
    """Create and start a workflow that resolves both dynamic options and a default."""
    name = unique_name("e2e-form-prompt-template")
    workflow = workflow_factory(
        WorkflowCreate(
            name=name,
            description="E2E: resolve form prompt options and defaults",
            workflow_definition=producer_prompt_consumer_workflow(
                name,
                producer_output=_PRODUCER_OUTPUT,
                form_fields=[
                    dynamic_option_field("environment", "${producer.stdout_json.environments}"),
                    {
                        "type": "text",
                        "value_name": "version",
                        "label": "Version",
                        "required": True,
                        "default": "${producer.stdout_json.default_version}",
                    },
                ],
            ),
            project_id=first_project_id,
        )
    )
    execution = syntara_api.executions.create(
        body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger")
    ).assert_and_get()
    exec_id = UUID(str(execution.id))
    prompt = poll_for_pending_form_prompt(syntara_api, exec_id, timeout=_PROMPT_POLL_TIMEOUT)
    return exec_id, prompt


def _get_prompt(syntara_api: SyntaraApiRegistry, prompt_id: UUID) -> FormPromptRead:
    return cast(
        "FormPromptRead",
        _assert_and_get_with_502_skip(syntara_api.form_prompts.get(form_prompt_id=prompt_id)),
    )


def test_dropdown_options_resolved_in_get_response(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
) -> None:
    """Resolved dropdown options are persisted with the form prompt.

    Procedure:
    1. Start a workflow whose producer emits environment records.
    2. Wait for the pending form prompt and GET its full representation.
    3. Inspect the materialized options and ensure no template expression remains.

    Expected:
    - Options use the dynamic_resolved source and retain the producer's order.
    - The persisted definition contains no unresolved expression.
    """
    _, prompt_row = _start(syntara_api, workflow_factory, first_project_id)
    prompt = _get_prompt(syntara_api, UUID(str(prompt_row.id)))
    definition = prompt.form_definition.to_dict()

    environment_field = next(field for field in definition["fields"] if field["value_name"] == "environment")
    assert environment_field["options"]["source"] == "dynamic_resolved"
    assert environment_field["options"]["values"] == ENVIRONMENT_RECORDS
    assert "${" not in json.dumps(definition)


def test_text_field_default_resolved_from_execution_context(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
) -> None:
    """A text default expression resolves to its native string value.

    Procedure:
    1. Start a workflow whose producer emits a default version.
    2. Wait for the pending prompt and GET the persisted form definition.
    3. Inspect the version field's default.

    Expected:
    - The default is the string v1.2.3, not the source expression.
    """
    _, prompt_row = _start(syntara_api, workflow_factory, first_project_id)
    prompt = _get_prompt(syntara_api, UUID(str(prompt_row.id)))
    definition = prompt.form_definition.to_dict()

    version_field = next(field for field in definition["fields"] if field["value_name"] == "version")
    assert version_field["default"] == "v1.2.3"
    assert isinstance(version_field["default"], str)


def test_submit_resolved_value_resumes_workflow(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
) -> None:
    """Submitting values accepted by the resolved form resumes downstream work.

    Procedure:
    1. Start the workflow and wait for its pending form prompt.
    2. Submit a valid environment and version.
    3. Poll execution to terminal and inspect activity results.

    Expected:
    - The submit returns 200 and execution completes.
    - The consumer completes and the prompt activity records the submission.
    """
    exec_id, prompt_row = _start(syntara_api, workflow_factory, first_project_id)
    submitted = {"environment": "prod", "version": "v9.9.9"}
    response = syntara_api.form_prompts.submit(
        form_prompt_id=UUID(str(prompt_row.id)),
        body=FormPromptSubmitRequest(response_data=FormPromptSubmitRequestResponseData.from_dict(submitted)),
    )
    if response.status_code == HTTPStatus.BAD_GATEWAY:
        pytest.skip("Backend returned 502 Bad Gateway - transient infrastructure issue")
    assert response.status_code == HTTPStatus.OK

    final = poll_execution(syntara_api, str(exec_id), timeout=_EXECUTION_POLL_TIMEOUT)
    assert final.status == ExecutionStatus.COMPLETED, (
        f"Expected COMPLETED after form submission, got {final.status}: {final.error_details}"
    )
    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    assert activities["consumer"].status == "completed"
    prompt_activity = activities["prompt"]
    assert isinstance(prompt_activity.output_data, ActivityDataOutputDataType0)
    output = prompt_activity.output_data.to_dict()
    assert output["response_data"] == submitted
    assert output["outcome"] == "submitted"


def test_pending_prompt_listed_for_execution(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
) -> None:
    """The list endpoint filters pending form prompts by execution.

    Procedure:
    1. Start a workflow and wait for its pending form prompt.
    2. List prompts filtered by the execution ID and pending status.

    Expected:
    - Exactly one prompt is returned, with the expected node ID and status.
    """
    exec_id, _ = _start(syntara_api, workflow_factory, first_project_id)
    listed = _assert_and_get_with_502_skip(
        syntara_api.form_prompts.list(
            execution_id=exec_id,
            status=FormPromptStatus.PENDING,
        )
    )

    assert len(listed.resources) == 1
    assert listed.resources[0].prompt_node_id == "prompt"
    assert listed.resources[0].status == FormPromptStatus.PENDING
