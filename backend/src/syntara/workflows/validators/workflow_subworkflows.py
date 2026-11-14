"""Database-backed validation for sub-workflow references."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationFinding, ValidationSeverity
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.utils.namespace_resolver import TEMPLATE_PATTERN
from syntara.workflows.validators.workflow_definition import (
    _known_node_output_schema,
    _output_types_compatible,
    _schema_type_at_path,
)
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType, SubWorkflowExecutorParameters

NodeTarget = tuple[str | None, UUID, str, Mapping[str, Any]]
TargetWorkflow = tuple[str | None, UUID, UUID | None, Mapping[str, Any] | None]
_SUBWORKFLOW_OUTPUT_PATH_PREFIX = ("Result", "outputs")


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

        target_id: UUID | None = None
        if not isinstance(workflow_id, str):
            findings.append(
                _invalid_reference_finding(
                    "A sub-workflow step must select a child workflow in this Project.",
                    node_id,
                    "parameters.workflow_id",
                )
            )
        else:
            try:
                SubWorkflowExecutorParameters.validate_workflow_id_format(workflow_id)
                target_id = UUID(workflow_id)
            except ValueError as exc:
                findings.append(_invalid_reference_finding(str(exc), node_id, "parameters.workflow_id"))

        if not isinstance(trigger_node_id, str) or not trigger_node_id:
            findings.append(
                _invalid_reference_finding(
                    "A sub-workflow step must select a Subworkflow Trigger in the child workflow.",
                    node_id,
                    "parameters.trigger_node_id",
                )
            )
        if target_id is None or not isinstance(trigger_node_id, str) or not trigger_node_id:
            continue

        target_ids.add(target_id)
        node_targets.append((node_id, target_id, trigger_node_id, input_mapping))

    return node_targets, target_ids, findings


async def _load_target_workflows(
    session: AsyncSession,
    node_targets: list[NodeTarget],
) -> dict[UUID, TargetWorkflow]:
    target_ids = {target_id for _, target_id, _, _ in node_targets}
    workflow_result = await session.exec(select(Workflow).where(col(Workflow.id).in_(target_ids)))
    workflows = {workflow.id: workflow for workflow in workflow_result.all()}

    selected_ids = {
        workflows[target_id].published_version_id for _, target_id, _, _ in node_targets if target_id in workflows
    }
    selected_ids.discard(None)
    if not selected_ids:
        return {}

    version_result = await session.exec(select(WorkflowVersion).where(col(WorkflowVersion.id).in_(selected_ids)))
    versions = {version.id: version for version in version_result.all()}
    targets: dict[UUID, TargetWorkflow] = {}
    for _, target_id, _, _ in node_targets:
        workflow = workflows.get(target_id)
        if workflow is None:
            continue
        selected_id = workflow.published_version_id
        version = versions.get(selected_id) if selected_id is not None else None
        if version is None or version.workflow_id != target_id:
            targets[target_id] = (workflow.name, workflow.project_id, None, None)
            continue
        targets[target_id] = (
            workflow.name,
            workflow.project_id,
            version.id,
            version.workflow_definition,
        )
    return targets


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


def _declared_output_type_for_expression(
    expression: str,
    nodes_by_id: Mapping[str, dict[str, Any]],
    subworkflow_output_schemas: Mapping[str, dict[str, Any]],
) -> str | None:
    match = TEMPLATE_PATTERN.fullmatch(expression.strip())
    if match is None:
        return None

    source_id, separator, source_path = match.group(1).partition(".")
    if not separator:
        return None

    source_segments = source_path.split(".")
    prefix_length = len(_SUBWORKFLOW_OUTPUT_PATH_PREFIX)
    if (
        tuple(source_segments[:prefix_length]) == _SUBWORKFLOW_OUTPUT_PATH_PREFIX
        and len(source_segments) > prefix_length
    ):
        output_schema = subworkflow_output_schemas.get(source_id)
        is_missing, source_type = _schema_type_at_path(output_schema, ".".join(source_segments[prefix_length:]))
        return None if is_missing else source_type

    source_schema = _known_node_output_schema(nodes_by_id.get(source_id, {}))
    is_missing, source_type = _schema_type_at_path(source_schema, source_path)
    return None if is_missing else source_type


def _parent_input_type_findings(
    *,
    node_id: str | None,
    input_mapping: Mapping[str, Any],
    input_schema: Mapping[str, Any],
    nodes_by_id: Mapping[str, dict[str, Any]],
    subworkflow_output_schemas: Mapping[str, dict[str, Any]],
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for input_path, expression in input_mapping.items():
        if not isinstance(input_path, str) or not isinstance(expression, str):
            continue
        _input_missing, input_type = _schema_type_at_path(dict(input_schema), input_path)
        source_type = _declared_output_type_for_expression(expression, nodes_by_id, subworkflow_output_schemas)
        if input_type is None or source_type is None or _output_types_compatible(source_type, input_type):
            continue
        findings.append(
            ValidationFinding(
                severity=ValidationSeverity.error,
                category=ValidationCategory.schema_violation,
                message=(
                    f"Input mapping for '{input_path}' has source type '{source_type}', "
                    f"but the child input expects '{input_type}'."
                ),
                node_id=node_id,
                field_path=f"parameters.input_mapping.{input_path}",
            )
        )
    return findings


def _validate_target_workflow(
    target_workflow: TargetWorkflow | None,
    project_id: UUID,
    trigger_node_id: str,
    node_id: str | None,
    input_mapping: Mapping[str, Any],
) -> list[ValidationFinding]:
    if target_workflow is None:
        return [
            _invalid_reference_finding(
                "The selected child workflow is no longer available.", node_id, "parameters.workflow_id"
            )
        ]

    workflow_name, target_project_id, selected_version_id, selected_definition = target_workflow
    if target_project_id != project_id:
        return [
            _invalid_reference_finding(
                "A sub-workflow step must reference a workflow in the same Project.",
                node_id,
                "parameters.workflow_id",
            )
        ]
    if selected_version_id is None:
        return [
            _invalid_reference_finding(
                "The selected child workflow must have a published version.", node_id, "parameters.workflow_id"
            )
        ]
    selected_trigger = _get_selected_subworkflow_trigger(selected_definition, trigger_node_id)
    if selected_trigger is None:
        return [
            _invalid_reference_finding(
                "The selected Subworkflow Trigger is not available in the latest published child workflow version.",
                node_id,
                "parameters.trigger_node_id",
            )
        ]

    return [
        ValidationFinding(
            severity=ValidationSeverity.warning,
            category=ValidationCategory.missing_field,
            message=(f"Child workflow '{workflow_name}' requires input '{input_name}', not provided in input_mapping"),
            node_id=node_id,
            field_path=f"parameters.input_mapping.{input_name}",
        )
        for input_name in _required_trigger_input_names(selected_trigger)
        if input_name not in input_mapping
    ]


async def validate_subworkflow_project_references(
    session: AsyncSession,
    workflow_definition: dict[str, Any],
    project_id: UUID,
) -> list[ValidationFinding]:
    """Validate each child workflow's latest published version, trigger, and required inputs."""
    nodes = workflow_definition.get("nodes", [])
    if not isinstance(nodes, list):
        return []

    node_targets, target_ids, findings = _collect_subworkflow_targets(nodes)
    if not target_ids:
        return findings
    targets = await _load_target_workflows(session, node_targets)
    nodes_by_id = {node["id"]: node for node in nodes if isinstance(node, dict) and isinstance(node.get("id"), str)}
    subworkflow_output_schemas: dict[str, dict[str, Any]] = {}
    for node_id, target_id, trigger_node_id, _ in node_targets:
        target_workflow = targets.get(target_id)
        if node_id is None or target_workflow is None:
            continue
        _, target_project_id, version_id, target_definition = target_workflow
        if target_project_id != project_id or version_id is None:
            continue
        trigger = _get_selected_subworkflow_trigger(target_definition, trigger_node_id)
        parameters = trigger.get("parameters") if isinstance(trigger, Mapping) else None
        output_schema = parameters.get("output_schema") if isinstance(parameters, Mapping) else None
        if isinstance(output_schema, dict):
            subworkflow_output_schemas[node_id] = output_schema

    for node_id, target_id, trigger_node_id, input_mapping in node_targets:
        target_workflow = targets.get(target_id)
        findings.extend(
            _validate_target_workflow(
                target_workflow,
                project_id,
                trigger_node_id,
                node_id,
                input_mapping,
            )
        )
        if target_workflow is None or target_workflow[1] != project_id or target_workflow[2] is None:
            continue
        trigger = _get_selected_subworkflow_trigger(target_workflow[3], trigger_node_id)
        parameters = trigger.get("parameters") if isinstance(trigger, Mapping) else None
        input_schema = parameters.get("input_schema") if isinstance(parameters, Mapping) else None
        if isinstance(input_schema, Mapping):
            findings.extend(
                _parent_input_type_findings(
                    node_id=node_id,
                    input_mapping=input_mapping,
                    input_schema=input_schema,
                    nodes_by_id=nodes_by_id,
                    subworkflow_output_schemas=subworkflow_output_schemas,
                )
            )
    return findings
