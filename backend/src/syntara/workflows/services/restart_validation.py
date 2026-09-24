"""Pre-restart validation for restart-from-failure (AAP-92820).

Shared by ``POST /executions/{id}/validate-restart-from-failure`` (pure verdict,
no state mutation) and ``POST /executions/{id}/restart-from-failure`` (re-validates independently
before doing any work, so the restart endpoint is safe to call directly).

Validation is a chain of checks:

1. **State guard** — source execution must be ``FAILED`` or
   ``COMPLETED_WITH_ERRORS``.
2. **Failure-point eligibility** — every selected id must match a ``failed``
   ``ActivityExecution`` of the source execution *and* a node in the retained
   workflow version that ran.
3. **Converge-mootness guard** — failure points feeding an already-completed
   converge node are rejected (the workflow moved past those branches); a
   failed converge keeps its branch failures as candidates.
4. **Retained-version guard** — restart always runs against the exact
   workflow version captured when the original run started
   (``source.workflow_version_id``). There is no comparison against the
   currently saved definition and no diffing — later edits never affect a
   retry (SDP ANSTRAT-1779 R9/R10). Rejected only if that version no longer
   exists, or a selected id is not a node in it.
5. **Sanitized-output guard** — persisted ``output_data`` is credential-scrubbed
   on write while the live run consumed raw values. Redacted *field paths*
   reject, but only when actually referenced from the restart execution path
   (selected failure points plus their downstream) — unreferenced markers are
   harmless. A whole-namespace ``${node}`` reference taints on any marker
   under that node. Loop iterations are evaluated per-iteration (any tainted
   iteration taints the node); iteration-suffixed selections are rejected
   with guidance to select base node ids. Truncated output is out of scope
   for restart validation — it affects all executions equally and is not
   restart-specific (SDP scope reduction, R9a).

   For an **explicit** selection, a sanitized dependency always rejects. For
   the **default** selection (empty input — see below), a sanitized
   dependency instead expands the restart points to include the sanitized
   node, repeated until no dependency remains, and reports what was added
   instead of rejecting (SDP AC-15/R9a). Either way, the response also
   reports ``sanitized_replacements`` — for *every* currently-failed node
   (not just the ones requested), which sanitized node(s) it would need to
   be replaced by — so the UI can disallow selecting a failed node
   explicitly before the user even submits a request (per Bill Wei,
   2026-09-24: "so that the UI can disallow replaced nodes being selected").

Design decisions (SDP ANSTRAT-1779, aligned 2026-09-24):

- Loop-iteration activities (``<node>#iter-<n>``) normalize to their base node
  id for eligibility; iteration-level classification is AAP-92821's job.
- An empty failure-point selection means "all currently failed nodes"
  (SDP R11/AC-15) — not an error. A non-empty selection means exactly those
  nodes. Rejected only if there are no failed nodes at all to default to.
- The response includes a re-run step count per failure point and a
  deduplicated total across the whole selection (SDP R11a/AC-2), computed
  against the retained version — and, for the default selection, against
  whatever nodes were auto-included to resolve a sanitized dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlmodel import select

from syntara.workflows.exceptions import ExecutionNotFoundError
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.utils.template_refs import find_template_refs, paths_overlap
from syntara.workflows.workflow_engine.utils.credential_scrubber import REDACTED

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

#: Statuses a restart may start from. Mirrors the story scope; anything else is
#: rejected with a reason (never silently).
RESTARTABLE_STATUSES = frozenset({ExecutionStatus.FAILED, ExecutionStatus.COMPLETED_WITH_ERRORS})

#: Separator for loop-iteration activity names (``<node>#iter-<n>``). Must match
#: ``_COMPOSITE_ITER_SEP`` in activity_sync_service.py.
LOOP_ITERATION_SEP = "#iter-"


@dataclass(frozen=True)
class RestartValidation:
    """Outcome of pre-restart validation (pure verdict, no side effects)."""

    eligible: bool
    reason: str | None = None
    failure_point_ids: list[str] = field(default_factory=list)
    upstream_node_ids: list[str] = field(default_factory=list)
    sanitized_node_ids: list[str] = field(default_factory=list)
    auto_included_node_ids: list[str] = field(default_factory=list)
    sanitized_replacements: dict[str, list[str]] = field(default_factory=dict)
    snapshot_version: int | None = None
    step_count_by_failure_point: dict[str, int] = field(default_factory=dict)
    total_step_count: int = 0


def strip_iteration_suffix(activity_name: str) -> str:
    """Normalize a loop-iteration activity name to its base node id."""
    base, _, _ = activity_name.rpartition(LOOP_ITERATION_SEP)
    return base or activity_name


def definition_nodes(definition: dict[str, Any]) -> list[dict[str, Any]]:
    """All addressable nodes in a definition: triggers plus graph nodes.

    Triggers live in a separate ``triggers`` list but anchor every upstream
    walk, so they must participate in traversal — otherwise every path
    trivially "starts" mid-graph.
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
    themselves; membership against the retained version is checked separately.
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


def collect_downstream_node_ids(
    definition: dict[str, Any],
    failure_point_ids: list[str],
) -> set[str]:
    """Return failure points plus every successor downstream (inclusive).

    The restart re-executes exactly this set (for the selected points), so
    only references originating here can consume injected outputs, and its
    size is the re-run step count (SDP R11a/AC-2).
    """
    nodes = definition_nodes(definition)
    edges = definition.get("edges", []) or []
    successors: dict[str, set[str]] = {node["id"]: set() for node in nodes if "id" in node}
    for edge in edges:
        src, dst = edge.get("from"), edge.get("to")
        if src is not None and dst is not None:
            successors.setdefault(src, set()).add(dst)

    downstream: set[str] = set()
    stack = list(failure_point_ids)
    while stack:
        node_id = stack.pop()
        if node_id in downstream:
            continue
        downstream.add(node_id)
        stack.extend(successors.get(node_id, ()))
    return downstream


def _step_counts(definition: dict[str, Any], failure_point_ids: list[str]) -> tuple[dict[str, int], int]:
    """Re-run step count per failure point, plus the deduplicated total.

    Per-point counts are computed independently (a node reachable from two
    selected points is not double-counted within its own point's count); the
    total is the size of the union across the whole selection, matching a
    branch converging back into another selected branch's path.
    """
    per_point = {point: len(collect_downstream_node_ids(definition, [point])) for point in failure_point_ids}
    total = len(collect_downstream_node_ids(definition, failure_point_ids))
    return per_point, total


def _state_reason(source: Execution) -> str | None:
    """Rejection reason when the source state cannot restart, else None."""
    if source.status not in RESTARTABLE_STATUSES:
        return (
            f"execution is in {source.status.value} state; "
            "restart is available for failed and completed_with_errors executions only"
        )
    return None


def _selection_reason(normalized: list[str], failed_ids: set[str]) -> str | None:
    """Rejection reason for an empty or ineligible selection, else None.

    ``normalized`` has already been resolved to the default (all currently
    failed nodes) if the caller's selection was empty, so an empty result
    here only happens when there are no failed nodes at all to default to.
    """
    if not normalized:
        return "no failed nodes in this execution to restart from"
    unknown = [point for point in normalized if point not in failed_ids]
    if unknown:
        return f"not failed nodes in this execution: {', '.join(unknown)}"
    return None


def _redacted_paths(value: Any, prefix: tuple = ()) -> set[tuple]:  # noqa: ANN401
    """Key paths in a persisted value carrying the credential-scrubber marker.

    Stored ``output_data`` is scrubbed on write (see ``get_activity_output``),
    while the live run consumed raw values. Any marker means injection would
    feed downstream nodes redacted data instead of the originals. List indices
    are path segments so ``items[0]`` references resolve precisely.
    """
    found: set[tuple] = set()
    if isinstance(value, str):
        if REDACTED in value:
            found.add(prefix)
    elif isinstance(value, dict):
        for key, item in value.items():
            found |= _redacted_paths(item, (*prefix, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found |= _redacted_paths(item, (*prefix, index))
    return found


def _nearest_downstream_converges(
    successors: dict[str, set[str]],
    by_id: dict[str, dict[str, Any]],
    node_id: str,
) -> list[str]:
    """Converge-type nodes at the shortest downstream distance, or empty.

    Breadth-first so the result is the truly nearest tier: a farther completed
    converge must not shadow a nearer failed one (which still needs the
    branch). Depth-first first-found would be order-dependent and wrong here.
    """
    seen = {node_id}
    frontier = sorted(successors.get(node_id, ()))
    while frontier:
        tier = sorted({node for node in frontier if node not in seen})
        if not tier:
            return []
        converges = [
            node for node in tier if (entry := by_id.get(node)) is not None and entry.get("type") == "converge"
        ]
        if converges:
            return converges
        seen.update(tier)
        frontier = sorted({dst for node in tier for dst in successors.get(node, ())})
    return []


def _converge_reason(
    snapshot_def: dict[str, Any],
    normalized: list[str],
    completed_ids: set[str],
) -> str | None:
    """Rejection reason when failure points feed an already-completed converge.

    A completed converge met its threshold without these branches, so the
    workflow already moved past them — restarting them is moot. A FAILED
    converge (threshold unmet) keeps its branch failures as valid candidates.
    """
    nodes = definition_nodes(snapshot_def)
    by_id = {node["id"]: node for node in nodes if "id" in node}
    successors: dict[str, set[str]] = {node_id: set() for node_id in by_id}
    for edge in snapshot_def.get("edges", []) or []:
        src, dst = edge.get("from"), edge.get("to")
        if src is not None and dst is not None:
            successors.setdefault(src, set()).add(dst)
    mooted: list[str] = []
    for point in normalized:
        nearest = _nearest_downstream_converges(successors, by_id, point)
        if nearest and all(converge in completed_ids for converge in nearest):
            mooted.extend(f"{point} (converge {converge} already completed)" for converge in nearest)
    if mooted:
        return (
            "failure points feed an already-completed converge node "
            f"({', '.join(mooted)}); the workflow already moved past these branches"
        )
    return None


def _restart_path_refs(definition: dict[str, Any], restart_path: set[str]) -> dict[str, set[tuple]]:
    """Template references by target, from nodes that will actually re-execute."""
    referenced: dict[str, set[tuple]] = {}
    for node in definition_nodes(definition):
        node_id = node.get("id")
        if node_id is None or node_id not in restart_path:
            continue
        for target_id, field_path in find_template_refs(node.get("parameters", {})):
            if target_id != node_id:
                referenced.setdefault(target_id, set()).add(field_path)
    return referenced


def _tainted_nodes(
    snapshot_def: dict[str, Any],
    normalized: list[str],
    completed_outputs: dict[str, list],
) -> list[str]:
    """Sanitized node ids whose taint is referenced on the restart path.

    Collects template references from nodes that will actually re-execute,
    then intersects each completed node's redacted field paths against the
    referenced paths. Whole-namespace refs match any taint under that node.

    Completed nodes *in* the restart path re-run fresh, so their stored
    outputs are never injected — only nodes outside it (skipped upstream nodes
    and completed side branches) can feed tainted data into the rerun.
    """
    restart_path = collect_downstream_node_ids(snapshot_def, normalized)
    referenced = _restart_path_refs(snapshot_def, restart_path)

    sanitized: list[str] = []
    for node_id, outputs in completed_outputs.items():
        if node_id in restart_path:
            continue
        refs = referenced.get(node_id, set())
        if not refs:
            continue
        redacted: set[tuple] = set()
        for output in outputs:
            redacted |= _redacted_paths(output)
        if any(paths_overlap(tainted, ref) for tainted in redacted for ref in refs):
            sanitized.append(node_id)
    return sorted(sanitized)


def _expand_sanitized_chain(
    snapshot_def: dict[str, Any],
    seed: set[str],
    completed_outputs: dict[str, list],
) -> tuple[set[str], list[str]]:
    """Expand a starting selection to include every sanitized dependency, transitively.

    Repeats the taint check against the growing selection until a pass finds
    nothing new outside it — so a sanitized node that itself depends on a
    further sanitized ancestor is followed to the end of the chain, not just
    one level. Returns the expanded selection and the sorted nodes added.
    """
    selection = set(seed)
    added: set[str] = set()
    while True:
        sanitized = _tainted_nodes(snapshot_def, sorted(selection), completed_outputs)
        newly_added = set(sanitized) - selection
        if not newly_added:
            return selection, sorted(added)
        selection |= newly_added
        added |= newly_added


def _version_reason(
    normalized: list[str],
    snapshot: WorkflowVersion | None,
    completed_outputs: dict[str, list],
    *,
    is_default_selection: bool,
) -> tuple[str | None, list[str], list[str], list[str]]:
    """Rejection reason, blocking sanitized nodes, auto-included nodes, and the final selection.

    Either way, the full transitive chain of sanitized dependencies is
    resolved first. For an explicit selection, that chain rejects outright
    (``sanitized`` names every node in it, the selection is unchanged). For
    the default selection (SDP AC-15), the selection is instead expanded to
    include the whole chain as additional restart points, and what was
    auto-included is reported instead of rejecting.
    """
    if snapshot is None:
        return "original workflow version no longer exists", [], [], normalized
    snapshot_def = snapshot.workflow_definition or {}
    snapshot_ids = {node.get("id") for node in definition_nodes(snapshot_def)}
    missing = [point for point in normalized if point not in snapshot_ids]
    if missing:
        return f"not nodes in the executed workflow version: {', '.join(missing)}", [], [], normalized

    expanded, added = _expand_sanitized_chain(snapshot_def, set(normalized), completed_outputs)
    if not added:
        return None, [], [], sorted(expanded)
    if not is_default_selection:
        return (
            (
                "upstream nodes have sanitized outputs referenced on the restart path "
                f"({', '.join(added)}); restarting would inject redacted data"
            ),
            added,
            [],
            normalized,
        )
    return None, [], added, sorted(expanded)


def _sanitized_replacements(
    snapshot_def: dict[str, Any],
    failed_ids: set[str],
    completed_outputs: dict[str, list],
) -> dict[str, list[str]]:
    """For every currently-failed node, the sanitized node(s) it must be replaced by.

    Computed per failed node in isolation (not against the request's actual
    selection) so the response always reflects every failed node's own
    restart-path dependency — independent of what this particular request
    asked for. Lets the UI disallow selecting a failed node explicitly
    before the user submits a request that would just be rejected.
    """
    replacements: dict[str, list[str]] = {}
    for node_id in sorted(failed_ids):
        _, added = _expand_sanitized_chain(snapshot_def, {node_id}, completed_outputs)
        if added:
            replacements[node_id] = added
    return replacements


async def validate_restart_from_failure(
    session: AsyncSession,
    execution_id: UUID,
    failure_point_ids: list[str],
) -> RestartValidation:
    """Validate that an execution can be restarted from the given failure points.

    Pure read path: loads the source execution, its failed/completed
    activities, and the retained workflow version, then runs the guard chain
    (state, selection, converge-mootness, retained-version, sanitized-taint).
    Never mutates state.

    An empty ``failure_point_ids`` means the default selection — all
    currently failed nodes (SDP R11/AC-15) — not an error.

    Raises:
        ExecutionNotFoundError: If the source execution is gone.

    """
    result = await session.exec(select(Execution).where(Execution.id == execution_id))
    source = result.one_or_none()
    if source is None:
        raise ExecutionNotFoundError(execution_id)

    suffixed = sorted({point.strip() for point in failure_point_ids if point and LOOP_ITERATION_SEP in point.strip()})
    if suffixed:
        return RestartValidation(
            eligible=False,
            reason=(
                "loop-iteration failure points are not selectable "
                f"({', '.join(suffixed)}); select base node ids instead"
            ),
            failure_point_ids=sorted({point.strip() for point in failure_point_ids if point and point.strip()}),
        )
    normalized_input = sorted({point.strip() for point in failure_point_ids if point and point.strip()})
    is_default_selection = not normalized_input

    activities = (
        await session.exec(
            select(ActivityExecution).where(
                ActivityExecution.execution_id == execution_id,
                ActivityExecution.status == ActivityStatus.FAILED,
            )
        )
    ).all()
    failed_ids = {strip_iteration_suffix(activity.activity_name) for activity in activities}
    normalized = sorted(failed_ids) if is_default_selection else normalized_input

    completed = (
        await session.exec(
            select(ActivityExecution).where(
                ActivityExecution.execution_id == execution_id,
                ActivityExecution.status == ActivityStatus.COMPLETED,
            )
        )
    ).all()
    # Per-iteration outputs keyed by base node id: any tainted iteration taints
    # the node (iteration-level classification is AAP-92821's job; validation
    # stays fail-closed at base-id granularity rather than last-write-wins).
    completed_outputs: dict[str, list] = {}
    for activity in completed:
        completed_outputs.setdefault(strip_iteration_suffix(activity.activity_name), []).append(activity.output_data)
    completed_ids = set(completed_outputs)

    snapshot_result = await session.exec(
        select(WorkflowVersion).where(WorkflowVersion.id == source.workflow_version_id)
    )
    snapshot = snapshot_result.one_or_none()

    version_reason, sanitized, auto_included, final_selection = _version_reason(
        normalized, snapshot, completed_outputs, is_default_selection=is_default_selection
    )
    snapshot_def = (snapshot.workflow_definition or {}) if snapshot is not None else {}
    reason = (
        _state_reason(source)
        or _selection_reason(normalized, failed_ids)
        or _converge_reason(snapshot_def, normalized, completed_ids)
        or version_reason
    )

    snapshot_version = snapshot.version if snapshot is not None else None
    reported_selection = final_selection if reason is None else normalized
    upstream = collect_upstream_node_ids(snapshot_def, reported_selection)
    step_counts, total_steps = _step_counts(snapshot_def, reported_selection) if snapshot is not None else ({}, 0)
    replacements = _sanitized_replacements(snapshot_def, failed_ids, completed_outputs) if snapshot is not None else {}

    if reason is not None:
        return RestartValidation(
            eligible=False,
            reason=reason,
            failure_point_ids=reported_selection,
            upstream_node_ids=sorted(upstream),
            sanitized_node_ids=sanitized,
            sanitized_replacements=replacements,
            snapshot_version=snapshot_version,
            step_count_by_failure_point=step_counts,
            total_step_count=total_steps,
        )

    return RestartValidation(
        eligible=True,
        failure_point_ids=reported_selection,
        upstream_node_ids=sorted(upstream),
        auto_included_node_ids=auto_included,
        sanitized_replacements=replacements,
        snapshot_version=snapshot_version,
        step_count_by_failure_point=step_counts,
        total_step_count=total_steps,
    )
