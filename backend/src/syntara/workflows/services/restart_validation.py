"""Pre-restart validation for restart-from-failure (AAP-92820).

Shared by ``POST /executions/{id}/validate-restart`` (pure verdict, no state
mutation) and ``POST /executions/{id}/restart`` (re-validates independently
before doing any work, so the restart endpoint is safe to call directly).

Validation is a chain of three checks:

1. **State guard** — source execution must be ``FAILED`` or
   ``COMPLETED_WITH_ERRORS``.
2. **Failure-point eligibility** — every selected id must match a ``failed``
   ``ActivityExecution`` of the source execution *and* a node in the snapshot
   definition that ran.
3. **Version-mismatch guard** — walk the graph from each failure point back to
   the start over the *snapshot* definition, then diff exactly those upstream
   nodes against the *current* definition. Upstream changes reject;
   downstream-only changes pass.

Design decisions (see AAP-92820; revisit if the SDP signs off otherwise):

- Diff compares node ``type``/``parameters``/``settings``/``outputs``/``name``;
  ``position`` (and ``label`` if present) are cosmetic and ignored. Fail-closed
  on anything else.
- Loop-iteration activities (``<node>#iter-<n>``) normalize to their base node
  id for eligibility; iteration-level classification is AAP-92821's job.
- An empty failure-point selection is rejected — the operator must select
  explicitly; the API does not assume "all".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlmodel import select

from syntara.workflows.exceptions import ExecutionNotFoundError
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

#: Statuses a restart may start from. Mirrors the story scope; anything else is
#: rejected with a reason (never silently).
RESTARTABLE_STATUSES = frozenset({ExecutionStatus.FAILED, ExecutionStatus.COMPLETED_WITH_ERRORS})

#: Separator for loop-iteration activity names (``<node>#iter-<n>``). Must match
#: ``_COMPOSITE_ITER_SEP`` in activity_sync_service.py.
LOOP_ITERATION_SEP = "#iter-"

#: Node fields ignored by the version-mismatch diff (purely cosmetic).
COSMETIC_NODE_FIELDS = frozenset({"position", "label"})


@dataclass(frozen=True)
class RestartValidation:
    """Outcome of pre-restart validation (pure verdict, no side effects)."""

    eligible: bool
    reason: str | None = None
    failure_point_ids: list[str] = field(default_factory=list)
    upstream_node_ids: list[str] = field(default_factory=list)
    changed_node_ids: list[str] = field(default_factory=list)
    snapshot_version: int | None = None
    current_version: int | None = None


def strip_iteration_suffix(activity_name: str) -> str:
    """Normalize a loop-iteration activity name to its base node id."""
    base, _, _ = activity_name.rpartition(LOOP_ITERATION_SEP)
    return base or activity_name


def definition_nodes(definition: dict[str, Any]) -> list[dict[str, Any]]:
    """All addressable nodes in a definition: triggers plus graph nodes.

    Triggers live in a separate ``triggers`` list but anchor every upstream
    walk, so they must participate in both traversal and diffing — otherwise
    every path trivially "changes" at its start.
    """
    triggers = definition.get("triggers", []) or []
    nodes = definition.get("nodes", []) or []
    return [entry for entry in [*triggers, *nodes] if isinstance(entry, dict)]


def collect_upstream_node_ids(
    definition: dict[str, Any],
    failure_point_ids: list[str],
) -> set[str]:
    """Return failure points plus every ancestor back to the start (inclusive).

    Built directly from the edge list (``from``/``to``) so validation does not
    depend on the runtime graph backend. Unknown ids contribute only
    themselves; membership against the snapshot is checked separately.
    """
    nodes = definition_nodes(definition)
    edges = definition.get("edges", []) or []
    predecessors: dict[str, set[str]] = {node["id"]: set() for node in nodes if "id" in node}
    for edge in edges:
        src, dst = edge.get("from"), edge.get("to")
        if src is not None and dst is not None:
            predecessors.setdefault(dst, set()).add(src)

    upstream: set[str] = set()
    stack = list(failure_point_ids)
    while stack:
        node_id = stack.pop()
        if node_id in upstream:
            continue
        upstream.add(node_id)
        stack.extend(predecessors.get(node_id, ()))
    return upstream


def canonical_node(node: dict[str, Any]) -> dict[str, Any]:
    """Structural projection of a definition node for the mismatch diff."""
    return {key: value for key, value in node.items() if key not in COSMETIC_NODE_FIELDS}


def diff_upstream_nodes(
    snapshot_definition: dict[str, Any],
    current_definition: dict[str, Any],
    upstream_node_ids: set[str],
) -> list[str]:
    """Return upstream node ids whose structural definition changed.

    A node counts as changed if it was removed, added on the upstream path is
    impossible (upstream derives from the snapshot), or its canonical form
    differs. Sorted for deterministic reasons/messages.
    """
    snapshot_by_id = {node["id"]: node for node in definition_nodes(snapshot_definition) if "id" in node}
    current_by_id = {node["id"]: node for node in definition_nodes(current_definition) if "id" in node}

    def _changed(node_id: str) -> bool:
        if node_id not in current_by_id:
            return True
        return canonical_node(snapshot_by_id.get(node_id, {})) != canonical_node(current_by_id[node_id])

    return sorted(node_id for node_id in upstream_node_ids if _changed(node_id))


def _state_reason(source: Execution) -> str | None:
    """Rejection reason when the source state cannot restart, else None."""
    if source.status not in RESTARTABLE_STATUSES:
        return (
            f"execution is in {source.status.value} state; "
            "restart is available for failed and completed_with_errors executions only"
        )
    return None


def _selection_reason(normalized: list[str], failed_ids: set[str]) -> str | None:
    """Rejection reason for an empty or ineligible selection, else None."""
    if not normalized:
        return "no failure points selected"
    unknown = [point for point in normalized if point not in failed_ids]
    if unknown:
        return f"not failed nodes in this execution: {', '.join(unknown)}"
    return None


def _version_reason(
    normalized: list[str],
    snapshot: WorkflowVersion | None,
    current: WorkflowVersion | None,
) -> tuple[str | None, list[str]]:
    """Rejection reason (and changed nodes) for the version-mismatch guard."""
    if snapshot is None:
        return "original workflow version no longer exists", []
    if current is None:
        return "current workflow version no longer exists", []
    snapshot_def = snapshot.workflow_definition or {}
    current_def = current.workflow_definition or {}
    snapshot_ids = {node.get("id") for node in definition_nodes(snapshot_def)}
    missing = [point for point in normalized if point not in snapshot_ids]
    if missing:
        return f"not nodes in the executed workflow version: {', '.join(missing)}", []
    upstream = collect_upstream_node_ids(snapshot_def, normalized)
    changed = diff_upstream_nodes(snapshot_def, current_def, upstream)
    if changed:
        return (
            "workflow definition changed upstream of the failure point "
            f"({', '.join(changed)}); restart is rejected to avoid corrupt state",
            changed,
        )
    return None, []


async def validate_restart(
    session: AsyncSession,
    execution_id: UUID,
    failure_point_ids: list[str],
) -> RestartValidation:
    """Validate that an execution can be restarted from the given failure points.

    Pure read path: loads the source execution, its failed activities, and the
    snapshot/current definitions, then runs the three-guard chain. Never mutates
    state.

    Raises:
        ExecutionNotFoundError: If the source execution (or its workflow) is gone.

    """
    result = await session.exec(select(Execution).where(Execution.id == execution_id))
    source = result.one_or_none()
    if source is None:
        raise ExecutionNotFoundError(execution_id)

    normalized = sorted({point.strip() for point in failure_point_ids if point and point.strip()})

    activities = (
        await session.exec(
            select(ActivityExecution).where(
                ActivityExecution.execution_id == execution_id,
                ActivityExecution.status == ActivityStatus.FAILED,
            )
        )
    ).all()
    failed_ids = {strip_iteration_suffix(activity.activity_name) for activity in activities}

    snapshot_result = await session.exec(
        select(WorkflowVersion).where(WorkflowVersion.id == source.workflow_version_id)
    )
    snapshot = snapshot_result.one_or_none()

    workflow_result = await session.exec(select(Workflow).where(Workflow.id == source.workflow_id))
    workflow = workflow_result.one_or_none()
    if workflow is None:
        raise ExecutionNotFoundError(execution_id)

    current_result = await session.exec(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.version == workflow.current_version,
        )
    )
    current = current_result.one_or_none()

    version_reason, changed = _version_reason(normalized, snapshot, current)
    reason = _state_reason(source) or _selection_reason(normalized, failed_ids) or version_reason

    snapshot_def = (snapshot.workflow_definition or {}) if snapshot is not None else {}
    snapshot_version = snapshot.version if snapshot is not None else None
    upstream = collect_upstream_node_ids(snapshot_def, normalized)
    if reason is not None:
        return RestartValidation(
            eligible=False,
            reason=reason,
            failure_point_ids=normalized,
            upstream_node_ids=sorted(upstream),
            changed_node_ids=changed,
            snapshot_version=snapshot_version,
            current_version=workflow.current_version,
        )

    return RestartValidation(
        eligible=True,
        failure_point_ids=normalized,
        upstream_node_ids=sorted(upstream),
        snapshot_version=snapshot_version,
        current_version=workflow.current_version,
    )
