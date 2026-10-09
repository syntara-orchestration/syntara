"""API E2E coverage for importing and exporting form-prompt workflows."""

from __future__ import annotations

import copy
import json
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import poll_for_pending_form_prompt
from orchestrator_test_sdk.factories import add_to_group
from syntara_api_client.models import ExecutionCreate, WorkflowCreate, WorkflowRead
from syntara_api_client.models.activity_data_output_data_type_0 import ActivityDataOutputDataType0
from syntara_api_client.models.validation_result import ValidationResult
from syntara_api_client.models.workflow_read_with_version import WorkflowReadWithVersion

from ._helpers import (
    PROMPT_POLL_TIMEOUT,
    assert_consumer_completed,
    assert_responders_configured,
    get_form_prompt,
    submit_form_prompt,
    wait_for_form_prompt_paused,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from orchestrator_test_sdk.factories import GroupFactory
    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models import FormPromptListRead
    from syntara_api_client.models.user_info import UserInfo

pytestmark = [pytest.mark.e2e]

_OPTION_RECORDS = [
    {"display_label": "Development", "value": "dev"},
    {"display_label": "Production", "value": "prod"},
]
_SUBMITTED_VALUES = {
    "reason": "approved for release",
    "retries": 3,
    "static_environment": "staging",
    "dynamic_environment": "prod",
}


@pytest.fixture(scope="module")
def form_prompt_responder(
    admin_api: SyntaraApiRegistry,
    syntara_admin_user: UserInfo,
    create_group: GroupFactory,
) -> dict[str, str]:
    """Provide a resolvable user and group for imported prompt responder lists."""
    group_id, group_name = create_group(admin_api, "form-prompt-import")
    add_to_group(admin_api, group_id, UUID(syntara_admin_user.id))
    return {"username": syntara_admin_user.username, "group_name": group_name}


def _handcrafted_workflow_definition(
    name: str,
    responder: dict[str, str],
    *,
    prompt_node_id: str = "form_prompt",
) -> dict[str, Any]:
    """Build a complete workflow definition with a form prompt and explicit layout."""
    producer_output = {"options": _OPTION_RECORDS}
    producer_code = f"print({json.dumps(producer_output)!r})"
    consumer_code = 'import os\nprint(os.environ["FORM_PROMPT_RESULT"])'

    return {
        "schema_version": "2.0.0",
        "name": name,
        "description": "Form prompt import/export E2E workflow",
        "triggers": [
            {
                "id": "trigger",
                "type": "manual_trigger",
                "name": "Manual Start",
                "parameters": {},
                "position": {"x": 80, "y": 180},
            }
        ],
        "nodes": [
            {
                "id": "producer",
                "type": "script",
                "name": "Option Producer",
                "parameters": {"language": "python", "code": producer_code},
                "position": {"x": 320, "y": 180},
            },
            {
                "id": prompt_node_id,
                "type": "form_prompt",
                "name": "Release Details",
                "parameters": {
                    "message": "Provide release details",
                    "form_definition": {
                        "fields": [
                            {
                                "type": "text",
                                "value_name": "reason",
                                "label": "Reason",
                                "required": True,
                                "default": "Routine release",
                            },
                            {
                                "type": "number",
                                "value_name": "retries",
                                "label": "Retry count",
                                "required": True,
                                "default": 2,
                            },
                            {
                                "type": "dropdown",
                                "value_name": "static_environment",
                                "label": "Static environment",
                                "required": True,
                                "default": "staging",
                                "options": {
                                    "source": "static",
                                    "values": [
                                        {"display_label": "Staging", "value": "staging"},
                                        {"display_label": "Production", "value": "prod"},
                                    ],
                                },
                            },
                            {
                                "type": "dropdown",
                                "value_name": "dynamic_environment",
                                "label": "Dynamic environment",
                                "required": True,
                                "default": "dev",
                                "options": {
                                    "source": "dynamic",
                                    "expression": "${producer.stdout_json.options}",
                                    "label_key": "display_label",
                                    "value_key": "value",
                                },
                            },
                        ]
                    },
                    "response_window": 30,
                    "fallback_decision": "submit",
                    "responder_users": [responder["username"]],
                    "responder_groups": [responder["group_name"]],
                    "submit_label": "Submit release details",
                },
                "settings": {"continue_on_failure": True},
                "position": {"x": 560, "y": 180},
            },
            {
                "id": "consumer",
                "type": "script",
                "name": "Use Submitted Values",
                "parameters": {
                    "language": "python",
                    "code": consumer_code,
                    "environment": {"FORM_PROMPT_RESULT": f"${{{prompt_node_id}}}"},
                },
                "position": {"x": 800, "y": 100},
            },
            {
                "id": "fallback_handler",
                "type": "script",
                "name": "Use Defaults",
                "parameters": {"language": "bash", "code": 'echo "default path executed"'},
                "position": {"x": 800, "y": 280},
            },
        ],
        "edges": [
            {"from": "trigger", "to": "producer"},
            {"from": "producer", "to": prompt_node_id},
            {"from": prompt_node_id, "to": "consumer", "from_port": "submitted"},
            {"from": prompt_node_id, "to": "fallback_handler", "from_port": "fallback"},
        ],
    }


def _definition_with_invalid_form_prompt(
    name: str,
    *,
    fields: list[dict[str, Any]],
    response_window: int = 30,
) -> dict[str, Any]:
    """Build a structurally valid graph around intentionally invalid prompt parameters."""
    definition = _handcrafted_workflow_definition(
        name,
        {"username": "not-used", "group_name": "not-used"},
    )
    prompt = next(node for node in definition["nodes"] if node["type"] == "form_prompt")
    prompt["parameters"]["form_definition"]["fields"] = fields
    prompt["parameters"]["response_window"] = response_window
    prompt["parameters"]["responder_users"] = []
    prompt["parameters"]["responder_groups"] = []
    return definition


def _create_workflow(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    *,
    name: str,
    project_id: UUID,
    workflow_definition: dict[str, Any],
    is_import: bool,
) -> WorkflowRead:
    """POST a workflow definition and register the created row for teardown."""
    body = WorkflowCreate.from_dict(
        {
            "name": name,
            "description": "Form prompt workflow import/export E2E",
            "workflow_definition": workflow_definition,
            "project_id": str(project_id),
            "is_import": is_import,
        }
    )
    response = syntara_api.workflows.create(body=body)
    assert response.status_code == HTTPStatus.CREATED, (
        f"Expected 201 when creating {name!r}, got {response.status_code}: {response.content!r}"
    )
    workflow = cast("WorkflowRead", response.assert_and_get())
    cleanup_workflows.append(UUID(str(workflow.id)))
    return workflow


def _export_definition(syntara_api: SyntaraApiRegistry, workflow_id: UUID) -> dict[str, Any]:
    """Export version 1 and parse the JSON attachment body."""
    response = syntara_api.workflows.export_version(workflow_id=workflow_id, version=1)
    assert response.status_code == HTTPStatus.OK, (
        f"Expected JSON export 200, got {response.status_code}: {response.content!r}"
    )
    assert response.headers["content-type"].split(";", maxsplit=1)[0] == "application/json"
    assert "attachment" in response.headers["content-disposition"]
    definition = json.loads(response.content)
    assert isinstance(definition, dict)
    return definition


def _get_workflow_definition(syntara_api: SyntaraApiRegistry, workflow_id: UUID) -> dict[str, Any]:
    """GET a workflow and return the current version's serialized definition."""
    response = syntara_api.workflows.get(workflow_id=workflow_id)
    assert response.status_code == HTTPStatus.OK, (
        f"Expected workflow GET 200, got {response.status_code}: {response.content!r}"
    )
    workflow = cast("WorkflowReadWithVersion", response.assert_and_get())
    return workflow.version.workflow_definition.to_dict()


def _node_by_id(definition: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(node for node in definition["nodes"] if node["id"] == node_id)


def _start_imported_workflow(
    syntara_api: SyntaraApiRegistry,
    workflow_id: UUID,
    track_execution: Callable[[UUID], None],
) -> tuple[UUID, FormPromptListRead]:
    """Execute an imported definition and wait for its form prompt to become pending."""
    response = syntara_api.executions.create(body=ExecutionCreate(workflow_id=workflow_id, trigger_node_id="trigger"))
    assert response.status_code == HTTPStatus.CREATED, (
        f"Expected execution create 201, got {response.status_code}: {response.content!r}"
    )
    execution = response.assert_and_get()
    execution_id = UUID(str(execution.id))
    track_execution(execution_id)

    prompt_row = poll_for_pending_form_prompt(syntara_api, execution_id, timeout=PROMPT_POLL_TIMEOUT)
    wait_for_form_prompt_paused(
        syntara_api,
        execution_id,
        prompt_node_id="form_prompt",
        timeout=PROMPT_POLL_TIMEOUT,
    )
    return execution_id, prompt_row


def _assert_prompt_and_execution_outputs(
    syntara_api: SyntaraApiRegistry,
    execution_id: UUID,
    prompt_id: UUID,
    *,
    responder: dict[str, str],
) -> None:
    """Verify runtime materialization, response persistence, and downstream data flow."""
    prompt = get_form_prompt(syntara_api, prompt_id)
    assert_responders_configured(
        prompt,
        expected_users=[responder["username"]],
        expected_groups=[responder["group_name"]],
    )
    prompt_definition = prompt.form_definition.to_dict()
    runtime_fields = {field["value_name"]: field for field in prompt_definition["fields"]}
    assert runtime_fields["static_environment"]["options"]["source"] == "static"
    assert runtime_fields["dynamic_environment"]["options"]["source"] == "dynamic_resolved"
    assert runtime_fields["dynamic_environment"]["options"]["values"] == _OPTION_RECORDS
    assert "${" not in json.dumps(prompt_definition)

    final = assert_consumer_completed(syntara_api, execution_id)
    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    prompt_activity = activities["form_prompt"]
    assert isinstance(prompt_activity.output_data, ActivityDataOutputDataType0)
    assert prompt_activity.output_data.to_dict()["response_data"] == _SUBMITTED_VALUES

    consumer_activity = activities["consumer"]
    assert isinstance(consumer_activity.output_data, ActivityDataOutputDataType0)
    captured_prompt = consumer_activity.output_data.to_dict().get("stdout_json")
    assert isinstance(captured_prompt, dict), f"Expected captured form-prompt output, got {captured_prompt!r}"
    assert captured_prompt.get("response_data") == _SUBMITTED_VALUES


def test_form_prompt_workflow_export_import_round_trip_executes(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    form_prompt_execution_cleanup: Callable[[UUID], None],
    form_prompt_responder: dict[str, str],
    first_project_id: UUID,
) -> None:
    """Export, delete, import, and execute a workflow containing a configured form prompt.

    Procedure:
    1. Create a workflow with form fields, response window, responder lists, and node positions.
    2. Export its first version and verify JSON format and the complete definition.
    3. Delete the source, import the definition under a new workflow name, and GET it.
    4. Execute the imported workflow, submit the pending prompt, and verify completion/data flow.

    Expected:
    - The JSON export and imported definition preserve form prompt configuration and layout.
    - The imported workflow pauses for a prompt, accepts the responder's submission, and completes.
    """
    source_name = unique_name("e2e-form-prompt-export-source")
    source_definition = _handcrafted_workflow_definition(source_name, form_prompt_responder)
    source = _create_workflow(
        syntara_api,
        cleanup_workflows,
        name=source_name,
        project_id=first_project_id,
        workflow_definition=source_definition,
        is_import=False,
    )
    assert source.has_validation_issues is False

    exported_definition = _export_definition(syntara_api, UUID(str(source.id)))
    assert exported_definition["nodes"] == source_definition["nodes"]
    assert exported_definition["edges"] == source_definition["edges"]

    delete_response = syntara_api.workflows.delete(workflow_id=source.id)
    assert delete_response.status_code == HTTPStatus.NO_CONTENT
    deleted_get = syntara_api.workflows.get(workflow_id=source.id)
    assert deleted_get.status_code == HTTPStatus.NOT_FOUND

    imported_name = unique_name("e2e-form-prompt-export-imported")
    imported_definition = copy.deepcopy(exported_definition)
    imported_definition["name"] = imported_name
    imported = _create_workflow(
        syntara_api,
        cleanup_workflows,
        name=imported_name,
        project_id=first_project_id,
        workflow_definition=imported_definition,
        is_import=True,
    )
    assert imported.has_validation_issues is False

    persisted_definition = _get_workflow_definition(syntara_api, UUID(str(imported.id)))
    assert persisted_definition == imported_definition
    prompt_node = _node_by_id(persisted_definition, "form_prompt")
    parameters = prompt_node["parameters"]
    assert parameters["response_window"] == 30
    assert parameters["responder_users"] == [form_prompt_responder["username"]]
    assert parameters["responder_groups"] == [form_prompt_responder["group_name"]]
    assert parameters["submit_label"] == "Submit release details"
    assert [field["value_name"] for field in parameters["form_definition"]["fields"]] == [
        "reason",
        "retries",
        "static_environment",
        "dynamic_environment",
    ]
    assert {node["id"]: node["position"] for node in persisted_definition["nodes"]} == {
        node["id"]: node["position"] for node in exported_definition["nodes"]
    }
    assert [trigger["position"] for trigger in persisted_definition["triggers"]] == [
        trigger["position"] for trigger in exported_definition["triggers"]
    ]

    execution_id, prompt_row = _start_imported_workflow(
        syntara_api,
        UUID(str(imported.id)),
        form_prompt_execution_cleanup,
    )
    prompt_id = UUID(str(prompt_row.id))
    response = submit_form_prompt(syntara_api, prompt_id, _SUBMITTED_VALUES)
    assert response.status_code == HTTPStatus.OK
    _assert_prompt_and_execution_outputs(
        syntara_api,
        execution_id,
        prompt_id,
        responder=form_prompt_responder,
    )


@pytest.mark.parametrize(
    ("case", "fields", "response_window"),
    [
        pytest.param(
            "unknown_field_type",
            [
                {
                    "type": "unknown_type",
                    "value_name": "reason",
                    "label": "Reason",
                    "required": True,
                }
            ],
            30,
            id="unknown-field-type",
        ),
        pytest.param(
            "missing_field_type",
            [{"value_name": "reason", "label": "Reason", "required": True}],
            30,
            id="missing-field-type",
        ),
        pytest.param(
            "negative_response_window",
            [
                {
                    "type": "text",
                    "value_name": "reason",
                    "label": "Reason",
                    "required": True,
                }
            ],
            -1,
            id="negative-response-window",
        ),
        pytest.param(
            "unknown_template_reference",
            [
                {
                    "type": "dropdown",
                    "value_name": "environment",
                    "label": "Environment",
                    "required": True,
                    "options": {
                        "source": "dynamic",
                        "expression": "${missing_source.stdout_json.options}",
                        "label_key": "display_label",
                        "value_key": "value",
                    },
                }
            ],
            30,
            id="unknown-template-reference",
        ),
    ],
)
def test_form_prompt_import_reports_save_time_validation_findings(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
    case: str,
    fields: list[dict[str, Any]],
    response_window: int,
) -> None:
    """Invalid form prompt definitions are saved with clear validation findings.

    Procedure:
    1. Build a raw import definition with one invalid form prompt field, response window,
       or template reference.
    2. POST the definition with ``is_import=true`` and inspect the save response.
    3. GET the workflow and verify the durable validation flag and submitted definition.

    Expected:
    - Import follows the workflow save contract and returns 201 with validation findings.
    - The validation result identifies the form_prompt node and invalid field/reference.
    - The saved workflow carries ``has_validation_issues=true``.
    """
    name = unique_name(f"e2e-form-prompt-invalid-{case}")
    definition = _definition_with_invalid_form_prompt(
        name,
        fields=fields,
        response_window=response_window,
    )
    body = WorkflowCreate.from_dict(
        {
            "name": name,
            "description": "Invalid form-prompt import validation case",
            "workflow_definition": definition,
            "project_id": str(first_project_id),
            "is_import": True,
        }
    )
    response = syntara_api.workflows.create(body=body)
    assert response.status_code == HTTPStatus.CREATED, (
        f"Expected invalid definition to be saved with findings, got {response.status_code}: {response.content!r}"
    )
    workflow = cast("WorkflowRead", response.assert_and_get())
    cleanup_workflows.append(UUID(str(workflow.id)))

    assert workflow.has_validation_issues is True
    validation_result = workflow.validation_result
    assert isinstance(validation_result, ValidationResult), (
        f"Create response omitted validation_result for {case}: {workflow.to_dict()}"
    )
    assert validation_result.is_valid is False
    assert validation_result.error_count > 0
    findings = validation_result.findings
    assert isinstance(findings, list), f"Create response omitted findings for {case}"

    prompt_findings = [finding for finding in findings if finding.node_id == "form_prompt"]
    assert prompt_findings, f"No form_prompt finding in {validation_result.to_dict()}"
    assert any(finding.severity.value == "error" for finding in prompt_findings)

    if case in {"unknown_field_type", "missing_field_type"}:
        assert any(
            isinstance(finding.field_path, str)
            and "form_definition.fields.0" in finding.field_path
            and ("type" in finding.field_path or "type" in finding.message.lower() or "unknown_type" in finding.message)
            for finding in prompt_findings
        ), f"Field type path missing from {prompt_findings!r}"
    elif case == "negative_response_window":
        assert any(
            isinstance(finding.field_path, str) and "response_window" in finding.field_path
            for finding in prompt_findings
        ), f"response_window path missing from {prompt_findings!r}"
    else:
        assert any(
            finding.category.value == "invalid_reference" and "missing_source" in finding.message
            for finding in prompt_findings
        ), f"Unknown source reference missing from {prompt_findings!r}"

    saved_definition = _get_workflow_definition(syntara_api, UUID(str(workflow.id)))
    assert (
        _node_by_id(saved_definition, "form_prompt")["parameters"]
        == _node_by_id(definition, "form_prompt")["parameters"]
    )
    saved = syntara_api.workflows.get(workflow_id=UUID(str(workflow.id))).assert_and_get()
    assert isinstance(saved, WorkflowReadWithVersion)
    assert saved.has_validation_issues is True


def test_import_renamed_form_prompt_node_preserves_configuration_and_edges(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    form_prompt_responder: dict[str, str],
    first_project_id: UUID,
) -> None:
    """Import applies a form prompt ID/name change and keeps its parameters and connections."""
    source_name = unique_name("e2e-form-prompt-rename-source")
    source_definition = _handcrafted_workflow_definition(
        source_name,
        form_prompt_responder,
        prompt_node_id="form_prompt_1",
    )
    source = _create_workflow(
        syntara_api,
        cleanup_workflows,
        name=source_name,
        project_id=first_project_id,
        workflow_definition=source_definition,
        is_import=False,
    )
    assert source.has_validation_issues is False
    exported_definition = _export_definition(syntara_api, UUID(str(source.id)))

    imported_name = unique_name("e2e-form-prompt-rename-imported")
    imported_definition = copy.deepcopy(exported_definition)
    imported_definition["name"] = imported_name
    source_prompt = _node_by_id(imported_definition, "form_prompt_1")
    original_parameters = copy.deepcopy(source_prompt["parameters"])
    source_prompt["id"] = "user_choice"
    source_prompt["name"] = "User Choice"
    consumer = _node_by_id(imported_definition, "consumer")
    consumer["parameters"]["environment"]["FORM_PROMPT_RESULT"] = "${user_choice}"
    for edge in imported_definition["edges"]:
        for endpoint in ("from", "to"):
            if edge[endpoint] == "form_prompt_1":
                edge[endpoint] = "user_choice"

    imported = _create_workflow(
        syntara_api,
        cleanup_workflows,
        name=imported_name,
        project_id=first_project_id,
        workflow_definition=imported_definition,
        is_import=True,
    )
    assert imported.has_validation_issues is False
    persisted_definition = _get_workflow_definition(syntara_api, UUID(str(imported.id)))

    renamed_prompt = _node_by_id(persisted_definition, "user_choice")
    assert renamed_prompt["name"] == "User Choice"
    assert renamed_prompt["parameters"] == original_parameters
    assert renamed_prompt["position"] == source_prompt["position"]
    assert persisted_definition["edges"] == imported_definition["edges"]
    assert all(
        edge.get(endpoint) != "form_prompt_1" for edge in persisted_definition["edges"] for endpoint in ("from", "to")
    )


def test_import_handcrafted_form_prompt_workflow_executes(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    form_prompt_execution_cleanup: Callable[[UUID], None],
    form_prompt_responder: dict[str, str],
    first_project_id: UUID,
) -> None:
    """Import and execute a complete hand-authored workflow without exporting a source.

    Procedure:
    1. Hand-build a v2 workflow with a producer, form prompt, executor, fields, responder
       configuration, timeout behavior, edges, and positions.
    2. Import it and GET the created workflow to verify the complete definition.
    3. Execute, submit the pending prompt, and verify dynamic options and downstream data flow.

    Expected:
    - The hand-authored definition imports with every node and configuration preserved.
    - The dynamic expression resolves, submission resumes the workflow, and the executor consumes it.
    """
    name = unique_name("e2e-form-prompt-handcrafted")
    definition = _handcrafted_workflow_definition(name, form_prompt_responder)
    workflow = _create_workflow(
        syntara_api,
        cleanup_workflows,
        name=name,
        project_id=first_project_id,
        workflow_definition=definition,
        is_import=True,
    )
    assert workflow.has_validation_issues is False

    persisted_definition = _get_workflow_definition(syntara_api, UUID(str(workflow.id)))
    assert persisted_definition == definition
    assert {node["type"] for node in persisted_definition["nodes"]} == {"script", "form_prompt"}
    prompt_parameters = _node_by_id(persisted_definition, "form_prompt")["parameters"]
    assert prompt_parameters["response_window"] == 30
    assert prompt_parameters["fallback_decision"] == "submit"
    assert prompt_parameters["responder_users"] == [form_prompt_responder["username"]]
    assert prompt_parameters["responder_groups"] == [form_prompt_responder["group_name"]]
    assert prompt_parameters["submit_label"] == "Submit release details"
    assert all("position" in node for node in persisted_definition["nodes"])
    assert all("position" in trigger for trigger in persisted_definition["triggers"])

    execution_id, prompt_row = _start_imported_workflow(
        syntara_api,
        UUID(str(workflow.id)),
        form_prompt_execution_cleanup,
    )
    prompt_id = UUID(str(prompt_row.id))
    response = submit_form_prompt(syntara_api, prompt_id, _SUBMITTED_VALUES)
    assert response.status_code == HTTPStatus.OK
    _assert_prompt_and_execution_outputs(
        syntara_api,
        execution_id,
        prompt_id,
        responder=form_prompt_responder,
    )
