"""Database-backed validation for sub-workflow references."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationFinding, ValidationSeverity
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType, SubWorkflowExecutorParameters

NodeTarget = tuple[str | None, UUID, UUID | None, str, Mapping[str, Any]]
TargetWorkflow = tuple[str | None, UUID, UUID | None, Mapping[str, Any] | None, bool]


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
        workflow_version_id = parameters.get("workflow_version_id") if isinstance(parameters, dict) else None
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
            continue
        try:
            SubWorkflowExecutorParameters.validate_workflow_id_format(workflow_id)
            target_id = UUID(workflow_id)
        except ValueError as exc:
            findings.append(_invalid_reference_finding(str(exc), node_id, "parameters.workflow_id"))
            continue

        parsed_version_id: UUID | None = None
        if workflow_version_id is not None:
            try:
                parsed_version_id = UUID(str(workflow_version_id))
            except (TypeError, ValueError):
                findings.append(
                    _invalid_reference_finding(
                        "The selected child workflow version is invalid.",
                        node_id,
                        "parameters.workflow_version_id",
                    )
                )

        if not isinstance(trigger_node_id, str) or not trigger_node_id:
            findings.append(
                _invalid_reference_finding(
                    "A sub-workflow step must select a Subworkflow Trigger in the child workflow.",
                    node_id,
                    "parameters.trigger_node_id",
                )
            )
            continue

        target_ids.add(target_id)
        node_targets.append((node_id, target_id, parsed_version_id, trigger_node_id, input_mapping))

    return node_targets, target_ids, findings


async def initialize_subworkflow_version_pins(
    session: AsyncSession,
    workflow_definition: dict[str, Any],
    project_id: UUID,
) -> bool:
    """Pin legacy Sub-workflow references to each child's current published version.

    Returns whether the supplied definition was changed. This is called when a
    parent draft is saved or published, so definitions predating version pins get
    a stable reference the next time they are edited.
    """
    nodes = workflow_definition.get("nodes", [])
    if not isinstance(nodes, list):
        return False

    missing_pin_nodes: list[tuple[dict[str, Any], dict[str, Any], UUID]] = []
    child_ids: set[UUID] = set()
    for node in nodes:
        if not isinstance(node, dict) or node.get("type") != NodeType.SUB_WORKFLOW:
            continue
        parameters = node.get("parameters")
        if not isinstance(parameters, dict) or parameters.get("workflow_version_id"):
            continue
        workflow_id = parameters.get("workflow_id")
        try:
            child_id = UUID(workflow_id) if isinstance(workflow_id, str) else None
        except ValueError:
            child_id = None
        if child_id is None:
            continue
        missing_pin_nodes.append((node, parameters, child_id))
        child_ids.add(child_id)

    if not child_ids:
        return False

    result = await session.exec(
        select(Workflow).where(
            col(Workflow.id).in_(child_ids),
            Workflow.project_id == project_id,
            Workflow.published_version_id.is_not(None),  # type: ignore[union-attr]
        )
    )
    current_versions = {workflow.id: workflow.published_version_id for workflow in result.all()}
    changed = False
    for _, parameters, child_id in missing_pin_nodes:
        version_id = current_versions.get(child_id)
        if version_id is not None:
            parameters["workflow_version_id"] = str(version_id)
            changed = True
    return changed


async def _load_target_workflows(
    session: AsyncSession,
    node_targets: list[NodeTarget],
) -> dict[tuple[UUID, UUID | None], TargetWorkflow]:
    target_ids = {target_id for _, target_id, _, _, _ in node_targets}
    workflow_result = await session.exec(select(Workflow).where(col(Workflow.id).in_(target_ids)))
    workflows = {workflow.id: workflow for workflow in workflow_result.all()}

    selected_ids = {
        pinned_version_id if pinned_version_id is not None else workflows[target_id].published_version_id
        for _, target_id, pinned_version_id, _, _ in node_targets
        if target_id in workflows
    }
    selected_ids.discard(None)
    if not selected_ids:
        return {}

    version_result = await session.exec(select(WorkflowVersion).where(col(WorkflowVersion.id).in_(selected_ids)))
    versions = {version.id: version for version in version_result.all()}
    event_result = await session.exec(
        select(WorkflowPublishEvent.version_id).where(
            col(WorkflowPublishEvent.version_id).in_(selected_ids),
            WorkflowPublishEvent.action == PublishAction.PUBLISHED,
        )
    )
    ever_published_ids = set(event_result.all())

    targets: dict[tuple[UUID, UUID | None], TargetWorkflow] = {}
    for _, target_id, pinned_version_id, _, _ in node_targets:
        workflow = workflows.get(target_id)
        if workflow is None:
            continue
        selected_id = pinned_version_id or workflow.published_version_id
        version = versions.get(selected_id) if selected_id is not None else None
        if version is None or version.workflow_id != target_id:
            targets[(target_id, pinned_version_id)] = (workflow.name, workflow.project_id, None, None, False)
            continue
        is_published = version.id == workflow.published_version_id or version.id in ever_published_ids
        targets[(target_id, pinned_version_id)] = (
            workflow.name,
            workflow.project_id,
            version.id,
            version.workflow_definition,
            is_published,
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


def _validate_target_workflow(
    target_workflow: TargetWorkflow | None,
    project_id: UUID,
    pinned_version_id: UUID | None,
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

    workflow_name, target_project_id, selected_version_id, selected_definition, is_published = target_workflow
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
    if not is_published:
        return [
            _invalid_reference_finding(
                "The selected child workflow version has not been published.",
                node_id,
                "parameters.workflow_version_id" if pinned_version_id else "parameters.workflow_id",
            )
        ]
    selected_trigger = _get_selected_subworkflow_trigger(selected_definition, trigger_node_id)
    if selected_trigger is None:
        return [
            _invalid_reference_finding(
                "The selected Subworkflow Trigger is not available in the pinned child workflow version.",
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
    *,
    require_version_pin: bool = False,
) -> list[ValidationFinding]:
    """Validate each child workflow, its pinned version, trigger, and required inputs."""
    nodes = workflow_definition.get("nodes", [])
    if not isinstance(nodes, list):
        return []

    node_targets, target_ids, findings = _collect_subworkflow_targets(nodes)
    if not target_ids:
        return findings
    if require_version_pin:
        for node_id, _, version_id, _, _ in node_targets:
            if version_id is None:
                findings.append(
                    _invalid_reference_finding(
                        "A published parent workflow must pin a published child workflow version.",
                        node_id,
                        "parameters.workflow_version_id",
                    )
                )

    targets = await _load_target_workflows(session, node_targets)
    for node_id, target_id, version_id, trigger_node_id, input_mapping in node_targets:
        findings.extend(
            _validate_target_workflow(
                targets.get((target_id, version_id)),
                project_id,
                version_id,
                trigger_node_id,
                node_id,
                input_mapping,
            )
        )
    return findings
