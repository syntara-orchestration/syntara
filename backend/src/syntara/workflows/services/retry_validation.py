"""Pre-retry validation for retry-from-failure (AAP-92820).

  Shared by ``GET /executions/{id}/retry-from-failure-preview`` (pure verdict,
  no state mutation, reports the default selection) and
  ``POST /executions/{id}/retry-from-failure`` (re-validates the caller's
  selection independently before doing any work, so the retry endpoint is safe
  to call directly).

Validation is a chain of checks:

1. **State guard** — source execution must be ``FAILED`` or
   ``COMPLETED_WITH_ERRORS``.
2. **Failure-point eligibility** — every selected id must match a ``failed``
   ``ActivityExecution`` of the source execution *and* a node in the retained
   workflow version that ran.
3. **Converge-mootness guard** — failure points feeding an already-completed
   converge node are rejected (the workflow moved past those branches); a
   failed converge keeps its branch failures as candidates.
4. **Retained-version guard** — retry always runs against the exact
   workflow version captured when the original run started
   (``source.workflow_version_id``). There is no comparison against the
   currently saved definition and no diffing — later edits never affect a
   retry (SDP ANSTRAT-1779 R9/R10). Rejected only if that version no longer
   exists, or a selected id is not a node in it.
5. **Sanitized-output guard** — persisted ``output_data`` is credential-scrubbed
   on write while the live run consumed raw values. Redacted *field paths*
   reject, but only when actually referenced from the retry execution path
   (selected failure points plus their downstream) — unreferenced markers are
   harmless. A whole-namespace ``${node}`` reference taints on any marker
   under that node. Loop iterations are evaluated per-iteration (any tainted
   iteration taints the node); iteration-suffixed selections are rejected
   with guidance to select base node ids. Truncated output is out of scope
   for retry validation — it affects all executions equally and is not
   retry-specific (SDP scope reduction, R9a).
6. **Input-override guard** — supplied input parameter overrides (SDP AC-14/R10c)
   may only name parameters that already exist on the target node in the
   retained version, and may only target nodes that are both currently failed
   and inside the re-run closure. A sanitized node is never a target even when
   it is an auto-included starting point: it was pulled in to regenerate raw
   output, not chosen by the caller. A failed node that the caller excluded from
   this retry is rejected too, since the override would be silently discarded.
   Overrides are validated here but never applied: the engine applies them at
   dispatch (AAP-92821). An override replaces the value the node would
   otherwise receive, after upstream outputs are injected.

    For an **explicit** selection, a sanitized dependency always rejects. For
    the **default** selection (empty input — see below), a sanitized
    dependency instead expands the retry points to include the sanitized
    node, repeated until no dependency remains, and reports what was added
    instead of rejecting (SDP AC-15/R9a). Either way, the response also
    reports ``sanitized_replacements`` — for *every* currently-failed node
    (not just the ones requested), which sanitized node(s) it would need to
    be replaced by — so the UI can disallow selecting a failed node
    explicitly before the user even submits a request (per Bill Wei,
    2026-09-24: "so that the UI can disallow replaced nodes being selected").

    The reported retry set is the **eligible** set: the expanded selection
    minus failed points superseded by auto-inclusion (a failed point strictly
    downstream of an auto-included sanitized node still re-executes, but the
    retry initiates at the sanitized head). Step counts are keyed by
    eligible point.


Design decisions (SDP ANSTRAT-1779, aligned 2026-09-24):

- Loop-iteration activities (``<node>#iter-<n>``) normalize to their base node
  id for eligibility; iteration-level classification is AAP-92821's job.
- An empty failure-point selection means "all currently failed nodes"
  (SDP R11/AC-15) — not an error. A non-empty selection means exactly those
  nodes. Rejected only if there are no failed nodes at all to default to.
- The response includes a re-run step count per eligible retry point and a
  deduplicated total across the whole selection (SDP R11a/AC-2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlmodel import select

from syntara.workflows.exceptions import ExecutionNotFoundError
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.utils.template_refs import FieldPath, find_template_refs, paths_overlap
from syntara.workflows.workflow_engine.utils.credential_scrubber import REDACTED

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

#: Statuses a retry may start from. Mirrors the story scope; anything else is
#: rejected with a reason (never silently).
RETRYABLE_FROM_FAILURE_STATUSES = frozenset({ExecutionStatus.FAILED, ExecutionStatus.COMPLETED_WITH_ERRORS})

#: Separator for loop-iteration activity names (``<node>#iter-<n>``). Must match
#: ``_COMPOSITE_ITER_SEP`` in activity_sync_service.py.
LOOP_ITERATION_SEP = "#iter-"


@dataclass(frozen=True)
class RetryValidation:
    """Outcome of pre-retry validation (pure verdict, no side effects)."""

    eligible: bool
    reason: str | None = None
    eligible_point_ids: list[str] = field(default_factory=list)
    sanitized_node_ids: list[str] = field(default_factory=list)
    auto_included_node_ids: list[str] = field(default_factory=list)
    sanitized_replacements: dict[str, list[str]] = field(default_factory=dict)
    step_count_by_eligible_point: dict[str, int] = field(default_factory=dict)
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


def build_successors(definition: dict[str, Any]) -> dict[str, set[str]]:
    """Successor adjacency (node id → downstream ids).

    Every downstream walk in this module takes the map as an optional argument
    so a single validation builds it once and shares it, instead of each
    traversal re-walking the edge list. Callers that omit it pay for their own
    build, which keeps the pure helpers usable standalone in tests.
    """
    nodes = definition_nodes(definition)
    edges = definition.get("edges", []) or []
    successors: dict[str, set[str]] = {node["id"]: set() for node in nodes if "id" in node}
    for edge in edges:
        src, dst = edge.get("from"), edge.get("to")
        if src is not None and dst is not None:
            successors.setdefault(src, set()).add(dst)
    return successors


def collect_downstream_node_ids(
    definition: dict[str, Any],
    retry_point_ids: list[str],
    successors: dict[str, set[str]] | None = None,
) -> set[str]:
    """Return failure points plus every successor downstream (inclusive).

    The retry re-executes exactly this set (for the selected points), so
    only references originating here can consume injected outputs, and its
    size is the re-run step count (SDP R11a/AC-2).
    """
    if successors is None:
        successors = build_successors(definition)

    downstream: set[str] = set()
    stack = list(retry_point_ids)
    while stack:
        node_id = stack.pop()
        if node_id in downstream:
            continue
        downstream.add(node_id)
        stack.extend(successors.get(node_id, ()))
    return downstream


def _step_counts(
    definition: dict[str, Any],
    retry_point_ids: list[str],
    successors: dict[str, set[str]] | None = None,
) -> tuple[dict[str, int], int]:
    """Re-run step count per eligible retry point, plus the deduplicated total.

    Per-point counts are computed independently (a node reachable from two
    selected points is not double-counted within its own point's count); the
    total is the size of the union across the whole selection, matching a
    branch converging back into another selected branch's path.
    """
    if successors is None:
        successors = build_successors(definition)
    per_point = {point: len(collect_downstream_node_ids(definition, [point], successors)) for point in retry_point_ids}
    total = len(collect_downstream_node_ids(definition, retry_point_ids, successors))
    return per_point, total


def _state_reason(source: Execution) -> str | None:
    """Rejection reason when the source state cannot retry, else None."""
    if source.status not in RETRYABLE_FROM_FAILURE_STATUSES:
        return (
            f"execution is in {source.status.value} state; "
            "retry is available for failed and completed_with_errors executions only"
        )
    return None


def _selection_reason(normalized: list[str], failed_ids: set[str]) -> str | None:
    """Rejection reason for an empty or ineligible selection, else None.

    ``normalized`` has already been resolved to the default (all currently
    failed nodes) if the caller's selection was empty, so an empty result
    here only happens when there are no failed nodes at all to default to.
    """
    if not normalized:
        return "no failed nodes in this execution to retry from"
    unknown = [point for point in normalized if point not in failed_ids]
    if unknown:
        return f"not failed nodes in this execution: {', '.join(unknown)}"
    return None


def _redacted_paths(value: Any, prefix: FieldPath = ()) -> set[FieldPath]:  # noqa: ANN401
    """Key paths in a persisted value carrying the credential-scrubber marker.

    Stored ``output_data`` is scrubbed on write (see ``get_activity_output``),
    while the live run consumed raw values. Any marker means injection would
    feed downstream nodes redacted data instead of the originals. List indices
    are path segments so ``items[0]`` references resolve precisely.
    """
    found: set[FieldPath] = set()
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
    successors: dict[str, set[str]] | None = None,
) -> str | None:
    """Rejection reason when failure points feed an already-completed converge.

    A completed converge met its threshold without these branches, so the
    workflow already moved past them — restarting them is moot. A FAILED
    converge (threshold unmet) keeps its branch failures as valid candidates.
    """
    nodes = definition_nodes(snapshot_def)
    by_id = {node["id"]: node for node in nodes if "id" in node}
    if successors is None:
        successors = build_successors(snapshot_def)
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


def _retry_path_refs(definition: dict[str, Any], retry_path: set[str]) -> dict[str, set[FieldPath]]:
    """Template references by target, from nodes that will actually re-execute."""
    referenced: dict[str, set[FieldPath]] = {}
    for node in definition_nodes(definition):
        node_id = node.get("id")
        if node_id is None or node_id not in retry_path:
            continue
        for target_id, field_path in find_template_refs(node.get("parameters", {})):
            if target_id != node_id:
                referenced.setdefault(target_id, set()).add(field_path)
    return referenced


def _tainted_nodes(
    snapshot_def: dict[str, Any],
    normalized: list[str],
    completed_outputs: dict[str, list[Any]],
    successors: dict[str, set[str]] | None = None,
) -> list[str]:
    """Sanitized node ids whose taint is referenced on the retry path.

    Collects template references from nodes that will actually re-execute,
    then intersects each completed node's redacted field paths against the
    referenced paths. Whole-namespace refs match any taint under that node.

    Completed nodes *in* the retry path re-run fresh, so their stored
    outputs are never injected — only nodes outside it (skipped upstream nodes
    and completed side branches) can feed tainted data into the rerun.
    """
    retry_path = collect_downstream_node_ids(snapshot_def, normalized, successors)
    referenced = _retry_path_refs(snapshot_def, retry_path)

    sanitized: list[str] = []
    for node_id, outputs in completed_outputs.items():
        if node_id in retry_path:
            continue
        refs = referenced.get(node_id, set())
        if not refs:
            continue
        redacted: set[FieldPath] = set()
        for output in outputs:
            if output is None:
                continue
            redacted |= _redacted_paths(output)
        if any(paths_overlap(tainted, ref) for tainted in redacted for ref in refs):
            sanitized.append(node_id)
    return sorted(sanitized)


def _expand_sanitized_chain(
    snapshot_def: dict[str, Any],
    seed: set[str],
    completed_outputs: dict[str, list[Any]],
    successors: dict[str, set[str]] | None = None,
) -> tuple[set[str], list[str]]:
    """Expand a starting selection to include every sanitized dependency, transitively.

    Repeats the taint check against the growing selection until a pass finds
    nothing new outside it — so a sanitized node that itself depends on a
    further sanitized ancestor is followed to the end of the chain, not just
    one level. Returns the expanded selection and the sorted nodes added.

    Callers that expand many seeds (see ``_sanitized_replacements``) pass a
    shared ``successors`` map so the cost is one build, not one per seed.
    """
    selection = set(seed)
    added: set[str] = set()
    if successors is None:
        successors = build_successors(snapshot_def)
    while True:
        sanitized = _tainted_nodes(snapshot_def, sorted(selection), completed_outputs, successors)
        newly_added = set(sanitized) - selection
        if not newly_added:
            return selection, sorted(added)
        selection |= newly_added
        added |= newly_added


def _eligible_points(
    snapshot_def: dict[str, Any],
    expanded: set[str],
    auto_included: set[str],
    successors: dict[str, set[str]] | None = None,
) -> set[str]:
    """Retry initiation points: the expanded selection minus superseded failed points.

    A failed point strictly downstream of an auto-included sanitized node still
    re-executes (as downstream of the sanitized head), but the retry no
    longer *starts* there — the sanitized head supersedes it. Auto-included
    sanitized nodes themselves always stay eligible: each must re-execute
    fresh to regenerate raw outputs (its stored output can never be injected).
    With no auto-inclusion, the eligible set is the requested selection
    unchanged.
    """
    if not auto_included:
        return set(expanded)
    if successors is None:
        successors = build_successors(snapshot_def)
    seen = set(auto_included)
    stack = list(auto_included)
    while stack:
        node_id = stack.pop()
        for nxt in successors.get(node_id, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return set(expanded) - (seen - set(auto_included))


def _version_reason(
    normalized: list[str],
    snapshot: WorkflowVersion | None,
    completed_outputs: dict[str, list[Any]],
    successors: dict[str, set[str]] | None = None,
    *,
    is_default_selection: bool,
) -> tuple[str | None, list[str], list[str], list[str]]:
    """Rejection reason, blocking sanitized nodes, auto-included nodes, and the final selection.

    Either way, the full transitive chain of sanitized dependencies is
    resolved first. For an explicit selection, that chain rejects outright
    (``sanitized`` names every node in it, the selection is unchanged). For
    the default selection (SDP AC-15), the selection is instead expanded to
    include the whole chain as additional retry points, and what was
    auto-included is reported instead of rejecting.
    """
    if snapshot is None:
        return "original workflow version no longer exists", [], [], normalized
    snapshot_def = snapshot.workflow_definition or {}
    snapshot_ids = {node.get("id") for node in definition_nodes(snapshot_def)}
    missing = [point for point in normalized if point not in snapshot_ids]
    if missing:
        return f"not nodes in the executed workflow version: {', '.join(missing)}", [], [], normalized

    expanded, added = _expand_sanitized_chain(snapshot_def, set(normalized), completed_outputs, successors)
    if not added:
        return None, [], [], sorted(expanded)
    if not is_default_selection:
        return (
            (
                "upstream nodes have sanitized outputs referenced on the retry path "
                f"({', '.join(added)}); retrying would inject redacted data"
            ),
            added,
            [],
            normalized,
        )
    return None, [], added, sorted(expanded)


def _override_reason(
    snapshot_def: dict[str, Any] | None,
    reported_selection: list[str],
    failed_ids: set[str],
    sanitized: set[str],
    overrides: dict[str, dict[str, Any]],
    successors: dict[str, set[str]] | None = None,
) -> str | None:
    """Rejection reason for input-parameter overrides that cannot apply, else None.

    An override may only target a node that is both currently failed and going
    to re-execute. Sanitized nodes are excluded even when they are starting
    points: they are pulled in automatically to regenerate raw output, so the
    caller never chose them and editing their inputs is rejected.

    Requiring the node to re-execute as well as to be failed keeps an override
    from being accepted on a failed branch the caller deselected, where it
    would be silently discarded.

    AC-14 separately constrains the keys: they must already exist on the target
    node in the *retained* version, so an override may change a value but never
    add a parameter or alter the definition for one run.

    An empty override map is always valid — most retries change nothing.
    """
    if not overrides:
        return None

    if snapshot_def is None:
        return "cannot apply input parameter overrides: original workflow version no longer exists"

    by_id = {node["id"]: node for node in definition_nodes(snapshot_def) if "id" in node}
    if successors is None:
        successors = build_successors(snapshot_def)
    will_re_execute = collect_downstream_node_ids(snapshot_def, reported_selection, successors)
    allowed_nodes = {node_id for node_id in failed_ids if node_id in will_re_execute and node_id not in sanitized}

    disallowed = sorted(node_id for node_id in overrides if node_id not in allowed_nodes)
    if disallowed:
        return (
            f"input parameter overrides may only target failed nodes that will re-execute: {', '.join(disallowed)}; "
            f"eligible targets are {', '.join(sorted(allowed_nodes)) if allowed_nodes else 'none'}. "
            "Nodes pulled in automatically to regenerate sanitized output are not editable."
        )

    for node_id in sorted(overrides):
        supplied = overrides[node_id]
        if not supplied:
            # No-op override: nothing to check, and it must not fail the retry.
            continue
        parameters = by_id.get(node_id, {}).get("parameters")
        existing = set(parameters) if isinstance(parameters, dict) else set()
        if not existing:
            return (
                f"node {node_id} has no input parameters in the executed workflow version; "
                "overrides cannot add new ones"
            )
        unknown_params = sorted(key for key in supplied if key not in existing)
        if unknown_params:
            return (
                f"input parameter overrides name keys that do not exist on node {node_id}: "
                f"{', '.join(unknown_params)}; "
                f"existing parameters are {', '.join(sorted(existing))}"
            )
    return None


def _sanitized_replacements(
    snapshot_def: dict[str, Any],
    failed_ids: set[str],
    completed_outputs: dict[str, list[Any]],
    successors: dict[str, set[str]] | None = None,
) -> dict[str, list[str]]:
    """For every currently-failed node, the sanitized node(s) it must be replaced by.

    Computed per failed node in isolation (not against the request's actual
    selection) so the response always reflects every failed node's own
    retry-path dependency — independent of what this particular request
    asked for. Lets the UI disallow selecting a failed node explicitly
    before the user submits a request that would just be rejected.

    One shared ``successors`` map is threaded through the per-node loop, so
    this costs a single adjacency build regardless of how many nodes failed.
    """
    replacements: dict[str, list[str]] = {}
    if successors is None:
        successors = build_successors(snapshot_def)
    for node_id in sorted(failed_ids):
        _, added = _expand_sanitized_chain(snapshot_def, {node_id}, completed_outputs, successors)
        if added:
            replacements[node_id] = added
    return replacements


async def validate_retry_from_failure(
    session: AsyncSession,
    execution_id: UUID,
    retry_point_ids: list[str],
    input_parameter_overrides: dict[str, dict[str, Any]] | None = None,
) -> RetryValidation:
    """Validate that an execution can be retried from the given failure points.

    Pure read path: loads the source execution, its failed/completed
    activities, and the retained workflow version, then runs the guard chain
    (state, selection, converge-mootness, retained-version, sanitized-taint,
    input-override). Never mutates state.

    An empty ``retry_point_ids`` means the default selection — all
    currently failed nodes (SDP R11/AC-15) — not an error.

    ``input_parameter_overrides`` is validated, never applied: this layer only
    decides whether the retry may proceed with them (SDP AC-14/R10c). The engine
    applies them at dispatch (AAP-92821).

    Raises:
        ExecutionNotFoundError: If the source execution is gone.

    """
    overrides = input_parameter_overrides or {}
    result = await session.exec(select(Execution).where(Execution.id == execution_id))
    source = result.one_or_none()
    if source is None:
        raise ExecutionNotFoundError(execution_id)

    suffixed = sorted({point.strip() for point in retry_point_ids if point and LOOP_ITERATION_SEP in point.strip()})
    if suffixed:
        return RetryValidation(
            eligible=False,
            reason=(
                "loop-iteration failure points are not selectable "
                f"({', '.join(suffixed)}); select base node ids instead"
            ),
            eligible_point_ids=sorted({point.strip() for point in retry_point_ids if point and point.strip()}),
        )
    normalized_input = sorted({point.strip() for point in retry_point_ids if point and point.strip()})
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
    completed_outputs: dict[str, list[Any]] = {}
    for activity in completed:
        completed_outputs.setdefault(strip_iteration_suffix(activity.activity_name), []).append(activity.output_data)
    completed_ids = set(completed_outputs)

    snapshot_result = await session.exec(
        select(WorkflowVersion).where(WorkflowVersion.id == source.workflow_version_id)
    )
    snapshot = snapshot_result.one_or_none()

    snapshot_def = (snapshot.workflow_definition or {}) if snapshot is not None else {}
    # One adjacency build for the whole validation, shared by every downstream
    # walk below (converge-mootness, sanitized expansion, step counts, eligible
    # points, and the per-failed-node replacement scan).
    successors = build_successors(snapshot_def) if snapshot is not None else {}

    version_reason, sanitized, auto_included, final_selection = _version_reason(
        normalized,
        snapshot,
        completed_outputs,
        successors,
        is_default_selection=is_default_selection,
    )
    reason = (
        _state_reason(source)
        or _selection_reason(normalized, failed_ids)
        or _converge_reason(snapshot_def, normalized, completed_ids, successors)
        or version_reason
    )

    if reason is None:
        reported_selection = sorted(
            _eligible_points(snapshot_def, set(final_selection), set(auto_included), successors)
        )
        # Only meaningful once the earlier guards have passed: overrides target
        # failed nodes that re-execute, not starting points.
        reason = _override_reason(
            snapshot.workflow_definition if snapshot is not None else None,
            reported_selection,
            failed_ids,
            set(sanitized),
            overrides,
            successors,
        )
    else:
        reported_selection = normalized
    step_counts, total_steps = (
        _step_counts(snapshot_def, reported_selection, successors) if snapshot is not None else ({}, 0)
    )
    replacements = (
        _sanitized_replacements(snapshot_def, failed_ids, completed_outputs, successors) if snapshot is not None else {}
    )

    if reason is not None:
        return RetryValidation(
            eligible=False,
            reason=reason,
            eligible_point_ids=reported_selection,
            sanitized_node_ids=sanitized,
            sanitized_replacements=replacements,
            step_count_by_eligible_point=step_counts,
            total_step_count=total_steps,
        )

    return RetryValidation(
        eligible=True,
        eligible_point_ids=reported_selection,
        auto_included_node_ids=auto_included,
        sanitized_replacements=replacements,
        step_count_by_eligible_point=step_counts,
        total_step_count=total_steps,
    )
