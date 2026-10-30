"""Derivation of the sub-workflow iteration-aware invocation identity.

``_execute_sub_workflow_node`` derives the invocation identity as
``join_loop_iteration_id(node_id, loop_index_chain(node_id, loop_body_map,
node_control_data))`` and uses it for BOTH the setup activity id
(``__internal__setup_sub_workflow_{invocation_node_id}``) and the child
execution id. These tests pin that derivation's format so a sub_workflow node
is distinct per loop iteration and per nesting level, and unchanged outside any
loop.
"""

from __future__ import annotations

from typing import Any

from syntara.workflows.workflow_engine.utils.loop_iteration_ids import (
    join_loop_iteration_id,
    loop_index_chain,
)


def _invocation_node_id(
    node_id: str,
    loop_body_map: dict[str, str],
    node_control_data: dict[str, dict[str, Any]],
) -> str:
    """Mirror the derivation used in _execute_sub_workflow_node."""
    return join_loop_iteration_id(node_id, loop_index_chain(node_id, loop_body_map, node_control_data))


def test_outside_loop_is_canvas_node_id() -> None:
    """With no enclosing loop the invocation identity equals the canvas node id."""
    assert _invocation_node_id("sub_wf_node", {}, {}) == "sub_wf_node"


def test_single_loop_appends_current_index() -> None:
    """A single enclosing loop appends its current_index as _iter_{n}."""
    body_map = {"sub_wf_node": "loopA"}
    control = {"loopA": {"current_index": 2}}
    assert _invocation_node_id("sub_wf_node", body_map, control) == "sub_wf_node_iter_2"


def test_nested_loops_append_outermost_first() -> None:
    """Nested loops append enclosing indices outermost-first."""
    body_map = {"sub_wf_node": "loopB", "loopB": "loopA"}
    control = {"loopA": {"current_index": 1}, "loopB": {"current_index": 0}}
    assert _invocation_node_id("sub_wf_node", body_map, control) == "sub_wf_node_iter_1_iter_0"


def test_distinct_iterations_yield_distinct_ids() -> None:
    """Different current_index values produce different invocation identities."""
    body_map = {"sub_wf_node": "loopA"}
    id0 = _invocation_node_id("sub_wf_node", body_map, {"loopA": {"current_index": 0}})
    id1 = _invocation_node_id("sub_wf_node", body_map, {"loopA": {"current_index": 1}})
    assert id0 != id1
