"""E2E coverage for invalid form-prompt definitions across workflow endpoints."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast

import pytest
from orchestrator_test_sdk.e2e import unique_name
from syntara_api_client.models import (
    ExecutionCreate,
    PublishVersionRequest,
    WorkflowCreate,
    WorkflowRead,
    WorkflowUpdate,
    WorkflowValidateRequest,
)
from syntara_api_client.models.validation_result import ValidationResult
from syntara_api_client.models.workflow_create_workflow_definition_type_1 import (
    WorkflowCreateWorkflowDefinitionType1,
)
from syntara_api_client.models.workflow_read_with_version import WorkflowReadWithVersion
from syntara_api_client.models.workflow_update_workflow_definition_type_1 import (
    WorkflowUpdateWorkflowDefinitionType1,
)
from syntara_api_client.models.workflow_validate_request_workflow_definition import (
    WorkflowValidateRequestWorkflowDefinition,
)

from ._helpers import (
    assert_and_get_with_502_skip,
    assert_definition_invalid,
    assert_problem_response,
)
from ._workflows import ALL_SUPPORTED_FORM_FIELDS, producer_prompt_consumer_workflow

if TYPE_CHECKING:
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.types import Response

pytestmark = [pytest.mark.e2e]

_NAME_PREFIX = "e2e-form-prompt-invalid-definition"
_DESCRIPTION = "E2E: invalid form prompt workflow definitions"
_VALID_TEXT_FIELD = {"type": "text", "value_name": "answer", "label": "Answer", "required": True}
_INVALID_DROPDOWN_DEFAULT = {
    "type": "dropdown",
    "value_name": "choice",
    "label": "Choice",
    "required": True,
    "options": {"source": "static", "values": [{"display_label": "Valid", "value": "valid"}]},
    "default": "missing",
}


def _workflow_definition(name: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the shared form-prompt graph while preserving deliberately invalid fields."""
    definition = cast(
        "dict[str, Any]",
        producer_prompt_consumer_workflow(
            name,
            producer_output={},
            form_fields=[_VALID_TEXT_FIELD],
        ).to_dict(),
    )
    prompt_node = next(node for node in definition["nodes"] if node["id"] == "prompt")
    prompt_node["parameters"]["form_definition"]["fields"] = fields
    return definition


def _validate_definition(
    syntara_api: SyntaraApiRegistry,
    name: str,
    fields: list[dict[str, Any]],
) -> Response[Any]:
    definition = WorkflowValidateRequestWorkflowDefinition.from_dict(_workflow_definition(name, fields))
    return syntara_api.workflows.validate_definition(body=WorkflowValidateRequest(workflow_definition=definition))


def _create_workflow(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
    *,
    name: str,
    fields: list[dict[str, Any]],
) -> WorkflowRead:
    definition = WorkflowCreateWorkflowDefinitionType1.from_dict(_workflow_definition(name, fields))
    response = syntara_api.workflows.create(
        body=WorkflowCreate(
            name=name,
            description=_DESCRIPTION,
            workflow_definition=definition,
            project_id=first_project_id,
        )
    )
    workflow = assert_and_get_with_502_skip(response)
    assert response.status_code == HTTPStatus.CREATED
    assert isinstance(workflow, WorkflowRead)
    cleanup_workflows.append(workflow.id)
    return workflow


def _prompt_findings(problem: dict[str, Any]) -> list[dict[str, Any]]:
    validation_result = problem["validation_result"]
    return [finding for finding in validation_result["findings"] if finding.get("node_id") == "prompt"]


def test_create_saves_invalid_form_definition_and_persists_issue_flag(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
) -> None:
    """Create accepts an invalid draft but returns actionable findings."""
    name = unique_name(_NAME_PREFIX)
    workflow = _create_workflow(
        syntara_api,
        cleanup_workflows,
        first_project_id,
        name=name,
        fields=[{**_VALID_TEXT_FIELD, "value_name": "2 bad name"}],
    )

    assert workflow.has_validation_issues is True
    validation_result = workflow.validation_result
    assert isinstance(validation_result, ValidationResult)
    assert validation_result.is_valid is False
    assert validation_result.error_count >= 1
    assert isinstance(validation_result.findings, list)

    prompt_findings = [finding for finding in validation_result.findings if finding.node_id == "prompt"]
    assert prompt_findings
    finding = next(
        item for item in prompt_findings if (item.field_path or "").startswith("parameters.form_definition.fields.0")
    )
    assert finding.severity.value == "error"
    assert finding.message.strip()
    assert "validation failed" not in finding.message.lower()
    assert ".fields.0" in (finding.field_path or "")

    saved = assert_and_get_with_502_skip(syntara_api.workflows.get(workflow_id=workflow.id))
    assert saved.has_validation_issues is True


def test_validate_returns_rfc9457_details_and_accepts_a_valid_form(
    syntara_api: SyntaraApiRegistry,
) -> None:
    """The stateless validate endpoint rejects the form defect with problem details."""
    invalid = _validate_definition(
        syntara_api,
        unique_name(_NAME_PREFIX),
        [{**_VALID_TEXT_FIELD, "value_name": "2 bad name"}],
    )
    problem = assert_definition_invalid(invalid)
    assert problem["detail"]
    assert all(
        {"severity", "category", "message"} <= finding.keys() for finding in problem["validation_result"]["findings"]
    )
    assert any(finding["node_id"] == "prompt" for finding in problem["validation_result"]["findings"])

    valid = _validate_definition(syntara_api, unique_name(_NAME_PREFIX), [_VALID_TEXT_FIELD])
    validation_result = assert_and_get_with_502_skip(valid)
    assert valid.status_code == HTTPStatus.OK
    assert isinstance(validation_result, ValidationResult)
    assert validation_result.is_valid is True
    assert validation_result.error_count == 0


def test_publish_rejects_invalid_form_definition_and_it_cannot_run_as_published(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
) -> None:
    """Publishing an invalid form is blocked and leaves no published version."""
    name = unique_name(_NAME_PREFIX)
    workflow = _create_workflow(
        syntara_api,
        cleanup_workflows,
        first_project_id,
        name=name,
        fields=[_INVALID_DROPDOWN_DEFAULT],
    )
    assert workflow.has_validation_issues is True

    publish = syntara_api.workflows.publish_version(
        workflow_id=workflow.id,
        version=1,
        body=PublishVersionRequest(),
    )
    problem = assert_problem_response(
        publish,
        expected_status=HTTPStatus.CONFLICT,
        expected_code="WORKFLOW_PUBLISH_VALIDATION_ERROR",
    )
    assert problem["title"] == "Workflow Publish Blocked"
    assert any(finding["category"] == "form_prompt_configuration" for finding in _prompt_findings(problem))

    saved = assert_and_get_with_502_skip(syntara_api.workflows.get(workflow_id=workflow.id))
    assert saved.published_version_id is None
    assert saved.has_validation_issues is True

    execution = syntara_api.executions.create(
        body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger", use_published=True)
    )
    execution_problem = assert_problem_response(
        execution,
        expected_status=HTTPStatus.BAD_REQUEST,
        expected_code="WORKFLOW_NOT_PUBLISHED",
    )
    assert execution_problem["retryable"] is False


@pytest.mark.parametrize(
    ("case_name", "fields", "expected_category", "field_path_prefix", "message_substring"),
    [
        (
            "unknown_type",
            [{"type": "not_a_real_type", "value_name": "choice", "label": "Choice"}],
            "form_prompt_configuration",
            "parameters.form_definition.fields.0",
            "",
        ),
        (
            "invalid_value_name_pattern",
            [{**_VALID_TEXT_FIELD, "value_name": "2bad"}],
            "schema_violation",
            "parameters.form_definition.fields.0.value_name",
            "match pattern",
        ),
        (
            "value_name_too_long",
            [{**_VALID_TEXT_FIELD, "value_name": "a" * 65}],
            "schema_violation",
            "parameters.form_definition.fields.0.value_name",
            "",
        ),
        (
            "empty_label",
            [{**_VALID_TEXT_FIELD, "label": ""}],
            "schema_violation",
            "parameters.form_definition.fields.0.label",
            "",
        ),
        (
            "extra_field_property",
            [{**_VALID_TEXT_FIELD, "unexpected": True}],
            "schema_violation",
            "parameters.form_definition.fields.0.unexpected",
            "",
        ),
        (
            "duplicate_value_names",
            [
                _VALID_TEXT_FIELD,
                {**_VALID_TEXT_FIELD, "label": "Second answer"},
            ],
            "form_prompt_configuration",
            "parameters.form_definition",
            "Duplicate field names are not allowed",
        ),
        (
            "empty_fields",
            [],
            "schema_violation",
            "parameters.form_definition.fields",
            "",
        ),
        (
            "date_without_components",
            [
                {
                    "type": "date",
                    "value_name": "when",
                    "label": "When",
                    "include_date": False,
                    "include_time": False,
                    "include_timezone": False,
                }
            ],
            "form_prompt_configuration",
            "parameters.form_definition.fields.0",
            "at least one of include_date, include_time, or include_timezone must be true",
        ),
        (
            "date_time_requires_timezone",
            [
                {
                    "type": "date",
                    "value_name": "when",
                    "label": "When",
                    "include_time": True,
                    "include_timezone": False,
                }
            ],
            "form_prompt_configuration",
            "parameters.form_definition.fields.0",
            "include_timezone is required when include_time is true",
        ),
        (
            "invalid_calendar_date_default",
            [
                {
                    "type": "date",
                    "value_name": "when",
                    "label": "When",
                    "default": {"date": "2026-02-30"},
                }
            ],
            "form_prompt_configuration",
            "parameters.form_definition.fields.0.default.date",
            "Invalid date: '2026-02-30'",
        ),
        (
            "invalid_timezone_default",
            [
                {
                    "type": "date",
                    "value_name": "when",
                    "label": "When",
                    "include_date": False,
                    "include_timezone": True,
                    "default": {"timezone": "Mars/Olympus"},
                }
            ],
            "form_prompt_configuration",
            "parameters.form_definition.fields.0.default.timezone",
            "Invalid timezone",
        ),
        (
            "date_default_missing_component",
            [
                {
                    "type": "date",
                    "value_name": "when",
                    "label": "When",
                    "include_timezone": True,
                    "default": {"date": "2026-02-14"},
                }
            ],
            "form_prompt_configuration",
            "parameters.form_definition.fields.0",
            "default is missing timezone",
        ),
        (
            "date_default_extra_component",
            [
                {
                    "type": "date",
                    "value_name": "when",
                    "label": "When",
                    "default": {"date": "2026-02-14", "timezone": "UTC"},
                }
            ],
            "form_prompt_configuration",
            "parameters.form_definition.fields.0",
            "default supplies timezone, which this field does not collect",
        ),
        (
            "empty_static_dropdown_options",
            [
                {
                    "type": "dropdown",
                    "value_name": "choice",
                    "label": "Choice",
                    "options": {"source": "static", "values": []},
                }
            ],
            "schema_violation",
            "parameters.form_definition.fields.0.options.values",
            "",
        ),
        (
            "dropdown_default_not_in_options",
            [_INVALID_DROPDOWN_DEFAULT],
            "form_prompt_configuration",
            "parameters.form_definition.fields.0.default",
            "is not in the option list",
        ),
        (
            "multi_select_default_not_in_options",
            [
                {
                    "type": "multi_select",
                    "value_name": "choices",
                    "label": "Choices",
                    "options": {"source": "static", "values": [{"display_label": "Valid", "value": "valid"}]},
                    "default": ["missing"],
                }
            ],
            "form_prompt_configuration",
            "parameters.form_definition.fields.0.default",
            "are not in the option list",
        ),
        (
            "engine_only_dynamic_resolved_options",
            [
                {
                    "type": "dropdown",
                    "value_name": "choice",
                    "label": "Choice",
                    "options": {
                        "source": "dynamic_resolved",
                        "values": [{"display_label": "Valid", "value": "valid"}],
                    },
                }
            ],
            "form_prompt_configuration",
            "parameters.form_definition.fields.0.options",
            "produced by the workflow engine at run time and cannot be authored",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) and value else None,
)
def test_validate_reports_specific_form_field_defect(
    syntara_api: SyntaraApiRegistry,
    case_name: str,
    fields: list[dict[str, Any]],
    expected_category: str,
    field_path_prefix: str,
    message_substring: str,
) -> None:
    """Each invalid form shape maps to its schema or model validation finding."""
    response = _validate_definition(syntara_api, unique_name(f"{_NAME_PREFIX}-{case_name}"), fields)
    problem = assert_definition_invalid(response)
    findings = _prompt_findings(problem)
    assert len(findings) == 1, f"Expected one form-prompt finding, got {findings}"

    finding = findings[0]
    assert finding["severity"] == "error"
    assert finding["category"] == expected_category
    assert finding["field_path"].startswith(field_path_prefix)
    assert finding["message"].strip()
    if message_substring:
        assert message_substring in finding["message"]


def test_validate_collects_multiple_form_field_defects_in_field_order(
    syntara_api: SyntaraApiRegistry,
) -> None:
    """Validation returns findings for separate bad fields instead of stopping early."""
    fields: list[dict[str, Any]] = [
        {**_VALID_TEXT_FIELD, "value_name": "2bad"},
        {
            "type": "date",
            "value_name": "when",
            "label": "When",
            "include_time": True,
            "include_timezone": False,
        },
        {
            "type": "dropdown",
            "value_name": "choice",
            "label": "Choice",
            "options": {"source": "static", "values": []},
        },
    ]
    response = _validate_definition(syntara_api, unique_name(_NAME_PREFIX), fields)
    problem = assert_definition_invalid(response)
    findings = _prompt_findings(problem)

    assert problem["validation_result"]["error_count"] >= 3
    paths = [finding.get("field_path", "") for finding in findings]
    for index in range(3):
        assert any(path.startswith(f"parameters.form_definition.fields.{index}") for path in paths), paths
    field_indices = [
        int(path.removeprefix("parameters.form_definition.fields.").split(".", maxsplit=1)[0])
        for path in paths
        if path.startswith("parameters.form_definition.fields.")
    ]
    assert field_indices == sorted(field_indices)

    severities = [finding["severity"] for finding in problem["validation_result"]["findings"]]
    expected_order = ["error"] * problem["validation_result"]["error_count"] + ["warning"] * problem[
        "validation_result"
    ]["warning_count"]
    assert severities == expected_order


def test_update_to_invalid_form_definition_flips_durable_issue_flag(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
) -> None:
    """Updating a good draft to an invalid form returns findings and blocks publish."""
    name = unique_name(_NAME_PREFIX)
    workflow = _create_workflow(
        syntara_api,
        cleanup_workflows,
        first_project_id,
        name=name,
        fields=[_VALID_TEXT_FIELD],
    )
    assert workflow.has_validation_issues is False

    invalid_definition = WorkflowUpdateWorkflowDefinitionType1.from_dict(
        _workflow_definition(name, [_INVALID_DROPDOWN_DEFAULT])
    )
    update = syntara_api.workflows.update(
        workflow_id=workflow.id,
        body=WorkflowUpdate(workflow_definition=invalid_definition),
    )
    updated = assert_and_get_with_502_skip(update)
    assert update.status_code == HTTPStatus.OK
    assert isinstance(updated, WorkflowReadWithVersion)
    assert updated.has_validation_issues is True
    update_validation_result = updated.validation_result
    assert isinstance(update_validation_result, ValidationResult)
    assert isinstance(update_validation_result.findings, list)
    update_findings = [finding for finding in update_validation_result.findings if finding.node_id == "prompt"]
    assert len(update_findings) == 1
    assert update_findings[0].category.value == "form_prompt_configuration"
    assert update_findings[0].message

    saved = assert_and_get_with_502_skip(syntara_api.workflows.get(workflow_id=workflow.id))
    assert saved.has_validation_issues is True

    publish = syntara_api.workflows.publish_version(
        workflow_id=workflow.id,
        version=updated.current_version,
        body=PublishVersionRequest(),
    )
    assert_problem_response(
        publish,
        expected_status=HTTPStatus.CONFLICT,
        expected_code="WORKFLOW_PUBLISH_VALIDATION_ERROR",
    )


def test_valid_multi_field_form_definition_can_be_published(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
) -> None:
    """A valid definition has no findings and publishes successfully."""
    name = unique_name(_NAME_PREFIX)
    workflow = _create_workflow(
        syntara_api,
        cleanup_workflows,
        first_project_id,
        name=name,
        fields=ALL_SUPPORTED_FORM_FIELDS,
    )
    assert workflow.has_validation_issues is False

    valid_response = _validate_definition(syntara_api, name, ALL_SUPPORTED_FORM_FIELDS)
    valid_result = assert_and_get_with_502_skip(valid_response)
    assert valid_response.status_code == HTTPStatus.OK
    assert isinstance(valid_result, ValidationResult)
    assert valid_result.is_valid is True
    assert valid_result.error_count == 0
    assert valid_result.warning_count == 0

    publish = syntara_api.workflows.publish_version(
        workflow_id=workflow.id,
        version=1,
        body=PublishVersionRequest(),
    )
    published = assert_and_get_with_502_skip(publish)
    assert publish.status_code == HTTPStatus.OK
    assert published is not None
