"""Cycle detection for published Sub-workflow dependencies."""

from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationFinding, ValidationSeverity
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType, SubWorkflowExecutorParameters

WorkflowContext = tuple[UUID | None, str]


@dataclass(frozen=True)
class _DependencyReference:
    node_id: str | None
    workflow_id: UUID
    trigger_id: str


@dataclass(frozen=True)
class _DependencyEdge:
    target: WorkflowContext
    node_id: str | None


def _trigger_ids(definition: Mapping[str, Any]) -> list[str]:
    triggers = definition.get("triggers")
    if not isinstance(triggers, list):
        return []
    return [
        trigger_id
        for trigger in triggers
        if isinstance(trigger, Mapping) and isinstance((trigger_id := trigger.get("id")), str)
    ]


def _reachable_node_ids(definition: Mapping[str, Any], trigger_id: str) -> set[str]:
    raw_edges = definition.get("edges")
    if not isinstance(raw_edges, list):
        return set()

    successors: dict[str, list[str]] = defaultdict(list)
    for edge in raw_edges:
        if isinstance(edge, Mapping) and isinstance(edge.get("from"), str) and isinstance(edge.get("to"), str):
            successors[edge["from"]].append(edge["to"])

    reachable = {trigger_id}
    pending = deque([trigger_id])
    while pending:
        current = pending.popleft()
        for successor in successors.get(current, []):
            if successor not in reachable:
                reachable.add(successor)
                pending.append(successor)
    return reachable


def _reachable_subworkflow_references(
    definition: Mapping[str, Any],
    trigger_id: str,
) -> list[_DependencyReference]:
    nodes = definition.get("nodes")
    if not isinstance(nodes, list):
        return []

    reachable = _reachable_node_ids(definition, trigger_id)
    references: list[_DependencyReference] = []
    for node in nodes:
        if not isinstance(node, Mapping) or node.get("type") != NodeType.SUB_WORKFLOW:
            continue
        node_id = node.get("id") if isinstance(node.get("id"), str) else None
        if node_id is None or node_id not in reachable:
            continue

        parameters = node.get("parameters")
        if not isinstance(parameters, Mapping):
            continue
        workflow_id = parameters.get("workflow_id")
        trigger_node_id = parameters.get("trigger_node_id")
        if not isinstance(workflow_id, str) or not isinstance(trigger_node_id, str) or not trigger_node_id:
            continue
        try:
            target_id = SubWorkflowExecutorParameters.parse_workflow_id(workflow_id)
        except ValueError:
            continue
        references.append(_DependencyReference(node_id, target_id, trigger_node_id))
    return references


async def _load_published_workflows(
    session: AsyncSession,
    workflow_ids: set[UUID],
) -> dict[UUID, tuple[UUID | None, Mapping[str, Any]]]:
    if not workflow_ids:
        return {}

    workflow_result = await session.exec(select(Workflow).where(col(Workflow.id).in_(workflow_ids)))
    workflows = {workflow.id: workflow for workflow in workflow_result.all()}
    version_ids = {workflow.published_version_id for workflow in workflows.values()}
    version_ids.discard(None)
    if not version_ids:
        return {}

    version_result = await session.exec(select(WorkflowVersion).where(col(WorkflowVersion.id).in_(version_ids)))
    versions = {version.id: version for version in version_result.all()}
    published: dict[UUID, tuple[UUID | None, Mapping[str, Any]]] = {}
    for workflow_id, workflow in workflows.items():
        version_id = workflow.published_version_id
        version = versions.get(version_id) if version_id is not None else None
        if (
            version is None
            or version.workflow_id != workflow_id
            or not isinstance(version.workflow_definition, Mapping)
        ):
            continue
        published[workflow_id] = (workflow.project_id, version.workflow_definition)
    return published


def _has_selected_subworkflow_trigger(definition: Mapping[str, Any], trigger_id: str) -> bool:
    triggers = definition.get("triggers")
    if not isinstance(triggers, list):
        return False
    return any(
        isinstance(trigger, Mapping)
        and trigger.get("id") == trigger_id
        and trigger.get("type") == NodeType.SUBWORKFLOW_TRIGGER
        for trigger in triggers
    )


async def _build_dependency_graph(
    session: AsyncSession,
    workflow_definition: Mapping[str, Any],
    project_id: UUID,
    workflow_id: UUID | None,
) -> tuple[dict[WorkflowContext, list[_DependencyEdge]], list[WorkflowContext]]:
    root_contexts = [(workflow_id, trigger_id) for trigger_id in _trigger_ids(workflow_definition)]
    definitions: dict[UUID, tuple[UUID | None, Mapping[str, Any]]] = {}
    if workflow_id is not None:
        definitions[workflow_id] = (project_id, workflow_definition)

    graph: dict[WorkflowContext, list[_DependencyEdge]] = {}
    pending = deque((context, workflow_definition) for context in root_contexts)
    while pending:
        contexts: list[tuple[WorkflowContext, Mapping[str, Any]]] = []
        seen_in_batch: set[WorkflowContext] = set()
        while pending:
            context, definition = pending.popleft()
            if context not in graph and context not in seen_in_batch:
                contexts.append((context, definition))
                seen_in_batch.add(context)

        references_by_context = {
            context: _reachable_subworkflow_references(definition, context[1]) for context, definition in contexts
        }
        target_ids = {
            reference.workflow_id
            for references in references_by_context.values()
            for reference in references
            if reference.workflow_id != workflow_id
        }
        newly_loaded = await _load_published_workflows(session, target_ids - definitions.keys())
        definitions.update(newly_loaded)

        for context, _ in contexts:
            graph[context] = []
            for reference in references_by_context[context]:
                target = definitions.get(reference.workflow_id)
                if target is None:
                    continue
                target_project_id, target_definition = target
                if target_project_id != project_id or not _has_selected_subworkflow_trigger(
                    target_definition, reference.trigger_id
                ):
                    continue

                target_context = (reference.workflow_id, reference.trigger_id)
                graph[context].append(_DependencyEdge(target_context, reference.node_id))
                if target_context not in graph:
                    pending.append((target_context, target_definition))

    return graph, root_contexts


def _cycle_findings(
    graph: Mapping[WorkflowContext, list[_DependencyEdge]],
    roots: list[WorkflowContext],
) -> list[ValidationFinding]:
    colors: dict[WorkflowContext, int] = {}
    findings: dict[tuple[str | None, tuple[WorkflowContext, ...]], ValidationFinding] = {}

    for root in roots:
        if colors.get(root, 0) != 0:
            continue

        active_path = [root]
        active_positions = {root: 0}
        stack: list[tuple[WorkflowContext, int]] = [(root, 0)]
        colors[root] = 1
        while stack:
            context, edge_index = stack[-1]
            edges = graph.get(context, [])
            if edge_index >= len(edges):
                stack.pop()
                active_path.pop()
                active_positions.pop(context)
                colors[context] = 2
                continue

            edge = edges[edge_index]
            stack[-1] = (context, edge_index + 1)
            target_color = colors.get(edge.target, 0)
            if target_color == 1:
                cycle_start = active_positions[edge.target]
                cycle = (*active_path[cycle_start:], edge.target)
                key = (edge.node_id, cycle)
                workflow_path = " → ".join(str(workflow_id) for workflow_id, _ in cycle)
                trigger_path = " → ".join(trigger_id for _, trigger_id in cycle)
                findings[key] = ValidationFinding(
                    severity=ValidationSeverity.error,
                    category=ValidationCategory.invalid_reference,
                    message=(
                        f"Sub-workflow dependency cycle detected ({workflow_path}; triggers {trigger_path}). "
                        "Remove or redirect this Sub-workflow step to break the cycle."
                    ),
                    node_id=edge.node_id,
                    field_path="parameters.workflow_id",
                )
            elif target_color == 0:
                active_positions[edge.target] = len(active_path)
                active_path.append(edge.target)
                stack.append((edge.target, 0))
                colors[edge.target] = 1
    return list(findings.values())


async def validate_subworkflow_dependency_cycles(
    session: AsyncSession,
    workflow_definition: Mapping[str, Any],
    project_id: UUID,
    workflow_id: UUID | None,
) -> list[ValidationFinding]:
    """Report cycles reachable from workflow triggers through selected child triggers."""
    graph, roots = await _build_dependency_graph(session, workflow_definition, project_id, workflow_id)
    return _cycle_findings(graph, roots)
