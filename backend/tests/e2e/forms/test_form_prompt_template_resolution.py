"""E2E coverage for resolving form-prompt templates from workflow output."""

import json
from collections.abc import Callable
from http import HTTPStatus
from uuid import UUID

import pytest
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import WorkflowCreate, WorkflowRead
from syntara_api_client.models.activity_data_output_data_type_0 import ActivityDataOutputDataType0
from syntara_api_client.models.form_prompt_list_read import FormPromptListRead
from syntara_api_client.models.form_prompt_status import FormPromptStatus

from ._helpers import (
    assert_and_get_with_502_skip,
    assert_consumer_completed,
    get_form_prompt,
    start_pending_form_prompt,
    submit_form_prompt,
)
from ._workflows import ENVIRONMENT_RECORDS, dynamic_option_field

pytestmark = [pytest.mark.e2e]

_PRODUCER_OUTPUT = {"environments": ENVIRONMENT_RECORDS, "default_version": "v1.2.3"}


def _start(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    track_execution: Callable[[UUID], None],
    *,
    response_window: int = 600,
) -> tuple[UUID, FormPromptListRead]:
    """Create and start a workflow that resolves both dynamic options and a default."""
    return start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        first_project_id,
        workflow_name_prefix="e2e-form-prompt-template",
        description="E2E: resolve form prompt options and defaults",
        track_execution=track_execution,
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
        response_window=response_window,
    )


def test_dropdown_options_resolved_in_get_response(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
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
    _, prompt_row = _start(
        syntara_api,
        workflow_factory,
        first_project_id,
        form_prompt_execution_cleanup,
        response_window=30,
    )
    prompt = get_form_prompt(syntara_api, UUID(str(prompt_row.id)))
    definition = prompt.form_definition.to_dict()

    environment_field = next(field for field in definition["fields"] if field["value_name"] == "environment")
    assert environment_field["options"]["source"] == "dynamic_resolved"
    assert environment_field["options"]["values"] == ENVIRONMENT_RECORDS
    assert "${" not in json.dumps(definition)


def test_text_field_default_resolved_from_execution_context(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """A text default expression resolves to its native string value.

    Procedure:
    1. Start a workflow whose producer emits a default version.
    2. Wait for the pending prompt and GET the persisted form definition.
    3. Inspect the version field's default.

    Expected:
    - The default is the string v1.2.3, not the source expression.
    """
    _, prompt_row = _start(
        syntara_api,
        workflow_factory,
        first_project_id,
        form_prompt_execution_cleanup,
        response_window=30,
    )
    prompt = get_form_prompt(syntara_api, UUID(str(prompt_row.id)))
    definition = prompt.form_definition.to_dict()

    version_field = next(field for field in definition["fields"] if field["value_name"] == "version")
    assert version_field["default"] == "v1.2.3"
    assert isinstance(version_field["default"], str)


def test_submit_resolved_value_resumes_workflow(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
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
    exec_id, prompt_row = _start(syntara_api, workflow_factory, first_project_id, form_prompt_execution_cleanup)
    submitted = {"environment": "prod", "version": "v9.9.9"}
    response = submit_form_prompt(syntara_api, UUID(str(prompt_row.id)), submitted)
    assert response.status_code == HTTPStatus.OK

    final = assert_consumer_completed(syntara_api, exec_id)
    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    prompt_activity = activities["prompt"]
    assert isinstance(prompt_activity.output_data, ActivityDataOutputDataType0)
    output = prompt_activity.output_data.to_dict()
    assert output["response_data"] == submitted
    assert output["outcome"] == "submitted"


def test_pending_prompt_listed_for_execution(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
) -> None:
    """The list endpoint filters pending form prompts by execution.

    Procedure:
    1. Start a workflow and wait for its pending form prompt.
    2. List prompts filtered by the execution ID and pending status.

    Expected:
    - Exactly one prompt is returned, with the expected node ID and status.
    """
    exec_id, _ = _start(
        syntara_api,
        workflow_factory,
        first_project_id,
        form_prompt_execution_cleanup,
        response_window=30,
    )
    listed = assert_and_get_with_502_skip(
        syntara_api.form_prompts.list(
            execution_id=exec_id,
            status=FormPromptStatus.PENDING,
        )
    )

    assert len(listed.resources) == 1
    assert listed.resources[0].prompt_node_id == "prompt"
    assert listed.resources[0].status == FormPromptStatus.PENDING
