"""E2E coverage for routing from submitted form prompt values."""

from collections.abc import Callable
from http import HTTPStatus
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import poll_execution, poll_for_pending_form_prompt
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import ExecutionCreate, WorkflowCreate, WorkflowDefinition, WorkflowRead
from syntara_api_client.models.activity_data_output_data_type_0 import ActivityDataOutputDataType0
from syntara_api_client.models.execution_status import ExecutionStatus

from ._helpers import assert_and_get_with_502_skip, submit_form_prompt

pytestmark = [pytest.mark.e2e]


def _conditional_form_prompt_workflow_definition(name: str) -> WorkflowDefinition:
    """Build a Form Prompt workflow with red and blue branches."""
    return WorkflowDefinition.from_dict(
        {
            "name": name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "form_prompt",
                    "name": "Wake up, Neo",
                    "type": "form_prompt",
                    "parameters": {
                        "form_definition": {
                            "fields": [
                                {
                                    "type": "dropdown",
                                    "value_name": "color",
                                    "label": "Color",
                                    "required": True,
                                    "options": {
                                        "source": "static",
                                        "values": [
                                            {"display_label": "Red", "value": "red"},
                                            {"display_label": "Blue", "value": "blue"},
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                },
                {
                    "id": "route",
                    "name": "Rabbit Hole",
                    "type": "condition",
                    "parameters": {"condition": "${form_prompt.response_data.color} == 'red'"},
                },
                {
                    "id": "red_executor",
                    "name": "Red Pill",
                    "type": "script",
                    "parameters": {
                        "language": "bash",
                        "code": 'echo "$COLOR selected"',
                        "environment": {"COLOR": "${form_prompt.response_data.color}"},
                    },
                },
                {
                    "id": "blue_executor",
                    "name": "Blue Pill",
                    "type": "script",
                    "parameters": {
                        "language": "bash",
                        "code": 'echo "$COLOR selected"',
                        "environment": {"COLOR": "${form_prompt.response_data.color}"},
                    },
                },
            ],
            "edges": [
                {"from": "trigger", "to": "form_prompt"},
                {"from": "form_prompt", "to": "route", "from_port": "submitted"},
                {"from": "route", "to": "red_executor", "from_port": "true"},
                {"from": "route", "to": "blue_executor", "from_port": "false"},
            ],
        }
    )


@pytest.mark.parametrize(
    ("color", "selected_executor", "other_executor"),
    [
        pytest.param("red", "red_executor", "blue_executor", id="red"),
        pytest.param("blue", "blue_executor", "red_executor", id="blue"),
    ],
)
def test_form_prompt_response_routes_to_selected_executor(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
    form_prompt_execution_cleanup: Callable[[UUID], None],
    color: str,
    selected_executor: str,
    other_executor: str,
) -> None:
    """Route to exactly one executor according to the submitted color."""
    workflow_name = unique_name("e2e-form-prompt-conditional")
    workflow = workflow_factory(
        WorkflowCreate(
            name=workflow_name,
            description="E2E: route based on a form prompt response",
            project_id=first_project_id,
            workflow_definition=_conditional_form_prompt_workflow_definition(workflow_name),
        )
    )
    execution = assert_and_get_with_502_skip(
        syntara_api.executions.create(body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger"))
    )
    execution_id = UUID(str(execution.id))
    form_prompt_execution_cleanup(execution_id)

    pending_prompt = poll_for_pending_form_prompt(syntara_api, execution_id, timeout=60)
    response = submit_form_prompt(syntara_api, UUID(str(pending_prompt.id)), {"color": color})
    assert response.status_code == HTTPStatus.OK

    completed = poll_execution(syntara_api, str(execution_id), timeout=90)
    assert completed.status == ExecutionStatus.COMPLETED, (
        f"Execution for color={color!r} did not complete: {completed.error_details}"
    )
    activities = {activity.activity_id: activity for activity in (completed.activities or [])}
    prompt_output = activities["form_prompt"].output_data
    assert isinstance(prompt_output, ActivityDataOutputDataType0)
    prompt_output_data = prompt_output.to_dict()
    assert prompt_output_data["response_data"] == {"color": color}
    assert "color" not in prompt_output_data
    assert activities["route"].status == "completed"
    selected_activity = activities[selected_executor]
    assert selected_activity.status == "completed"
    assert isinstance(selected_activity.output_data, ActivityDataOutputDataType0)
    assert selected_activity.output_data.to_dict()["stdout"] == f"{color} selected\n"
    other_activity = activities.get(other_executor)
    assert other_activity is None or other_activity.status != "completed"
