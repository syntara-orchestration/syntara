"""E2E coverage for invalid form-prompt and Form Trigger definitions."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
from orchestrator_test_sdk.e2e import unique_name
from syntara_api_client.models import (
    ExecutionCreate,
    ExecutionCreateInputData,
    PublishVersionRequest,
    WorkflowUpdate,
)
from syntara_api_client.models.validation_result import ValidationResult
from syntara_api_client.models.workflow_read_with_version import WorkflowReadWithVersion
from syntara_api_client.models.workflow_update_workflow_definition_type_1 import (
    WorkflowUpdateWorkflowDefinitionType1,
)

from ._helpers import (
    assert_and_get_response,
    assert_definition_invalid,
    assert_problem_response,
)
from ._invalid_definition import (
    FORM_FIELD_CASES,
    FORM_VARIANTS,
    INVALID_DROPDOWN_DEFAULT,
    PROMPT_ONLY_PARAMETER_CASES,
    TRIGGER_VARIANT,
    VALID_TEXT_FIELD,
    FormVariant,
    _workflow_definition,
    create_workflow,
    element_findings,
    validate_definition,
)
from ._workflows import ALL_SUPPORTED_FORM_FIELDS

if TYPE_CHECKING:
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry

pytestmark = [pytest.mark.e2e]


@pytest.mark.parametrize("variant", FORM_VARIANTS, ids=lambda variant: variant.label)
def test_create_saves_invalid_form_definition_and_persists_issue_flag(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
    variant: FormVariant,
) -> None:
    """Create accepts an invalid draft and returns actionable findings."""
    name = unique_name(variant.name_prefix)
    workflow = create_workflow(
        syntara_api,
        cleanup_workflows,
        first_project_id,
        variant,
        name=name,
        fields=[{**VALID_TEXT_FIELD, "value_name": "2 bad name"}],
    )

    assert workflow.has_validation_issues is True
    validation_result = workflow.validation_result
    assert isinstance(validation_result, ValidationResult)
    assert validation_result.is_valid is False
    assert validation_result.error_count >= 1
    assert isinstance(validation_result.findings, list)

    form_findings = [finding for finding in validation_result.findings if finding.node_id == variant.element_id]
    assert form_findings
    finding = next(
        item for item in form_findings if (item.field_path or "").startswith("parameters.form_definition.fields.0")
    )
    assert finding.severity.value == "error"
    assert finding.message.strip()
    assert "validation failed" not in finding.message.lower()
    assert ".fields.0" in (finding.field_path or "")

    saved = assert_and_get_response(syntara_api.workflows.get(workflow_id=workflow.id))
    assert saved.has_validation_issues is True


@pytest.mark.parametrize("variant", FORM_VARIANTS, ids=lambda variant: variant.label)
def test_validate_returns_rfc9457_details_and_accepts_a_valid_form(
    syntara_api: SyntaraApiRegistry,
    variant: FormVariant,
) -> None:
    """The stateless validate endpoint rejects invalid fields and accepts a valid form."""
    invalid = validate_definition(
        syntara_api,
        variant,
        unique_name(variant.name_prefix),
        [{**VALID_TEXT_FIELD, "value_name": "2 bad name"}],
    )
    problem = assert_definition_invalid(invalid, node_id=variant.element_id)
    assert problem["detail"]
    assert all(
        {"severity", "category", "message"} <= finding.keys() for finding in problem["validation_result"]["findings"]
    )
    assert element_findings(problem, variant)

    valid = validate_definition(
        syntara_api,
        variant,
        unique_name(variant.name_prefix),
        [VALID_TEXT_FIELD],
    )
    validation_result = assert_and_get_response(valid)
    assert valid.status_code == HTTPStatus.OK
    assert isinstance(validation_result, ValidationResult)
    assert validation_result.is_valid is True
    assert validation_result.error_count == 0


@pytest.mark.parametrize("variant", FORM_VARIANTS, ids=lambda variant: variant.label)
def test_publish_rejects_invalid_form_definition_and_it_cannot_run_as_published(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
    variant: FormVariant,
) -> None:
    """Publishing an invalid form is blocked and leaves no published version."""
    name = unique_name(variant.name_prefix)
    workflow = create_workflow(
        syntara_api,
        cleanup_workflows,
        first_project_id,
        variant,
        name=name,
        fields=[INVALID_DROPDOWN_DEFAULT],
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
    findings = element_findings(problem, variant)
    assert any(finding["category"] == variant.configuration_category for finding in findings)

    saved = assert_and_get_response(syntara_api.workflows.get(workflow_id=workflow.id))
    assert saved.published_version_id is None
    assert saved.has_validation_issues is True

    execution_body = ExecutionCreate(
        workflow_id=workflow.id,
        trigger_node_id=variant.execution_trigger_node_id,
        use_published=True,
    )
    if variant == TRIGGER_VARIANT:
        execution_body.input_data = ExecutionCreateInputData.from_dict({"choice": "valid"})
    execution = syntara_api.executions.create(body=execution_body)
    execution_problem = assert_problem_response(
        execution,
        expected_status=HTTPStatus.BAD_REQUEST,
        expected_code="WORKFLOW_NOT_PUBLISHED",
    )
    assert execution_problem["retryable"] is False


@pytest.mark.parametrize(
    ("variant", "case_name", "fields", "expected_category", "field_path_prefix", "message_substring", "expected_count"),
    FORM_FIELD_CASES,
)
def test_validate_reports_specific_form_field_defect(
    syntara_api: SyntaraApiRegistry,
    variant: FormVariant,
    case_name: str,
    fields: list[dict[str, Any]],
    expected_category: str | None,
    field_path_prefix: str,
    message_substring: str,
    expected_count: int,
) -> None:
    """Each invalid form shape maps to a locatable schema or model finding."""
    response = validate_definition(
        syntara_api,
        variant,
        unique_name(f"{variant.name_prefix}-{case_name}"),
        fields,
    )
    problem = assert_definition_invalid(response, node_id=variant.element_id)
    findings = element_findings(problem, variant)
    assert len(findings) == expected_count, f"Expected {expected_count} {variant.label} finding(s), got {findings}"

    category = expected_category or variant.configuration_category
    for finding in findings:
        assert finding["severity"] == "error"
        assert finding["category"] == category
        assert finding["field_path"].startswith(field_path_prefix)
        assert finding["message"].strip()
    if message_substring:
        assert any(message_substring in finding["message"] for finding in findings), findings


@pytest.mark.parametrize("variant", FORM_VARIANTS, ids=lambda variant: variant.label)
def test_validate_collects_multiple_form_field_defects_in_field_order(
    syntara_api: SyntaraApiRegistry,
    variant: FormVariant,
) -> None:
    """Validation returns findings for separate bad fields instead of stopping early."""
    fields: list[dict[str, Any]] = [
        {**VALID_TEXT_FIELD, "value_name": "2bad"},
        {
            "type": "date",
            "value_name": "when",
            "label": "When",
            "include_date": True,
            "include_time": False,
            "include_timezone": True,
        },
        {
            "type": "dropdown",
            "value_name": "choice",
            "label": "Choice",
            "options": {"source": "static", "values": []},
        },
    ]
    response = validate_definition(syntara_api, variant, unique_name(variant.name_prefix), fields)
    problem = assert_definition_invalid(response, node_id=variant.element_id)
    findings = element_findings(problem, variant)

    assert problem["validation_result"]["error_count"] >= 3
    paths = [finding.get("field_path") or "" for finding in findings]
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


@pytest.mark.parametrize("variant", FORM_VARIANTS, ids=lambda variant: variant.label)
def test_update_to_invalid_form_definition_flips_durable_issue_flag(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
    variant: FormVariant,
) -> None:
    """Updating a good draft to an invalid form returns findings and blocks publish."""
    name = unique_name(variant.name_prefix)
    workflow = create_workflow(
        syntara_api,
        cleanup_workflows,
        first_project_id,
        variant,
        name=name,
        fields=[VALID_TEXT_FIELD],
    )
    assert workflow.has_validation_issues is False

    invalid_definition = WorkflowUpdateWorkflowDefinitionType1.from_dict(
        _workflow_definition(variant, name, [INVALID_DROPDOWN_DEFAULT])
    )
    update = syntara_api.workflows.update(
        workflow_id=workflow.id,
        body=WorkflowUpdate(workflow_definition=invalid_definition),
    )
    updated = assert_and_get_response(update)
    assert update.status_code == HTTPStatus.OK
    assert isinstance(updated, WorkflowReadWithVersion)
    assert updated.has_validation_issues is True
    update_validation_result = updated.validation_result
    assert isinstance(update_validation_result, ValidationResult)
    assert isinstance(update_validation_result.findings, list)
    update_findings = [
        finding for finding in update_validation_result.findings if finding.node_id == variant.element_id
    ]
    assert len(update_findings) == 1
    assert update_findings[0].category.value == variant.configuration_category
    assert (update_findings[0].field_path or "").startswith("parameters.form_definition.fields.0")
    assert update_findings[0].message

    saved = assert_and_get_response(syntara_api.workflows.get(workflow_id=workflow.id))
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


@pytest.mark.parametrize("variant", FORM_VARIANTS, ids=lambda variant: variant.label)
def test_valid_multi_field_form_definition_can_be_published(
    syntara_api: SyntaraApiRegistry,
    cleanup_workflows: list[UUID],
    first_project_id: UUID,
    variant: FormVariant,
) -> None:
    """A valid definition has no findings and publishes successfully."""
    name = unique_name(variant.name_prefix)
    workflow = create_workflow(
        syntara_api,
        cleanup_workflows,
        first_project_id,
        variant,
        name=name,
        fields=ALL_SUPPORTED_FORM_FIELDS,
    )
    assert workflow.has_validation_issues is False

    valid_response = validate_definition(syntara_api, variant, name, ALL_SUPPORTED_FORM_FIELDS)
    valid_result = assert_and_get_response(valid_response)
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
    published = assert_and_get_response(publish)
    assert publish.status_code == HTTPStatus.OK
    assert published is not None


@pytest.mark.parametrize(("parameter", "value"), PROMPT_ONLY_PARAMETER_CASES)
def test_form_trigger_rejects_prompt_only_parameters(
    syntara_api: SyntaraApiRegistry,
    parameter: str,
    value: object,
) -> None:
    """Each parameter supported only by form prompts is rejected on a trigger."""
    response = validate_definition(
        syntara_api,
        TRIGGER_VARIANT,
        unique_name(TRIGGER_VARIANT.name_prefix),
        [VALID_TEXT_FIELD],
        extra_parameters={parameter: value},
    )
    problem = assert_definition_invalid(response, node_id=TRIGGER_VARIANT.element_id)
    findings = element_findings(problem, TRIGGER_VARIANT)
    assert len(findings) == 1, findings
    assert findings[0]["severity"] == "error"
    assert findings[0]["category"] == "schema_violation"
    assert findings[0]["field_path"] == f"parameters.{parameter}"
    assert "Extra inputs are not permitted" in findings[0]["message"]
