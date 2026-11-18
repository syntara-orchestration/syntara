"""Database-backed validation for sub-workflow references."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationFinding, ValidationSeverity
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType, SubWorkflowExecutorParameters

from .template_expressions import extract_element_expressions

NodeTarget = tuple[str | None, UUID, str, Mapping[str, Any]]
TargetWorkflow = tuple[str | None, UUID, UUID | None, Mapping[str, Any] | None]


def _invalid_reference_finding(message: str, node_id: str | None, field_path: str) -> ValidationFinding:
    return ValidationFinding(
        severity=ValidationSeverity.error,
        category=ValidationCategory.invalid_reference,
        message=message,
        node_id=node_id,
        field_path=field_path,
    )


def _collect_subworkflow_targets(
    nodes: list[Any],
) -> tuple[list[NodeTarget], set[UUID], list[ValidationFinding]]:
    node_targets: list[NodeTarget] = []
    target_ids: set[UUID] = set()
    findings: list[ValidationFinding] = []

    for node in nodes:
        if not isinstance(node, dict) or node.get("type") != NodeType.SUB_WORKFLOW:
            continue

        parameters = node.get("parameters")
        workflow_id = parameters.get("workflow_id") if isinstance(parameters, dict) else None
        trigger_node_id = parameters.get("trigger_node_id") if isinstance(parameters, dict) else None
        input_mapping = parameters.get("input_mapping") if isinstance(parameters, dict) else None
        if not isinstance(input_mapping, Mapping):
            input_mapping = {}
        node_id = node.get("id") if isinstance(node.get("id"), str) else None
        if not isinstance(workflow_id, str):
            findings.append(
                _invalid_reference_finding(
                    "A sub-workflow step must select a child workflow in this Project.",
                    node_id,
                    "parameters.workflow_id",
                )
            )
            workflow_id = None
        else:
            try:
                SubWorkflowExecutorParameters.validate_workflow_id_format(workflow_id)
            except ValueError as exc:
                findings.append(_invalid_reference_finding(str(exc), node_id, "parameters.workflow_id"))
                workflow_id = None

        if not isinstance(trigger_node_id, str) or not trigger_node_id:
            findings.append(
                _invalid_reference_finding(
                    "A sub-workflow step must select a Subworkflow Trigger in the child workflow.",
                    node_id,
                    "parameters.trigger_node_id",
                )
            )

        if workflow_id is None or not isinstance(trigger_node_id, str) or not trigger_node_id:
            continue

        target_id = UUID(workflow_id)
        target_ids.add(target_id)
        node_targets.append((node_id, target_id, trigger_node_id, input_mapping))

    return node_targets, target_ids, findings


async def _load_target_workflows(
    session: AsyncSession,
    target_ids: set[UUID],
) -> dict[UUID, TargetWorkflow]:
    result = await session.exec(
        select(Workflow, WorkflowVersion)
        .outerjoin(WorkflowVersion, col(Workflow.published_version_id) == col(WorkflowVersion.id))
        .where(col(Workflow.id).in_(target_ids))
    )
    return {
        workflow.id: (
            workflow.name,
            workflow.project_id,
            workflow.published_version_id,
            published_version.workflow_definition if published_version else None,
        )
        for workflow, published_version in result.all()
    }


def _get_selected_subworkflow_trigger(
    definition: Mapping[str, Any] | None,
    trigger_node_id: str,
) -> Mapping[str, Any] | None:
    if not isinstance(definition, Mapping):
        return None

    triggers = definition.get("triggers")
    if not isinstance(triggers, list):
        return None

    return next(
        (
            trigger
            for trigger in triggers
            if isinstance(trigger, Mapping)
            and trigger.get("type") == NodeType.SUBWORKFLOW_TRIGGER
            and trigger.get("id") == trigger_node_id
        ),
        None,
    )


def _required_trigger_input_names(trigger: Mapping[str, Any]) -> list[str]:
    parameters = trigger.get("parameters")
    input_schema = parameters.get("input_schema") if isinstance(parameters, Mapping) else None
    required = input_schema.get("required") if isinstance(input_schema, Mapping) else None
    if not isinstance(required, list):
        return []
    return [name for name in required if isinstance(name, str)]


def _referenced_child_output_paths(
    workflow_definition: Mapping[str, Any],
    subworkflow_node_id: str | None,
) -> set[tuple[str, ...]]:
    """Find declared output paths referenced through a Sub-workflow expression."""
    if subworkflow_node_id is None:
        return set()

    triggers = workflow_definition.get("triggers")
    nodes = workflow_definition.get("nodes")
    elements = [*(triggers if isinstance(triggers, list) else []), *(nodes if isinstance(nodes, list) else [])]
    referenced_paths: set[tuple[str, ...]] = set()
    for element in elements:
        if not isinstance(element, dict):
            continue
        for expression, _field_path in extract_element_expressions(element):
            scope, *path = expression.split(".")
            if scope != subworkflow_node_id or not path:
                continue
            result_field, *path = path
            if result_field != "Result" or not path:
                continue
            outputs_field, *output_path = path
            if outputs_field != "outputs" or not output_path:
                continue
            referenced_paths.add(tuple(output_path))
    return referenced_paths


def _allows_composed_schema_path(schema: Mapping[str, Any], path: tuple[str, ...]) -> bool | None:
    """Check paths through JSON Schema composition keywords when present."""
    for union_key in ("anyOf", "oneOf"):
        branches = schema.get(union_key)
        if isinstance(branches, list) and branches:
            return any(isinstance(branch, Mapping) and _schema_allows_nested_path(branch, path) for branch in branches)
    all_of = schema.get("allOf")
    if isinstance(all_of, list) and all_of:
        return all(isinstance(branch, Mapping) and _schema_allows_nested_path(branch, path) for branch in all_of)
    return None


def _allows_object_schema_path(schema: Mapping[str, Any], segment: str, remaining: tuple[str, ...]) -> bool:
    """Check an object property or additional property against its schema."""
    properties = schema.get("properties")
    if isinstance(properties, Mapping) and segment in properties:
        child_schema = properties[segment]
        return not remaining or (
            isinstance(child_schema, Mapping) and _schema_allows_nested_path(child_schema, remaining)
        )

    if schema.get("additionalProperties") is False:
        return False
    additional_schema = schema.get("additionalProperties")
    return (
        not remaining
        or not isinstance(additional_schema, Mapping)
        or _schema_allows_nested_path(additional_schema, remaining)
    )


def _allows_array_schema_path(schema: Mapping[str, Any], segment: str, remaining: tuple[str, ...]) -> bool:
    """Check a numeric array index and its item schema."""
    item_schema = schema.get("items")
    return (
        segment.isdecimal()
        and isinstance(item_schema, Mapping)
        and (not remaining or _schema_allows_nested_path(item_schema, remaining))
    )


def _schema_allows_nested_path(schema: Mapping[str, Any], path: tuple[str, ...]) -> bool:
    """Check nested object/array path segments against a JSON Schema fragment."""
    if not path or not schema:
        return True

    composed_result = _allows_composed_schema_path(schema, path)
    if composed_result is not None:
        return composed_result

    schema_type = schema.get("type")
    schema_types = schema_type if isinstance(schema_type, list) else [schema_type]
    has_object_type = "object" in schema_types or schema_type is None
    has_array_type = "array" in schema_types
    if not has_object_type and not has_array_type:
        return False

    segment, *remaining = path
    remaining_path = tuple(remaining)
    if has_object_type:
        return _allows_object_schema_path(schema, segment, remaining_path)
    # Numeric path segments can address array items in a declared array output.
    return _allows_array_schema_path(schema, segment, remaining_path)


def _is_declared_output_path(output_schema: Mapping[str, Any] | None, path: tuple[str, ...]) -> bool:
    """Check that the first path segment is public and nested segments fit its schema."""
    if not path or not isinstance(output_schema, Mapping):
        return False

    properties = output_schema.get("properties")
    if not isinstance(properties, Mapping) or path[0] not in properties:
        return False

    field_schema = properties[path[0]]
    return len(path) == 1 or (isinstance(field_schema, Mapping) and _schema_allows_nested_path(field_schema, path[1:]))


def _validate_target_workflow(
    target_workflow: TargetWorkflow | None,
    project_id: UUID,
    trigger_node_id: str,
    node_id: str | None,
    input_mapping: Mapping[str, Any],
    parent_workflow_definition: Mapping[str, Any],
) -> list[ValidationFinding]:
    if target_workflow is None:
        return [
            _invalid_reference_finding(
                "The selected child workflow is no longer available.", node_id, "parameters.workflow_id"
            )
        ]

    _workflow_name, target_project_id, published_version_id, published_definition = target_workflow
    if target_project_id != project_id:
        return [
            _invalid_reference_finding(
                "A sub-workflow step must reference a workflow in the same Project.",
                node_id,
                "parameters.workflow_id",
            )
        ]
    if published_version_id is None:
        return [
            ValidationFinding(
                severity=ValidationSeverity.warning,
                category=ValidationCategory.invalid_reference,
                message="The selected child workflow has no published version",
                node_id=node_id,
                field_path="parameters.workflow_id",
            )
        ]
    selected_trigger = _get_selected_subworkflow_trigger(published_definition, trigger_node_id)
    if selected_trigger is None:
        return [
            _invalid_reference_finding(
                "The selected Subworkflow Trigger is not available in the child workflow's published version.",
                node_id,
                "parameters.trigger_node_id",
            )
        ]

    findings = [
        ValidationFinding(
            severity=ValidationSeverity.warning,
            category=ValidationCategory.missing_field,
            message=f"The selected child workflow requires input '{input_name}', not provided in input_mapping",
            node_id=node_id,
            field_path=f"parameters.input_mapping.{input_name}",
        )
        for input_name in _required_trigger_input_names(selected_trigger)
        if input_name not in input_mapping
    ]

    trigger_parameters = selected_trigger.get("parameters")
    output_schema = trigger_parameters.get("output_schema") if isinstance(trigger_parameters, Mapping) else None
    referenced_paths = _referenced_child_output_paths(parent_workflow_definition, node_id)
    stale_output_paths = sorted(path for path in referenced_paths if not _is_declared_output_path(output_schema, path))
    findings.extend(
        [
            ValidationFinding(
                severity=ValidationSeverity.warning,
                category=ValidationCategory.invalid_reference,
                message=(
                    f"Parent references child output '{'.'.join(path)}' which is not declared "
                    "by the selected Subworkflow Trigger"
                ),
                node_id=node_id,
                field_path=f"Result.outputs.{'.'.join(path)}",
            )
            for path in stale_output_paths
        ]
    )
    return findings


async def validate_subworkflow_project_references(
    session: AsyncSession,
    workflow_definition: dict[str, Any],
    project_id: UUID,
) -> list[ValidationFinding]:
    """Validate child workflow targets, required inputs, and referenced public outputs.

    Reuse the parameter model's UUID check because the service can receive raw
    workflow-definition dictionaries. Collect IDs first to batch the lookup. Findings for
    missing child inputs, unpublished children, or undeclared child outputs are warnings.
    """
    nodes = workflow_definition.get("nodes", [])
    if not isinstance(nodes, list):
        return []

    node_targets, target_ids, findings = _collect_subworkflow_targets(nodes)
    if not target_ids:
        return findings

    target_workflows = await _load_target_workflows(session, target_ids)
    for node_id, target_id, trigger_node_id, input_mapping in node_targets:
        findings.extend(
            _validate_target_workflow(
                target_workflows.get(target_id),
                project_id,
                trigger_node_id,
                node_id,
                input_mapping,
                workflow_definition,
            )
        )

    return findings
