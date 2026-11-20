"""Integration tests for project-scoped, published Sub-workflow references."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models.project import Project
from syntara.core.models import User
from syntara.workflows.exceptions import WorkflowNotPublishedError, WorkflowPublishValidationError
from syntara.workflows.models import Workflow
from syntara.workflows.models.validation_finding import ValidationCategory, ValidationResult, ValidationSeverity
from syntara.workflows.models.workflow import WorkflowCreate
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.workflow_service import WorkflowService
from syntara.workflows.validators import validate_subworkflow_project_references


def _definition_with_subworkflow(
    child_workflow_id: UUID | None,
    *,
    trigger_node_id: str = "child_entry",
    input_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a valid-shaped definition containing one selected child workflow."""
    return {
        "schema_version": "2.0.0",
        "name": "parent-workflow",
        "triggers": [{"id": "manual", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "call_child",
                "name": "Call child",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": str(child_workflow_id) if child_workflow_id is not None else "",
                    "trigger_node_id": trigger_node_id,
                    "input_mapping": input_mapping or {},
                },
            }
        ],
        "edges": [{"from": "manual", "to": "call_child"}],
    }


def _definition_without_subworkflow() -> dict[str, Any]:
    """Build a valid definition for creating a parent before adding a child call."""
    return {
        "schema_version": "2.0.0",
        "name": "parent-workflow",
        "triggers": [{"id": "manual", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "script",
                "name": "Script",
                "type": "script",
                "parameters": {"language": "python", "code": "pass"},
            }
        ],
        "edges": [{"from": "manual", "to": "script"}],
    }


def _definition_with_subworkflow_output_references(
    child_workflow_id: UUID,
    references: list[str],
) -> dict[str, Any]:
    """Build a parent definition whose downstream condition uses child outputs."""
    definition = _definition_with_subworkflow(child_workflow_id)
    definition["nodes"].append(
        {
            "id": "consume_output",
            "name": "Consume child output",
            "type": "condition",
            "parameters": {"condition": " and ".join(f"${{{reference}}}" for reference in references)},
        }
    )
    definition["edges"].append({"from": "call_child", "to": "consume_output"})
    return definition


def _definition_with_dependencies(
    entry_trigger_id: str,
    references: list[tuple[str, UUID, str]],
    *,
    additional_trigger_ids: list[str] | None = None,
) -> dict[str, Any]:
    trigger_ids = [entry_trigger_id, *(additional_trigger_ids or [])]
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": trigger_id, "type": "subworkflow_trigger", "parameters": {}} for trigger_id in trigger_ids],
        "nodes": [
            {
                "id": node_id,
                "type": "sub_workflow",
                "parameters": {"workflow_id": str(child_id), "trigger_node_id": child_trigger_id},
            }
            for node_id, child_id, child_trigger_id in references
        ],
        "edges": [{"from": entry_trigger_id, "to": node_id} for node_id, _, _ in references],
    }


async def _replace_published_definition(
    session: AsyncSession,
    workflow: Workflow,
    definition: dict[str, Any],
) -> None:
    assert workflow.published_version_id is not None
    version = await session.get(WorkflowVersion, workflow.published_version_id)
    assert version is not None
    version.workflow_definition = definition
    await session.flush()


async def _create_child_workflow(
    session: AsyncSession,
    user: User,
    project_id: UUID,
    *,
    published: bool = True,
    trigger_node_id: str = "child_entry",
    trigger_type: str = "subworkflow_trigger",
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    additional_triggers: list[dict[str, Any]] | None = None,
) -> Workflow:
    child = Workflow(
        name=f"child-{uuid4().hex[:8]}",
        created_by=user.id,
        project_id=project_id,
        current_version=1,
        is_enabled=False,
    )
    session.add(child)
    await session.flush()

    if published:
        trigger_parameters = {}
        if input_schema is not None:
            trigger_parameters["input_schema"] = input_schema
        if output_schema is not None:
            trigger_parameters["output_schema"] = output_schema
        triggers = [{"id": trigger_node_id, "type": trigger_type, "parameters": trigger_parameters}]
        triggers.extend(additional_triggers or [])
        version = WorkflowVersion(
            workflow_id=child.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition={
                "schema_version": "2.0.0",
                "name": child.name,
                "triggers": triggers,
                "nodes": [],
                "edges": [],
            },
            created_by=user.id,
        )
        session.add(version)
        await session.flush()
        child.published_version_id = version.id
        child.is_enabled = True
        await session.flush()

    return child


def _valid_workflow_validator() -> MagicMock:
    validator = MagicMock()
    validator.collect_findings.return_value = ValidationResult(
        is_valid=True,
        error_count=0,
        warning_count=0,
        findings=[],
    )
    return validator


@pytest.mark.asyncio
async def test_subworkflow_reference_in_same_project_passes_validation(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    child = await _create_child_workflow(test_db_session, test_user, test_project_id)

    findings = await validate_subworkflow_project_references(
        test_db_session,
        _definition_with_subworkflow(child.id),
        test_project_id,
    )

    assert findings == []


@pytest.mark.asyncio
async def test_missing_child_workflow_reference_returns_error_finding(
    test_db_session: AsyncSession,
    test_project_id: UUID,
) -> None:
    missing_child_id = uuid4()

    findings = await validate_subworkflow_project_references(
        test_db_session,
        _definition_with_subworkflow(missing_child_id),
        test_project_id,
    )

    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == ValidationSeverity.error
    assert finding.category == ValidationCategory.invalid_reference
    assert finding.node_id == "call_child"
    assert finding.field_path == "parameters.workflow_id"
    assert finding.message == "The selected child workflow is no longer available."


@pytest.mark.asyncio
async def test_direct_self_reference_is_a_cycle_finding(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    workflow = await _create_child_workflow(test_db_session, test_user, test_project_id, trigger_node_id="entry")
    definition = _definition_with_dependencies("entry", [("call_self", workflow.id, "entry")])

    findings = await validate_subworkflow_project_references(
        test_db_session,
        definition,
        test_project_id,
        workflow_id=workflow.id,
    )

    cycle_findings = [finding for finding in findings if "dependency cycle" in finding.message.lower()]
    assert len(cycle_findings) == 1
    assert cycle_findings[0].severity == ValidationSeverity.error
    assert cycle_findings[0].node_id == "call_self"
    assert cycle_findings[0].field_path == "parameters.workflow_id"


@pytest.mark.asyncio
async def test_transitive_cycle_is_detected_through_the_selected_child_trigger(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    workflow_a = await _create_child_workflow(test_db_session, test_user, test_project_id, trigger_node_id="entry_a")
    workflow_b = await _create_child_workflow(test_db_session, test_user, test_project_id, trigger_node_id="entry_b")
    await _replace_published_definition(
        test_db_session,
        workflow_b,
        _definition_with_dependencies("entry_b", [("call_a", workflow_a.id, "entry_a")]),
    )
    definition_a = _definition_with_dependencies("entry_a", [("call_b", workflow_b.id, "entry_b")])
    service = WorkflowService(test_db_session, test_user)

    with (
        patch(
            "syntara.workflows.services.workflow_service.workflow_validator",
            _valid_workflow_validator(),
        ),
        patch(
            "syntara.workflows.services.workflow_service.get_system_continue_on_failure",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        version, validation_result = await service.create_workflow_version(
            workflow_a,
            definition_a,
            "Add a cyclic child dependency",
        )

        cycle_findings = [
            finding for finding in validation_result.findings if "dependency cycle" in finding.message.lower()
        ]
        assert version is not None
        assert len(cycle_findings) == 1
        assert cycle_findings[0].severity == ValidationSeverity.error
        assert cycle_findings[0].node_id == "call_a"
        assert "entry_a" in cycle_findings[0].message
        assert "entry_b" in cycle_findings[0].message

        with pytest.raises(WorkflowPublishValidationError) as exc_info:
            await service.publish_workflow_version(workflow_id=workflow_a.id, version=version.version)

    assert any("dependency cycle" in finding.message.lower() for finding in exc_info.value.validation_result.findings)


@pytest.mark.asyncio
async def test_shared_child_workflow_does_not_create_a_cycle(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    workflow_a = await _create_child_workflow(test_db_session, test_user, test_project_id, trigger_node_id="entry_a")
    workflow_b = await _create_child_workflow(test_db_session, test_user, test_project_id, trigger_node_id="entry_b")
    workflow_c = await _create_child_workflow(test_db_session, test_user, test_project_id, trigger_node_id="entry_c")
    await _replace_published_definition(
        test_db_session,
        workflow_b,
        _definition_with_dependencies("entry_b", [("call_c", workflow_c.id, "entry_c")]),
    )
    definition_a = _definition_with_dependencies(
        "entry_a",
        [("call_b", workflow_b.id, "entry_b"), ("call_c", workflow_c.id, "entry_c")],
    )

    findings = await validate_subworkflow_project_references(
        test_db_session,
        definition_a,
        test_project_id,
        workflow_id=workflow_a.id,
    )

    assert not [finding for finding in findings if "dependency cycle" in finding.message.lower()]


@pytest.mark.asyncio
async def test_cycle_check_ignores_an_unreachable_child_trigger_branch(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    workflow_a = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        trigger_node_id="entry_a",
        additional_triggers=[{"id": "alternate_a", "type": "subworkflow_trigger", "parameters": {}}],
    )
    workflow_b = await _create_child_workflow(test_db_session, test_user, test_project_id, trigger_node_id="entry_b")
    await _replace_published_definition(
        test_db_session,
        workflow_b,
        _definition_with_dependencies("entry_b", [("call_a", workflow_a.id, "alternate_a")]),
    )
    definition_a = _definition_with_dependencies(
        "entry_a",
        [("call_b", workflow_b.id, "entry_b")],
        additional_trigger_ids=["alternate_a"],
    )

    findings = await validate_subworkflow_project_references(
        test_db_session,
        definition_a,
        test_project_id,
        workflow_id=workflow_a.id,
    )

    assert not [finding for finding in findings if "dependency cycle" in finding.message.lower()]


@pytest.mark.asyncio
async def test_cross_project_subworkflow_reference_returns_error_finding(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    other_project = Project(name=f"other-project-{uuid4().hex[:8]}")
    test_db_session.add(other_project)
    await test_db_session.flush()
    child = await _create_child_workflow(test_db_session, test_user, other_project.id)

    findings = await validate_subworkflow_project_references(
        test_db_session,
        _definition_with_subworkflow(child.id),
        test_project_id,
    )

    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "error"
    assert finding.category == ValidationCategory.invalid_reference
    assert finding.node_id == "call_child"
    assert finding.field_path == "parameters.workflow_id"
    assert "same Project" in finding.message


@pytest.mark.asyncio
async def test_incomplete_subworkflow_selection_is_saved_with_validation_findings(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    service = WorkflowService(test_db_session, test_user)
    incomplete_definition = _definition_with_subworkflow(None, trigger_node_id="")
    request = WorkflowCreate.model_validate(
        {
            "name": f"incomplete-parent-{uuid4().hex[:8]}",
            "workflow_definition": incomplete_definition,
            "project_id": test_project_id,
        }
    )
    assert isinstance(request.workflow_definition, dict)

    with (
        patch(
            "syntara.workflows.services.workflow_service.workflow_validator",
            _valid_workflow_validator(),
        ),
        patch(
            "syntara.workflows.services.workflow_service.get_system_continue_on_failure",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        workflow, version, validation_result = await service.create_workflow(
            name=request.name,
            description=None,
            labels={},
            workflow_definition=request.workflow_definition,
            project_id=test_project_id,
        )

    assert version is not None
    assert workflow.has_validation_issues is True
    assert validation_result.error_count == 2
    assert [finding.field_path for finding in validation_result.findings] == [
        "parameters.workflow_id",
        "parameters.trigger_node_id",
    ]


@pytest.mark.asyncio
async def test_cross_project_reference_is_reported_when_saved_and_blocks_publish(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    other_project = Project(name=f"other-project-{uuid4().hex[:8]}")
    test_db_session.add(other_project)
    await test_db_session.flush()
    child = await _create_child_workflow(test_db_session, test_user, other_project.id)
    service = WorkflowService(test_db_session, test_user)

    with (
        patch(
            "syntara.workflows.services.workflow_service.workflow_validator",
            _valid_workflow_validator(),
        ),
        patch(
            "syntara.workflows.services.workflow_service.get_system_continue_on_failure",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        parent, _initial_version, _initial_validation = await service.create_workflow(
            name=f"parent-{uuid4().hex[:8]}",
            description=None,
            labels={},
            workflow_definition=_definition_without_subworkflow(),
            project_id=test_project_id,
        )

        version, validation_result = await service.create_workflow_version(
            parent,
            _definition_with_subworkflow(child.id),
            "Add cross-project sub-workflow reference",
        )

        assert version is not None
        assert parent.has_validation_issues is True
        assert validation_result.error_count == 1
        assert validation_result.findings[0].node_id == "call_child"
        assert validation_result.findings[0].field_path == "parameters.workflow_id"

        with pytest.raises(WorkflowPublishValidationError) as exc_info:
            await service.publish_workflow_version(workflow_id=parent.id, version=version.version)

    assert exc_info.value.validation_result.error_count == 1
    assert exc_info.value.validation_result.findings[0].category == ValidationCategory.invalid_reference


@pytest.mark.asyncio
async def test_same_project_reference_can_be_saved_and_published(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    child = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        trigger_node_id="primary_entry",
        input_schema={
            "type": "object",
            "properties": {"primary_input": {"type": "string"}},
            "required": ["primary_input"],
        },
        additional_triggers=[
            {
                "id": "selected_entry",
                "type": "subworkflow_trigger",
                "parameters": {
                    "input_schema": {
                        "type": "object",
                        "properties": {"environment": {"type": "string"}},
                        "required": ["environment"],
                    }
                },
            }
        ],
    )
    service = WorkflowService(test_db_session, test_user)

    with (
        patch(
            "syntara.workflows.services.workflow_service.workflow_validator",
            _valid_workflow_validator(),
        ),
        patch(
            "syntara.workflows.services.workflow_service.get_system_continue_on_failure",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        parent, version, validation_result = await service.create_workflow(
            name=f"parent-{uuid4().hex[:8]}",
            description=None,
            labels={},
            workflow_definition=_definition_with_subworkflow(
                child.id,
                trigger_node_id="selected_entry",
                input_mapping={"environment": "staging"},
            ),
            project_id=test_project_id,
        )

        assert parent.has_validation_issues is False
        assert validation_result.error_count == 0

        webhook_service = MagicMock()
        webhook_service.return_value.sync_webhook_triggers = AsyncMock()
        with patch("syntara.workflows.services.workflow_service.WebhookTriggerService", webhook_service):
            published_workflow, published_version, _warning = await service.publish_workflow_version(
                workflow_id=parent.id,
                version=version.version,
            )

    assert published_workflow.published_version_id == published_version.id
    assert published_workflow.is_enabled is True


@pytest.mark.asyncio
async def test_reference_to_declared_child_output_has_no_finding(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    child = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        output_schema={
            "type": "object",
            "properties": {
                "release": {
                    "type": "object",
                    "properties": {"artifact_url": {"type": "string"}},
                    "additionalProperties": False,
                }
            },
        },
    )

    findings = await validate_subworkflow_project_references(
        test_db_session,
        _definition_with_subworkflow_output_references(
            child.id,
            ["call_child.outputs.release.artifact_url"],
        ),
        test_project_id,
    )

    assert findings == []


@pytest.mark.asyncio
async def test_declared_output_references_in_script_code_are_validated(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    child = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        output_schema={
            "type": "object",
            "properties": {
                "release": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "additionalProperties": False,
                }
            },
        },
    )
    parent_definition = _definition_with_subworkflow(child.id)
    parent_definition["nodes"].append(
        {
            "id": "consume_output",
            "name": "Consume child output in script",
            "type": "script",
            "parameters": {
                "language": "python",
                "code": ('print("${call_child.outputs.release.url}")\nprint("${call_child.outputs.release.tag}")'),
            },
        }
    )
    parent_definition["edges"].append({"from": "call_child", "to": "consume_output"})

    findings = await validate_subworkflow_project_references(test_db_session, parent_definition, test_project_id)

    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.warning
    assert findings[0].node_id == "call_child"
    assert findings[0].field_path == "outputs.release.tag"


@pytest.mark.asyncio
async def test_undeclared_child_output_references_each_produce_warnings(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    child = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        output_schema={
            "type": "object",
            "properties": {
                "still_present": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "additionalProperties": False,
                }
            },
        },
    )

    findings = await validate_subworkflow_project_references(
        test_db_session,
        _definition_with_subworkflow_output_references(
            child.id,
            [
                "call_child.outputs.removed_a.value",
                "call_child.outputs.still_present.value",
                "call_child.outputs.removed_b",
            ],
        ),
        test_project_id,
    )

    assert len(findings) == 2
    assert all(finding.severity == ValidationSeverity.warning for finding in findings)
    assert [finding.message for finding in findings] == [
        "Parent references child output 'removed_a.value' which is not declared by the selected Subworkflow Trigger",
        "Parent references child output 'removed_b' which is not declared by the selected Subworkflow Trigger",
    ]
    assert all(finding.node_id == "call_child" for finding in findings)
    assert [finding.field_path for finding in findings] == [
        "outputs.removed_a.value",
        "outputs.removed_b",
    ]


@pytest.mark.asyncio
async def test_undeclared_child_output_warning_does_not_block_publish(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    child = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        output_schema={"type": "object", "properties": {}},
    )
    service = WorkflowService(test_db_session, test_user)

    with (
        patch(
            "syntara.workflows.services.workflow_service.workflow_validator",
            _valid_workflow_validator(),
        ),
        patch(
            "syntara.workflows.services.workflow_service.get_system_continue_on_failure",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as webhook_service,
    ):
        webhook_service.return_value.sync_webhook_triggers = AsyncMock()
        parent, version, validation_result = await service.create_workflow(
            name=f"parent-{uuid4().hex[:8]}",
            description=None,
            labels={},
            workflow_definition=_definition_with_subworkflow_output_references(
                child.id,
                ["call_child.outputs.removed_step.value"],
            ),
            project_id=test_project_id,
        )

        assert validation_result.error_count == 0
        assert validation_result.warning_count == 1
        assert validation_result.findings[0].message == (
            "Parent references child output 'removed_step.value' which is not declared "
            "by the selected Subworkflow Trigger"
        )

        published_workflow, published_version, warning = await service.publish_workflow_version(
            workflow_id=parent.id,
            version=version.version,
        )

    assert published_workflow.published_version_id == published_version.id
    assert "Parent references child output 'removed_step.value' which is not declared" in warning


@pytest.mark.asyncio
async def test_nested_dynamic_child_output_paths_follow_declared_schema(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    child = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        output_schema={
            "type": "object",
            "properties": {
                "labels": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                }
            },
        },
    )

    findings = await validate_subworkflow_project_references(
        test_db_session,
        _definition_with_subworkflow_output_references(
            child.id,
            [
                "call_child.outputs.labels.release",
                "call_child.outputs.labels.region",
            ],
        ),
        test_project_id,
    )

    assert findings == []


@pytest.mark.asyncio
async def test_child_output_validation_uses_selected_trigger_schema(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    child = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        output_schema={"type": "object", "properties": {"selected": {"type": "string"}}},
        additional_triggers=[
            {
                "id": "other_entry",
                "type": "subworkflow_trigger",
                "parameters": {"output_schema": {"type": "object", "properties": {"other": {"type": "string"}}}},
            }
        ],
    )

    findings = await validate_subworkflow_project_references(
        test_db_session,
        _definition_with_subworkflow_output_references(
            child.id,
            ["call_child.outputs.selected", "call_child.outputs.other"],
        ),
        test_project_id,
    )

    assert len(findings) == 1
    assert findings[0].field_path == "outputs.other"


@pytest.mark.asyncio
async def test_nested_child_output_path_rejects_missing_property_in_closed_object(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    child = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        output_schema={
            "type": "object",
            "properties": {
                "release": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "additionalProperties": False,
                }
            },
        },
    )

    findings = await validate_subworkflow_project_references(
        test_db_session,
        _definition_with_subworkflow_output_references(
            child.id,
            ["call_child.outputs.release.tag"],
        ),
        test_project_id,
    )

    assert len(findings) == 1
    assert findings[0].field_path == "outputs.release.tag"


@pytest.mark.asyncio
async def test_array_child_output_paths_follow_item_schema(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    child = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        output_schema={
            "type": "object",
            "properties": {
                "artifacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "additionalProperties": False,
                    },
                }
            },
        },
    )

    findings = await validate_subworkflow_project_references(
        test_db_session,
        _definition_with_subworkflow_output_references(
            child.id,
            [
                "call_child.outputs.artifacts.0.url",
                "call_child.outputs.artifacts.0.tag",
                "call_child.outputs.artifacts.url",
            ],
        ),
        test_project_id,
    )

    assert len(findings) == 2
    assert [finding.field_path for finding in findings] == [
        "outputs.artifacts.0.tag",
        "outputs.artifacts.url",
    ]
    assert all(finding.severity == ValidationSeverity.warning for finding in findings)


@pytest.mark.asyncio
async def test_missing_required_child_inputs_warn_on_save_and_allow_publish(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    child = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        input_schema={
            "type": "object",
            "properties": {"target_host": {"type": "string"}, "region": {"type": "string"}},
            "required": ["target_host", "region"],
        },
    )
    service = WorkflowService(test_db_session, test_user)

    with (
        patch(
            "syntara.workflows.services.workflow_service.workflow_validator",
            _valid_workflow_validator(),
        ),
        patch(
            "syntara.workflows.services.workflow_service.get_system_continue_on_failure",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as webhook_service,
    ):
        webhook_service.return_value.sync_webhook_triggers = AsyncMock()
        parent, version, validation_result = await service.create_workflow(
            name=f"parent-{uuid4().hex[:8]}",
            description=None,
            labels={},
            workflow_definition=_definition_with_subworkflow(child.id),
            project_id=test_project_id,
        )

        assert parent.has_validation_issues is True
        assert validation_result.error_count == 0
        assert validation_result.warning_count == 2
        assert [finding.field_path for finding in validation_result.findings] == [
            "parameters.input_mapping.target_host",
            "parameters.input_mapping.region",
        ]
        assert [finding.message for finding in validation_result.findings] == [
            "The selected child workflow requires input 'target_host', not provided in input_mapping",
            "The selected child workflow requires input 'region', not provided in input_mapping",
        ]

        published_workflow, published_version, warning = await service.publish_workflow_version(
            workflow_id=parent.id,
            version=version.version,
        )

    assert published_workflow.published_version_id == published_version.id
    assert "requires input 'target_host'" in warning
    assert "requires input 'region'" in warning


@pytest.mark.asyncio
async def test_parent_subworkflow_input_rejects_incompatible_upstream_declared_output(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    producer = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        output_schema={
            "type": "object",
            "properties": {"release": {"type": "object", "properties": {"id": {"type": "string"}}}},
        },
    )
    consumer = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        input_schema={"type": "object", "properties": {"build_id": {"type": "number"}}},
    )
    parent_definition = {
        "schema_version": "2.0.0",
        "name": "typed-parent",
        "triggers": [{"id": "parent_entry", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "invoke_release",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": str(producer.id),
                    "trigger_node_id": "child_entry",
                    "input_mapping": {},
                },
            },
            {
                "id": "consume_release",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": str(consumer.id),
                    "trigger_node_id": "child_entry",
                    "input_mapping": {"build_id": "${invoke_release.outputs.release.id}"},
                },
            },
        ],
        "edges": [
            {"from": "parent_entry", "to": "invoke_release"},
            {"from": "invoke_release", "to": "consume_release"},
        ],
    }

    findings = await validate_subworkflow_project_references(test_db_session, parent_definition, test_project_id)

    type_findings = [finding for finding in findings if finding.field_path == "parameters.input_mapping.build_id"]
    assert len(type_findings) == 1
    assert type_findings[0].severity == ValidationSeverity.error
    assert type_findings[0].category == ValidationCategory.schema_violation
    assert type_findings[0].node_id == "consume_release"
    assert "source type 'string'" in type_findings[0].message
    assert "expects 'number'" in type_findings[0].message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("child_state", "child_trigger_id", "child_trigger_type", "selected_trigger_id", "expected_field_path"),
    [
        ("unpublished", "child_entry", "subworkflow_trigger", "child_entry", "parameters.workflow_id"),
        ("published", "available_entry", "subworkflow_trigger", "missing_entry", "parameters.trigger_node_id"),
        ("published", "child_entry", "manual_trigger", "child_entry", "parameters.trigger_node_id"),
    ],
)
async def test_unavailable_child_invocation_severity_controls_publishability(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
    child_state: str,
    child_trigger_id: str,
    child_trigger_type: str,
    selected_trigger_id: str,
    expected_field_path: str,
) -> None:
    child = await _create_child_workflow(
        test_db_session,
        test_user,
        test_project_id,
        published=child_state == "published",
        trigger_node_id=child_trigger_id,
        trigger_type=child_trigger_type,
    )
    service = WorkflowService(test_db_session, test_user)

    with (
        patch(
            "syntara.workflows.services.workflow_service.workflow_validator",
            _valid_workflow_validator(),
        ),
        patch(
            "syntara.workflows.services.workflow_service.get_system_continue_on_failure",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as webhook_service,
    ):
        webhook_service.return_value.sync_webhook_triggers = AsyncMock()
        parent, _initial_version, _initial_validation = await service.create_workflow(
            name=f"parent-{uuid4().hex[:8]}",
            description=None,
            labels={},
            workflow_definition=_definition_without_subworkflow(),
            project_id=test_project_id,
        )

        version, validation_result = await service.create_workflow_version(
            parent,
            _definition_with_subworkflow(child.id, trigger_node_id=selected_trigger_id),
            "Add unavailable sub-workflow reference",
        )

        assert version is not None
        assert parent.has_validation_issues is True
        expected_severity = ValidationSeverity.warning if child_state == "unpublished" else ValidationSeverity.error
        assert validation_result.error_count == int(expected_severity == ValidationSeverity.error)
        assert validation_result.warning_count == int(expected_severity == ValidationSeverity.warning)
        assert validation_result.findings[0].severity == expected_severity
        assert validation_result.findings[0].field_path == expected_field_path

        if child_state == "unpublished":
            published_workflow, published_version, warning = await service.publish_workflow_version(
                workflow_id=parent.id,
                version=version.version,
            )
            assert published_workflow.published_version_id == published_version.id
            assert "has no published version" in warning
        else:
            with pytest.raises(WorkflowPublishValidationError) as exc_info:
                await service.publish_workflow_version(workflow_id=parent.id, version=version.version)
            assert exc_info.value.validation_result.error_count == 1
            assert exc_info.value.validation_result.findings[0].field_path == expected_field_path


@pytest.mark.asyncio
async def test_invocation_schema_uses_published_version_and_filters_trigger_types(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    workflow = Workflow(
        name=f"invocation-schema-{uuid4().hex[:8]}",
        created_by=test_user.id,
        project_id=test_project_id,
        current_version=2,
        is_enabled=False,
    )
    test_db_session.add(workflow)
    await test_db_session.flush()

    published_definition = {
        "triggers": [
            {"id": "manual", "type": "manual_trigger", "parameters": {}},
            {
                "id": "child_entry",
                "name": "Child Entry",
                "type": "subworkflow_trigger",
                "parameters": {
                    "input_schema": {
                        "type": "object",
                        "properties": {"username": {"type": "string"}},
                        "required": ["username"],
                    }
                },
            },
            {"id": "child_entry_empty", "type": "subworkflow_trigger", "parameters": {}},
        ]
    }
    published_version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=published_definition,
        name="Release 1",
        created_by=test_user.id,
    )
    draft_version = WorkflowVersion(
        workflow_id=workflow.id,
        version=2,
        schema_version="2.0.0",
        workflow_definition={
            "triggers": [
                {
                    "id": "draft_only",
                    "name": "Draft Only",
                    "type": "subworkflow_trigger",
                    "parameters": {"input_schema": {"type": "object", "properties": {"draft": {"type": "boolean"}}}},
                }
            ]
        },
        created_by=test_user.id,
    )
    test_db_session.add_all([published_version, draft_version])
    await test_db_session.flush()
    workflow.published_version_id = published_version.id
    workflow.is_enabled = True
    await test_db_session.flush()

    result = await WorkflowService(test_db_session, test_user).get_workflow_invocation_schema(workflow)

    assert result.workflow_id == workflow.id
    assert result.published_version_id == published_version.id
    assert result.published_version == 1
    assert result.published_version_name == "Release 1"
    assert result.published_version_created_at == published_version.created_at
    assert result.is_eligible is True
    assert [trigger.trigger_node_id for trigger in result.triggers] == ["child_entry", "child_entry_empty"]
    assert result.triggers[0].input_schema == {
        "type": "object",
        "properties": {"username": {"type": "string"}},
        "required": ["username"],
    }
    assert result.triggers[1].input_schema == {}


@pytest.mark.asyncio
async def test_invocation_schema_rejects_workflow_without_published_version(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    workflow = Workflow(
        name=f"unpublished-{uuid4().hex[:8]}",
        created_by=test_user.id,
        project_id=test_project_id,
        current_version=1,
        is_enabled=False,
    )

    with pytest.raises(WorkflowNotPublishedError):
        await WorkflowService(test_db_session, test_user).get_workflow_invocation_schema(workflow)


@pytest.mark.asyncio
async def test_published_workflow_without_subworkflow_trigger_has_empty_invocation_schema(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> None:
    workflow = Workflow(
        name=f"no-subworkflow-trigger-{uuid4().hex[:8]}",
        created_by=test_user.id,
        project_id=test_project_id,
        current_version=1,
        is_enabled=False,
    )
    test_db_session.add(workflow)
    await test_db_session.flush()

    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition={"triggers": [{"id": "manual", "type": "manual_trigger", "parameters": {}}]},
        created_by=test_user.id,
    )
    test_db_session.add(version)
    await test_db_session.flush()
    workflow.published_version_id = version.id
    workflow.is_enabled = True
    await test_db_session.flush()

    result = await WorkflowService(test_db_session, test_user).get_workflow_invocation_schema(workflow)

    assert result.published_version_id == version.id
    assert result.published_version == 1
    assert result.is_eligible is False
    assert result.triggers == []
