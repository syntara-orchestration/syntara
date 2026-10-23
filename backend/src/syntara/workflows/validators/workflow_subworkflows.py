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

    workflow_name, target_project_id, published_version_id, published_definition = target_workflow
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
            _invalid_reference_finding(
                "The selected child workflow must have a published version.", node_id, "parameters.workflow_id"
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
    """Ensure each configured child workflow is invokable from the parent Project.

    Reuse the parameter model's UUID check because the service can receive raw
    workflow-definition dictionaries. Collect IDs first to batch the lookup.
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
            )
        )

    return findings
