"""API E2E coverage for importing and exporting Form Trigger workflows."""

from __future__ import annotations

import copy
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import poll_execution
from syntara_api_client.models import ExecutionCreate, WorkflowCreate, WorkflowRead
from syntara_api_client.models.activity_data_output_data_type_0 import ActivityDataOutputDataType0
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.validation_result import ValidationResult
from syntara_api_client.models.workflow_read_with_version import WorkflowReadWithVersion

from ._helpers import create_workflow, export_workflow_definition, get_workflow_definition

if TYPE_CHECKING:
    from collections.abc import Callable

    from syntara_api_client.api import SyntaraApiRegistry

pytestmark = [pytest.mark.e2e]

_SUBMITTED_VALUES = {
    "reason": "approved for release",
    "retries": 3,
    "static_environment": "staging",
    "dynamic_environment": "prod",
}


def _form_trigger_workflow_definition(name: str, *, trigger_id: str = "form_trigger") -> dict[str, Any]:
    """Build a Form Trigger workflow with one consumer script node."""
    consumer_code = """
import json
import os

print(json.dumps({
    "reason": os.environ["REASON"],
    "retries": int(os.environ["RETRIES"]),
    "static_environment": os.environ["STATIC_ENVIRONMENT"],
    "dynamic_environment": os.environ["DYNAMIC_ENVIRONMENT"],
}))
"""
    return {
        "schema_version": "2.0.0",
        "name": name,
        "description": "Form Trigger import/export E2E workflow",
        "triggers": [
            {
                "id": trigger_id,
                "type": "form_trigger",
                "parameters": {
                    "message": "Provide release details",
                    "form_definition": {
                        "fields": [
                            {
                                "type": "text",
                                "value_name": "reason",
                                "label": "Reason",
                                "required": True,
                            },
                            {
                                "type": "number",
                                "value_name": "retries",
                                "label": "Retry count",
                                "required": True,
                            },
                            {
                                "type": "dropdown",
                                "value_name": "static_environment",
                                "label": "Static environment",
                                "required": True,
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
                                "label": "Environment",
                                "required": True,
                                "options": {
                                    "source": "static",
                                    "values": [
                                        {"display_label": "Development", "value": "dev"},
                                        {"display_label": "Production", "value": "prod"},
                                    ],
                                },
                            },
                        ]
                    },
                },
                "position": {"x": 80, "y": 180},
            }
        ],
        "nodes": [
            {
                "id": "consume",
                "type": "script",
                "name": "Consume Form Values",
                "parameters": {
                    "language": "python",
                    "code": consumer_code,
                    "environment": {
                        "REASON": f"${{{trigger_id}.response_data.reason}}",
                        "RETRIES": f"${{{trigger_id}.response_data.retries}}",
                        "STATIC_ENVIRONMENT": f"${{{trigger_id}.response_data.static_environment}}",
                        "DYNAMIC_ENVIRONMENT": f"${{{trigger_id}.response_data.dynamic_environment}}",
                    },
                },
                "position": {"x": 400, "y": 180},
            }
        ],
        "edges": [{"from": trigger_id, "to": "consume"}],
    }


def _definition_with_invalid_form_trigger(name: str, *, fields: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a structurally valid graph around intentionally invalid trigger fields."""
    definition = _form_trigger_workflow_definition(name)
    definition["triggers"][0]["parameters"]["form_definition"]["fields"] = fields
    definition["nodes"][0]["parameters"] = {"language": "bash", "code": "echo done"}
    return definition


def _submit_form_trigger(
    syntara_api: SyntaraApiRegistry,
    workflow_id: UUID,
    track_execution: Callable[[UUID], None],
) -> UUID:
    """Submit valid values to an imported Form Trigger and track the execution."""
    response = syntara_api.executions.create(
        body=ExecutionCreate.from_dict(
            {
                "workflow_id": str(workflow_id),
                "trigger_node_id": "form_trigger",
                "input_data": _SUBMITTED_VALUES,
            }
        )
    )
    assert response.status_code == HTTPStatus.CREATED, (
        f"Expected execution create 201, got {response.status_code}: {response.content!r}"
    )
    execution = response.assert_and_get()
    execution_id = UUID(str(execution.id))
    track_execution(execution_id)
    return execution_id


def _assert_form_trigger_execution_outputs(syntara_api: SyntaraApiRegistry, execution_id: UUID) -> None:
    """Verify submission output and its data flow through the consumer node."""
    final = poll_execution(syntara_api, str(execution_id), timeout=90)
    assert final.status == ExecutionStatus.COMPLETED, (
        f"Expected COMPLETED after form submission, got {final.status}: {final.error_details}"
    )
    activities = {activity.activity_id: activity for activity in (final.activities or [])}
    trigger_activity = activities["form_trigger"]
    assert isinstance(trigger_activity.output_data, ActivityDataOutputDataType0)
    assert trigger_activity.output_data.to_dict()["response_data"] == _SUBMITTED_VALUES
    consume_activity = activities["consume"]
    assert consume_activity.status == "completed"
    assert isinstance(consume_activity.output_data, ActivityDataOutputDataType0)
    assert consume_activity.output_data.to_dict()["stdout_json"] == _SUBMITTED_VALUES


def test_form_trigger_workflow_export_import_round_trip_executes(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    form_execution_cleanup: Callable[[UUID], None],
    first_project_id: UUID,
) -> None:
    """Export, delete, import, and execute a Form Trigger workflow.

    Procedure:
    1. Create a two-component workflow with a Form Trigger and consumer.
    2. Export version 1, delete the source, and import the definition under a new name.
    3. Submit form values and verify the trigger and consumer outputs.

    Expected:
    - Export and import preserve the form configuration and graph layout.
    - The imported workflow accepts form data and completes the consumer.
    """
    source_name = unique_name("e2e-form-trigger-export-source")
    source_definition = _form_trigger_workflow_definition(source_name)
    source = create_workflow(
        syntara_api,
        cleanup_workflows,
        name=source_name,
        description="Form Trigger workflow import/export E2E",
        project_id=first_project_id,
        workflow_definition=source_definition,
        is_import=False,
    )
    assert source.has_validation_issues is False

    exported_definition = export_workflow_definition(syntara_api, UUID(str(source.id)))
    assert exported_definition["triggers"] == source_definition["triggers"]
    assert exported_definition["nodes"] == source_definition["nodes"]
    assert exported_definition["edges"] == source_definition["edges"]

    delete_response = syntara_api.workflows.delete(workflow_id=source.id)
    assert delete_response.status_code == HTTPStatus.NO_CONTENT
    assert syntara_api.workflows.get(workflow_id=source.id).status_code == HTTPStatus.NOT_FOUND

    imported_name = unique_name("e2e-form-trigger-export-imported")
    imported_definition = copy.deepcopy(exported_definition)
    imported_definition["name"] = imported_name
    imported = create_workflow(
        syntara_api,
        cleanup_workflows,
        name=imported_name,
        description="Form Trigger workflow import/export E2E",
        project_id=first_project_id,
        workflow_definition=imported_definition,
        is_import=True,
    )
    assert imported.has_validation_issues is False

    persisted_definition = get_workflow_definition(syntara_api, UUID(str(imported.id)))
    assert persisted_definition == imported_definition
    assert len(persisted_definition["triggers"]) == 1
    assert persisted_definition["triggers"][0]["type"] == "form_trigger"
    assert [node["id"] for node in persisted_definition["nodes"]] == ["consume"]
    assert all("position" in trigger for trigger in persisted_definition["triggers"])
    assert all("position" in node for node in persisted_definition["nodes"])

    execution_id = _submit_form_trigger(syntara_api, UUID(str(imported.id)), form_execution_cleanup)
    _assert_form_trigger_execution_outputs(syntara_api, execution_id)


@pytest.mark.parametrize(
    ("case", "fields"),
    [
        pytest.param(
            "unknown_field_type",
            [{"type": "unknown_type", "value_name": "reason", "label": "Reason", "required": True}],
            id="unknown-field-type",
        ),
        pytest.param(
            "missing_field_type",
            [{"value_name": "reason", "label": "Reason", "required": True}],
            id="missing-field-type",
        ),
    ],
)
def test_form_trigger_import_reports_save_time_validation_findings(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
    case: str,
    fields: list[dict[str, Any]],
) -> None:
    """Invalid Form Trigger fields are saved with clear validation findings."""
    name = unique_name(f"e2e-form-trigger-invalid-{case}")
    definition = _definition_with_invalid_form_trigger(name, fields=fields)
    body = WorkflowCreate.from_dict(
        {
            "name": name,
            "description": "Invalid Form Trigger import validation case",
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

    trigger_findings = [finding for finding in findings if finding.node_id == "form_trigger"]
    assert trigger_findings, f"No form_trigger finding in {validation_result.to_dict()}"
    assert any(finding.severity.value == "error" for finding in trigger_findings)
    assert any(
        isinstance(finding.field_path, str)
        and "form_definition.fields.0" in finding.field_path
        and ("type" in finding.field_path or "type" in finding.message.lower() or "unknown_type" in finding.message)
        for finding in trigger_findings
    ), f"Field type path missing from {trigger_findings!r}"

    saved_definition = get_workflow_definition(syntara_api, UUID(str(workflow.id)))
    saved_trigger = next(trigger for trigger in saved_definition["triggers"] if trigger["id"] == "form_trigger")
    submitted_trigger = next(trigger for trigger in definition["triggers"] if trigger["id"] == "form_trigger")
    assert saved_trigger["parameters"] == submitted_trigger["parameters"]
    saved = syntara_api.workflows.get(workflow_id=UUID(str(workflow.id))).assert_and_get()
    assert isinstance(saved, WorkflowReadWithVersion)
    assert saved.has_validation_issues is True


def test_import_renamed_form_trigger_preserves_configuration_and_edges(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
) -> None:
    """Import applies a Form Trigger ID change and keeps its parameters and connection."""
    source_name = unique_name("e2e-form-trigger-rename-source")
    source_definition = _form_trigger_workflow_definition(source_name)
    source = create_workflow(
        syntara_api,
        cleanup_workflows,
        name=source_name,
        description="Form Trigger workflow import/export E2E",
        project_id=first_project_id,
        workflow_definition=source_definition,
        is_import=False,
    )
    assert source.has_validation_issues is False
    exported_definition = export_workflow_definition(syntara_api, UUID(str(source.id)))

    imported_name = unique_name("e2e-form-trigger-rename-imported")
    imported_definition = copy.deepcopy(exported_definition)
    imported_definition["name"] = imported_name
    source_trigger = imported_definition["triggers"][0]
    original_parameters = copy.deepcopy(source_trigger["parameters"])
    source_trigger["id"] = "user_choice"
    imported_definition["edges"][0]["from"] = "user_choice"
    consumer = imported_definition["nodes"][0]
    for variable, expression in consumer["parameters"]["environment"].items():
        consumer["parameters"]["environment"][variable] = expression.replace("${form_trigger.", "${user_choice.")

    imported = create_workflow(
        syntara_api,
        cleanup_workflows,
        name=imported_name,
        description="Form Trigger workflow import/export E2E",
        project_id=first_project_id,
        workflow_definition=imported_definition,
        is_import=True,
    )
    assert imported.has_validation_issues is False
    persisted_definition = get_workflow_definition(syntara_api, UUID(str(imported.id)))

    renamed_trigger = next(trigger for trigger in persisted_definition["triggers"] if trigger["id"] == "user_choice")
    assert renamed_trigger["parameters"] == original_parameters
    assert renamed_trigger["position"] == source_trigger["position"]
    assert persisted_definition["edges"] == [{"from": "user_choice", "to": "consume"}]
    assert persisted_definition["edges"] == imported_definition["edges"]


def test_import_handcrafted_form_trigger_workflow_executes(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    form_execution_cleanup: Callable[[UUID], None],
    first_project_id: UUID,
) -> None:
    """Import and execute a hand-authored Form Trigger workflow without exporting a source."""
    name = unique_name("e2e-form-trigger-handcrafted")
    definition = _form_trigger_workflow_definition(name)
    workflow = create_workflow(
        syntara_api,
        cleanup_workflows,
        name=name,
        description="Form Trigger workflow import/export E2E",
        project_id=first_project_id,
        workflow_definition=definition,
        is_import=True,
    )
    assert workflow.has_validation_issues is False

    persisted_definition = get_workflow_definition(syntara_api, UUID(str(workflow.id)))
    assert persisted_definition == definition
    assert len(persisted_definition["triggers"]) == 1
    assert persisted_definition["triggers"][0]["type"] == "form_trigger"
    assert [node["id"] for node in persisted_definition["nodes"]] == ["consume"]
    assert all("position" in trigger for trigger in persisted_definition["triggers"])
    assert all("position" in node for node in persisted_definition["nodes"])

    execution_id = _submit_form_trigger(syntara_api, UUID(str(workflow.id)), form_execution_cleanup)
    _assert_form_trigger_execution_outputs(syntara_api, execution_id)
