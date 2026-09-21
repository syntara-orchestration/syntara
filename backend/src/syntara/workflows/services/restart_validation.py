"""Pre-restart validation for restart-from-failure (AAP-92820).

Shared by ``POST /executions/{id}/validate-restart-from-failure`` (pure verdict,
no state mutation) and ``POST /executions/{id}/restart-from-failure`` (re-validates independently
before doing any work, so the restart endpoint is safe to call directly).

Validation is a chain of checks:

1. **State guard** — source execution must be ``FAILED`` or
   ``COMPLETED_WITH_ERRORS``.
2. **Failure-point eligibility** — every selected id must match a ``failed``
   ``ActivityExecution`` of the source execution *and* a node in the snapshot
   definition that ran.
3. **Version-mismatch guard** — walk the graph from each failure point back to
   the start over the *snapshot* definition, then diff exactly those upstream
   nodes against the *current* definition. Upstream changes reject;
   downstream-only changes pass. Nodes newly inserted on the upstream path in
   the current definition also reject (walked the same way over the current
   definition).
4. **Converge-mootness guard** — failure points feeding an already-completed
   converge node are rejected (the workflow moved past those branches); a
   failed converge keeps its branch failures as candidates.
5. **Tainted-output guard** — persisted ``output_data`` is credential-scrubbed
   on write while the live run consumed raw values, and script outputs may be
   stream/payload-truncated. Tainted *field paths* (redacted markers,
   truncation sentinels, or engine-written ``__truncated_fields`` provenance)
   reject, but only when actually referenced from the restart execution path
   (selected failure points plus their downstream) — unreferenced taint is
   harmless. A whole-namespace ``${node}`` reference taints on any marker;
   payload-truncation markers additionally taint ``stdout``, which is silently
   trimmed before the notice is appended. Loop iterations are evaluated
   per-iteration (any tainted iteration taints the node); iteration-suffixed
   selections are rejected with guidance to select base node ids.

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

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlmodel import select

from syntara.workflows.exceptions import ExecutionNotFoundError
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.utils.template_refs import find_template_refs, paths_overlap
from syntara.workflows.workflow_engine.constants import TRUNCATED_FIELDS_KEY
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

#: Node fields ignored by the version-mismatch diff (purely cosmetic).
COSMETIC_NODE_FIELDS = frozenset({"position", "label"})

#: Sentinels appended by script-output truncation (see script_activity.py).
#: Stream truncation caps stdout/stderr independently and always reports into
#: stderr; payload truncation silently trims stdout first, so its marker taints
#: both fields.
STREAM_TRUNCATED_MARKER = "[Output truncated:"
PAYLOAD_TRUNCATED_MARKER = "[Payload truncated:"
_STREAM_DETAIL_PATTERN = re.compile(r"\(stdout: (\w+), stderr: (\w+)\)")


@dataclass(frozen=True)
class RestartValidation:
    """Outcome of pre-restart validation (pure verdict, no side effects)."""

    eligible: bool
    reason: str | None = None
    failure_point_ids: list[str] = field(default_factory=list)
    upstream_node_ids: list[str] = field(default_factory=list)
    changed_node_ids: list[str] = field(default_factory=list)
    sanitized_node_ids: list[str] = field(default_factory=list)
    truncated_node_ids: list[str] = field(default_factory=list)
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


def _normalized_edge(edge: dict[str, Any]) -> tuple | None:
    """Edge as a comparable tuple, normalizing absent ports to None."""
    src, dst = edge.get("from"), edge.get("to")
    if src is None or dst is None:
        return None
    return (src, dst, edge.get("from_port"), edge.get("to_port"))


def collect_upstream_edges(
    definition: dict[str, Any],
    failure_point_ids: list[str],
) -> set[tuple]:
    """Upstream edges (normalized) traversed walking back from failure points."""
    edges = definition.get("edges", []) or []
    predecessors: dict[str, set[str]] = {}
    edge_by_pair: dict[tuple[str, str], list[tuple]] = {}
    for edge in edges:
        normalized = _normalized_edge(edge)
        if normalized is None:
            continue
        src, dst = normalized[0], normalized[1]
        predecessors.setdefault(dst, set()).add(src)
        edge_by_pair.setdefault((src, dst), []).append(normalized)

    seen: set[str] = set()
    collected: set[tuple] = set()
    stack = list(failure_point_ids)
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        for src in predecessors.get(node_id, ()):
            collected.update(edge_by_pair.get((src, node_id), []))
            stack.append(src)
    return collected


def collect_downstream_node_ids(
    definition: dict[str, Any],
    failure_point_ids: list[str],
) -> set[str]:
    """Return failure points plus every successor downstream (inclusive).

    The restart re-executes exactly this set (for the selected points), so
    only references originating here can consume injected outputs.
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


def canonical_node(node: dict[str, Any]) -> dict[str, Any]:
    """Structural projection of a definition node for the mismatch diff."""
    return {key: value for key, value in node.items() if key not in COSMETIC_NODE_FIELDS}


def diff_upstream_nodes(
    snapshot_definition: dict[str, Any],
    current_definition: dict[str, Any],
    upstream_node_ids: set[str],
) -> list[str]:
    """Return upstream node ids whose structural definition changed.

    A node counts as changed if it was removed from the current definition or
    its canonical form differs. Newly inserted nodes are handled by the caller,
    which walks the current definition the same way. Sorted for deterministic
    reasons/messages.
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


def _truncation_taints(output: Any) -> set[tuple]:  # noqa: ANN401
    """Field paths of a stored output tainted by stream/payload truncation.

    Prefers the ``__truncated_fields`` provenance key written at truncation
    time (survives output mapping, unlike the stderr notice). Falls back to
    sentinel parsing for rows recorded before provenance existed: both
    truncation paths report into ``stderr``; a payload marker additionally
    taints ``stdout``, which is silently trimmed before the notice is appended.
    A stream marker names the cut stream(s) in ``(stdout: …, stderr: …)``
    detail; unparseable detail taints both (fail-closed).
    """
    tainted: set[tuple] = set()
    if isinstance(output, dict):
        provenance = output.get(TRUNCATED_FIELDS_KEY)
        if isinstance(provenance, list):
            tainted = {(field,) for field in provenance if isinstance(field, str)}
        else:
            tainted = _sentinel_taints(output.get("stderr"))
    return tainted


def _sentinel_taints(stderr: Any) -> set[tuple]:  # noqa: ANN401
    """Field paths tainted per legacy stderr truncation sentinels."""
    if not isinstance(stderr, str):
        return set()
    if PAYLOAD_TRUNCATED_MARKER in stderr:
        return {("stderr",), ("stdout",)}
    if STREAM_TRUNCATED_MARKER in stderr:
        match = _STREAM_DETAIL_PATTERN.search(stderr)
        if match is None:
            return {("stderr",), ("stdout",), ("stdout_json",)}
        tainted = set()
        if match.group(1) == "truncated":
            # stdout_json is parsed from stdout text — cut stdout taints it too.
            tainted.update([("stdout",), ("stdout_json",)])
        if match.group(2) == "truncated":
            tainted.add(("stderr",))
        return tainted or {("stderr",), ("stdout",), ("stdout_json",)}
    return set()


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


def _mapped_legacy_taint(output: Any, *, is_script: bool) -> set[tuple]:  # noqa: ANN401
    """Taint for mapped-only legacy outputs whose stderr was dropped.

    Reserved for rows that predate provenance. When ``__truncated_fields`` is
    present the writer already recorded authoritative (possibly empty) taint, so
    this heuristic must not override it — otherwise a proven-clean output whose
    mapping dropped ``stderr`` would be falsely flagged. Only when the key is
    absent does a dropped ``stderr`` leave a missing sentinel unprovable, so a
    script node's present fields are treated as unknown. Non-script nodes have
    no truncation mechanism.
    """
    if (
        is_script
        and isinstance(output, dict)
        and output
        and TRUNCATED_FIELDS_KEY not in output
        and "stderr" not in output
    ):
        return {(key,) for key in output if isinstance(key, str)}
    return set()


def _restart_path_refs(current_def: dict[str, Any], restart_path: set[str]) -> dict[str, set[tuple]]:
    """Template references by target, from nodes that will actually re-execute."""
    referenced: dict[str, set[tuple]] = {}
    for node in definition_nodes(current_def):
        node_id = node.get("id")
        if node_id is None or node_id not in restart_path:
            continue
        for target_id, field_path in find_template_refs(node.get("parameters", {})):
            if target_id != node_id:
                referenced.setdefault(target_id, set()).add(field_path)
    return referenced


def _tainted_nodes(
    snapshot_def: dict[str, Any],
    current_def: dict[str, Any],
    normalized: list[str],
    completed_outputs: dict[str, list],
) -> tuple[list[str], list[str]]:
    """Sanitized and truncated node ids whose taint is referenced on the restart path.

    Collects template references from nodes that will actually re-execute, then
    intersects each completed node's tainted field paths (redacted markers,
    truncation sentinels/provenance) against the referenced paths.
    Whole-namespace refs match any taint under that node.

    Completed nodes *in* the restart path re-run fresh, so their stored outputs
    are never injected — only nodes outside it (skipped upstream nodes and
    completed side branches) can feed tainted data into the rerun.
    """
    restart_path = collect_downstream_node_ids(current_def, normalized)
    referenced = _restart_path_refs(current_def, restart_path)
    by_id = {node.get("id"): node for node in definition_nodes(snapshot_def) if node.get("id") is not None}

    def _taint(node_id: str) -> tuple[set[tuple], set[tuple]]:
        redacted: set[tuple] = set()
        truncated: set[tuple] = set()
        is_script = by_id.get(node_id, {}).get("type") == "script"
        for output in completed_outputs.get(node_id, []):
            for path in _redacted_paths(output):
                redacted.add(path)
            truncated |= _truncation_taints(output)
            truncated |= _mapped_legacy_taint(output, is_script=is_script)
        return redacted, truncated

    sanitized: list[str] = []
    truncated: list[str] = []
    for node_id in completed_outputs:
        if node_id in restart_path:
            continue
        refs = referenced.get(node_id, set())
        if not refs:
            continue
        redacted, truncation = _taint(node_id)
        if any(paths_overlap(tainted, ref) for tainted in redacted for ref in refs):
            sanitized.append(node_id)
        if any(paths_overlap(tainted, ref) for tainted in truncation for ref in refs):
            truncated.append(node_id)
    return sorted(sanitized), sorted(truncated)


def _version_reason(
    normalized: list[str],
    snapshot: WorkflowVersion | None,
    current: WorkflowVersion | None,
    completed_outputs: dict[str, list],
) -> tuple[str | None, list[str], list[str], list[str]]:
    """Rejection reason, changed, sanitized, and truncated nodes for the guards."""
    if snapshot is None:
        return "original workflow version no longer exists", [], [], []
    if current is None:
        return "current workflow version no longer exists", [], [], []
    snapshot_def = snapshot.workflow_definition or {}
    current_def = current.workflow_definition or {}
    snapshot_ids = {node.get("id") for node in definition_nodes(snapshot_def)}
    missing = [point for point in normalized if point not in snapshot_ids]
    if missing:
        return f"not nodes in the executed workflow version: {', '.join(missing)}", [], [], []
    snapshot_upstream = collect_upstream_node_ids(snapshot_def, normalized)
    current_upstream = collect_upstream_node_ids(current_def, normalized)
    inserted = sorted(current_upstream - snapshot_upstream)
    snapshot_edges = collect_upstream_edges(snapshot_def, normalized)
    current_edges = collect_upstream_edges(current_def, normalized)
    snapshot_by_id = {node["id"]: node for node in definition_nodes(snapshot_def) if "id" in node}
    current_by_id = {node["id"]: node for node in definition_nodes(current_def) if "id" in node}

    def _endpoint_unchanged(node_id: str) -> bool:
        return (
            node_id in snapshot_by_id
            and node_id in current_by_id
            and canonical_node(snapshot_by_id[node_id]) == canonical_node(current_by_id[node_id])
        )

    # Pure rewiring: same nodes, different upstream edges (e.g. a sidecar
    # bypassed but still defined). Reported only when no insertion explains the
    # edge difference — otherwise the incident (but unchanged) endpoints would
    # drown out the inserted node in the listing.
    rewired: list[str] = []
    if not inserted:
        rewired = sorted(
            {
                node_id
                for edge in snapshot_edges.symmetric_difference(current_edges)
                for node_id in edge[:2]
                if _endpoint_unchanged(node_id)
            }
        )
    changed = sorted(
        set(diff_upstream_nodes(snapshot_def, current_def, snapshot_upstream)) | set(inserted) | set(rewired)
    )
    sanitized, truncated = _tainted_nodes(snapshot_def, current_def, normalized, completed_outputs)
    parts = []
    if changed:
        parts.append(
            "workflow definition changed upstream of the failure point "
            f"({', '.join(changed)}); restart is rejected to avoid corrupt state"
        )
    if sanitized:
        parts.append(
            "upstream nodes have sanitized outputs referenced on the restart path "
            f"({', '.join(sanitized)}); restarting would inject redacted data"
        )
    if truncated:
        parts.append(
            "upstream nodes have truncated outputs referenced on the restart path "
            f"({', '.join(truncated)}); restarting would inject incomplete data"
        )
    if parts:
        return "; ".join(parts), changed, sanitized, truncated
    return None, [], [], []


async def validate_restart_from_failure(
    session: AsyncSession,
    execution_id: UUID,
    failure_point_ids: list[str],
) -> RestartValidation:
    """Validate that an execution can be restarted from the given failure points.

    Pure read path: loads the source execution, its failed/completed activities,
    and the snapshot/current definitions, then runs the guard chain (state,
    selection, converge-mootness, version/structural, taint). Never mutates
    state.

    Raises:
        ExecutionNotFoundError: If the source execution (or its workflow) is gone.

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

    version_reason, changed, sanitized, truncated = _version_reason(normalized, snapshot, current, completed_outputs)
    snapshot_def_for_converge = (snapshot.workflow_definition or {}) if snapshot is not None else {}
    reason = (
        _state_reason(source)
        or _selection_reason(normalized, failed_ids)
        or _converge_reason(snapshot_def_for_converge, normalized, completed_ids)
        or version_reason
    )

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
            sanitized_node_ids=sanitized,
            truncated_node_ids=truncated,
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
