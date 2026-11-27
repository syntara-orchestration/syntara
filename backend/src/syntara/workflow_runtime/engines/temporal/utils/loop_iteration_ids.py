"""Canonical loop-iteration Temporal IDs.

A node outside any loop keeps its canvas ID. Inside one or more loops the
Temporal activity ID is the canvas ID plus one ``_iter_{n}`` suffix per
enclosing loop, outermost first.

Loop *control* activities always append their own ``current_index`` after any
enclosing-loop indices (see ``loop_control_activity_id``).

The Approvals API ``approval_node_id`` stays the canvas ID. Iteration identity
for approval rows is ``loop_iteration_path`` (the same index chain).

Examples::

    approval                    # no loop
    approval_iter_3             # single loop, Temporal id, index 3
    approval_iter_1_iter_0      # outer index 1, inner index 0
    outer_iter_0                # top-level loop control, index 0
    inner_iter_1_iter_0         # nested loop control, outer 1, inner 0

``workflow.patched`` keeps in-flight executions on pre-upgrade Temporal IDs
(canvas ID for loop-body approvals; own index only for nested loop control).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from temporalio import workflow

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

LOOP_ITERATION_UNIQUE_IDS_PATCH = "loop-iteration-unique-ids"

_LOOP_ITER_CHAIN_RE = re.compile(r"(?:_iter_\d+)+$")
_LOOP_ITER_CAPTURE_RE = re.compile(r"_iter_(\d+)$")


def use_unique_loop_iteration_ids() -> bool:
    """Return True for new executions; False when replaying pre-patch history.

    Outside a Temporal workflow (unit tests) this returns True so helpers
    exercise the unique-id path by default.
    """
    if not workflow.in_workflow():
        return True
    return workflow.patched(LOOP_ITERATION_UNIQUE_IDS_PATCH)


def strip_loop_iteration_suffixes(activity_id: str) -> str:
    """Return the canvas node ID, removing every trailing ``_iter_N`` suffix."""
    return _LOOP_ITER_CHAIN_RE.sub("", activity_id)


def resolve_loop_iteration_canvas_id(
    activity_id: str,
    canvas_node_ids: Iterable[str],
    loop_body_node_ids: Iterable[str] = (),
    loop_control_node_ids: Iterable[str] = (),
) -> str | None:
    """Resolve a Temporal activity ID to its canvas node using known node IDs.

    Node IDs may themselves contain ``_iter_N``. Matching the longest known
    canvas-node prefix ensures ``approval_iter_0_iter_1`` resolves to
    ``approval_iter_0`` when that canvas node exists, rather than ``approval``.

    A sole loop-body match wins over longer ordinary canvas IDs because only
    loop-body nodes append enclosing-loop indices. A sole loop-control match is
    likewise authoritative. Exact matches and overlapping loop-body/control
    matches are rejected when another node can generate the same ID.
    """
    known_ids = tuple(canvas_node_ids)
    loop_body_ids = set(loop_body_node_ids)
    loop_control_ids = set(loop_control_node_ids)
    matches = [
        node_id
        for node_id in known_ids
        if activity_id.startswith(node_id) and _is_iteration_suffix(activity_id[len(node_id) :])
    ]
    loop_body_matches = [node_id for node_id in matches if node_id in loop_body_ids]
    loop_control_matches = [node_id for node_id in matches if node_id in loop_control_ids]

    if activity_id in known_ids:
        return activity_id if not (loop_body_matches or loop_control_matches) else None

    if (loop_body_matches and loop_control_matches) or len(loop_body_matches) > 1 or len(loop_control_matches) > 1:
        return None
    if len(loop_body_matches) == 1:
        return loop_body_matches[0]
    if len(loop_control_matches) == 1:
        return loop_control_matches[0]
    return max(matches, key=len) if matches else None


def extract_loop_body_node_ids(definition: Mapping[str, Any]) -> set[str]:
    """Return node IDs reachable from loop iterate edges before feedback."""
    loop_ids = {
        node.get("id")
        for node in [*definition.get("nodes", []), *definition.get("triggers", [])]
        if node.get("type") == "loop" and node.get("id")
    }
    edges = definition.get("edges", [])
    body_ids: set[str] = set()

    for loop_id in loop_ids:
        queue = [
            edge["to"]
            for edge in edges
            if edge.get("from") == loop_id and edge.get("from_port") == "iterate" and edge.get("to") != loop_id
        ]
        visited: set[str] = set()
        while queue:
            node_id = queue.pop(0)
            if node_id in visited or node_id == loop_id:
                continue
            visited.add(node_id)
            is_nested_loop = node_id in loop_ids
            if not is_nested_loop:
                body_ids.add(node_id)
            next_edges = [edge for edge in edges if edge.get("from") == node_id]
            if is_nested_loop:
                next_edges = [edge for edge in next_edges if edge.get("from_port") in ("iterate", "complete")]
            queue.extend(edge["to"] for edge in next_edges if edge.get("to") != loop_id)

    return body_ids


def innermost_iteration_index(activity_id: str) -> int | None:
    """Return the last ``_iter_N`` index, or None if the ID has no iteration suffix."""
    match = _LOOP_ITER_CAPTURE_RE.search(activity_id)
    return int(match.group(1)) if match else None


def iteration_indices(activity_id: str) -> list[int]:
    """Return every loop index in a Temporal activity ID, outermost first."""
    return [int(value) for value in re.findall(r"_iter_(\d+)", activity_id)]


def join_loop_iteration_id(node_id: str, indices: Sequence[int]) -> str:
    """Build ``{node_id}_iter_{i0}_iter_{i1}...`` (empty indices → canvas ID)."""
    if not indices:
        return node_id
    return node_id + "".join(f"_iter_{i}" for i in indices)


def loop_index_chain(
    node_id: str,
    loop_body_map: Mapping[str, str],
    node_control_data: Mapping[str, Mapping[str, Any]],
) -> list[int]:
    """Return enclosing-loop ``current_index`` values, outermost first.

    Walks ``loop_body_map`` from ``node_id`` toward outer loops. A visited set
    stops cycles. Missing control data counts as index 0.
    """
    indices: list[int] = []
    seen: set[str] = set()
    parent_loop_id = loop_body_map.get(node_id)
    while parent_loop_id is not None and parent_loop_id not in seen:
        seen.add(parent_loop_id)
        control = node_control_data.get(parent_loop_id, {})
        raw = control.get("current_index", 0)
        indices.append(0 if raw is None else int(raw))
        parent_loop_id = loop_body_map.get(parent_loop_id)
    indices.reverse()
    return indices


def approval_temporal_activity_id(
    node_id: str,
    loop_body_map: Mapping[str, str],
    node_control_data: Mapping[str, Mapping[str, Any]],
) -> str:
    """Temporal activity ID for an approval node.

    New executions use the loop-index chain. Pre-patch in-flight executions
    keep the canvas node ID so replay matches history.
    """
    if not use_unique_loop_iteration_ids():
        return node_id
    return join_loop_iteration_id(node_id, loop_index_chain(node_id, loop_body_map, node_control_data))


def loop_body_temporal_activity_id(
    node_id: str,
    loop_body_map: Mapping[str, str],
    node_control_data: Mapping[str, Mapping[str, Any]],
) -> str:
    """Temporal activity ID for any node scheduled inside one or more loops."""
    if not use_unique_loop_iteration_ids():
        return node_id
    return join_loop_iteration_id(node_id, loop_index_chain(node_id, loop_body_map, node_control_data))


def loop_control_activity_id(
    node_id: str,
    current_index: int,
    loop_body_map: Mapping[str, str],
    node_control_data: Mapping[str, Mapping[str, Any]],
) -> str:
    """Temporal activity ID for a loop control node.

    Top-level loops are ``{node_id}_iter_{current_index}`` on both code paths.
    Nested loops prepend enclosing indices on the new path; pre-patch replay
    uses only ``current_index``.
    """
    if use_unique_loop_iteration_ids():
        enclosing = loop_index_chain(node_id, loop_body_map, node_control_data)
        return join_loop_iteration_id(node_id, [*enclosing, current_index])
    return join_loop_iteration_id(node_id, [current_index])


def _is_iteration_suffix(remainder: str) -> bool:
    return _LOOP_ITER_CHAIN_RE.fullmatch(remainder) is not None


def matches_loop_iteration_id(stored_id: str, canvas_or_activity_id: str) -> bool:
    """Return True if ``stored_id`` is this canvas node or a loop-iteration ID for it.

    Matches suffixed stored ids against a canvas query, and legacy canvas stored
    ids against a suffixed query (pre-upgrade rows expired after deploy).
    """
    if stored_id == canvas_or_activity_id:
        return True
    if stored_id.startswith(canvas_or_activity_id) and _is_iteration_suffix(stored_id[len(canvas_or_activity_id) :]):
        return True
    return canvas_or_activity_id.startswith(stored_id) and _is_iteration_suffix(canvas_or_activity_id[len(stored_id) :])
