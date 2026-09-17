"""Unit tests for loop-iteration Temporal / approval ID helpers."""

from unittest.mock import patch

from syntara.workflows.workflow_engine.utils.loop_iteration_ids import (
    approval_temporal_activity_id,
    innermost_iteration_index,
    join_loop_iteration_id,
    loop_control_activity_id,
    loop_index_chain,
    matches_loop_iteration_id,
    strip_loop_iteration_suffixes,
)


def test_strip_loop_iteration_suffixes_plain_id() -> None:
    """Canvas IDs are unchanged."""
    assert strip_loop_iteration_suffixes("approval") == "approval"


def test_strip_loop_iteration_suffixes_single_and_nested() -> None:
    """Every trailing numeric _iter_N suffix is removed."""
    assert strip_loop_iteration_suffixes("approval_iter_3") == "approval"
    assert strip_loop_iteration_suffixes("approval_iter_1_iter_0") == "approval"
    assert strip_loop_iteration_suffixes("approval_iter_2_iter_4_iter_1") == "approval"


def test_strip_loop_iteration_suffixes_ignores_non_numeric() -> None:
    """A non-numeric _iter_ tail is not a loop suffix."""
    assert strip_loop_iteration_suffixes("approval_iter_n") == "approval_iter_n"


def test_innermost_iteration_index() -> None:
    """The last _iter_N is the innermost loop index."""
    assert innermost_iteration_index("approval") is None
    assert innermost_iteration_index("approval_iter_3") == 3
    assert innermost_iteration_index("approval_iter_1_iter_0") == 0


def test_join_loop_iteration_id() -> None:
    """Empty chain is the canvas ID; otherwise outermost-first suffixes."""
    assert join_loop_iteration_id("approval", []) == "approval"
    assert join_loop_iteration_id("approval", [3]) == "approval_iter_3"
    assert join_loop_iteration_id("approval", [1, 0]) == "approval_iter_1_iter_0"


def test_loop_index_chain_no_parent() -> None:
    """Nodes outside a loop have an empty chain."""
    assert loop_index_chain("approval", {}, {}) == []


def test_loop_index_chain_single_loop() -> None:
    """One parent loop contributes its current_index."""
    chain = loop_index_chain(
        "approval",
        {"approval": "loop"},
        {"loop": {"current_index": 3}},
    )
    assert chain == [3]


def test_loop_index_chain_nested_outermost_first() -> None:
    """Nested loops encode outer then inner so inner-index resets stay unique."""
    chain = loop_index_chain(
        "approval",
        {"approval": "inner", "inner": "outer"},
        {"inner": {"current_index": 0}, "outer": {"current_index": 2}},
    )
    assert chain == [2, 0]
    assert join_loop_iteration_id("approval", chain) == "approval_iter_2_iter_0"


def test_loop_index_chain_second_outer_iteration_differs() -> None:
    """The same inner index under a new outer index produces a distinct ID."""
    first = join_loop_iteration_id(
        "approval",
        loop_index_chain(
            "approval",
            {"approval": "inner", "inner": "outer"},
            {"inner": {"current_index": 0}, "outer": {"current_index": 0}},
        ),
    )
    second = join_loop_iteration_id(
        "approval",
        loop_index_chain(
            "approval",
            {"approval": "inner", "inner": "outer"},
            {"inner": {"current_index": 0}, "outer": {"current_index": 1}},
        ),
    )
    assert first == "approval_iter_0_iter_0"
    assert second == "approval_iter_1_iter_0"
    assert first != second


def test_loop_index_chain_breaks_cycles() -> None:
    """A cyclic loop_body_map must not loop forever."""
    chain = loop_index_chain(
        "approval",
        {"approval": "a", "a": "b", "b": "a"},
        {"a": {"current_index": 1}, "b": {"current_index": 2}},
    )
    assert chain == [2, 1]


def test_loop_control_activity_id_top_level() -> None:
    """A loop that is not inside another loop is {id}_iter_{n}."""
    assert loop_control_activity_id("outer", 0, {}, {}) == "outer_iter_0"
    assert loop_control_activity_id("outer", 3, {}, {}) == "outer_iter_3"


def test_loop_control_activity_id_nested() -> None:
    """Inner loop control IDs prepend enclosing indices, outermost first."""
    body_map = {"inner": "outer"}
    control = {"outer": {"current_index": 2}}
    assert loop_control_activity_id("inner", 0, body_map, control) == "inner_iter_2_iter_0"


def test_loop_control_activity_id_same_inner_next_outer_differs() -> None:
    """The same inner index under a new outer index must not reuse a Temporal ID."""
    body_map = {"inner": "outer"}
    first = loop_control_activity_id("inner", 0, body_map, {"outer": {"current_index": 0}})
    second = loop_control_activity_id("inner", 0, body_map, {"outer": {"current_index": 1}})
    assert first == "inner_iter_0_iter_0"
    assert second == "inner_iter_1_iter_0"
    assert first != second


def test_loop_control_activity_id_unpatched_nested_uses_own_index_only() -> None:
    """Pre-patch nested loop control IDs used only the inner current_index."""
    body_map = {"inner": "outer"}
    control = {"outer": {"current_index": 2}}
    with patch(
        "syntara.workflows.workflow_engine.utils.loop_iteration_ids.use_unique_loop_iteration_ids",
        return_value=False,
    ):
        assert loop_control_activity_id("inner", 0, body_map, control) == "inner_iter_0"


def test_approval_temporal_activity_id_new_and_unpatched() -> None:
    """New runs suffix Temporal IDs; unpatched replay keeps the canvas ID."""
    body_map = {"approval": "loop"}
    control = {"loop": {"current_index": 3}}
    assert approval_temporal_activity_id("approval", body_map, control) == "approval_iter_3"
    with patch(
        "syntara.workflows.workflow_engine.utils.loop_iteration_ids.use_unique_loop_iteration_ids",
        return_value=False,
    ):
        assert approval_temporal_activity_id("approval", body_map, control) == "approval"


def test_matches_loop_iteration_id() -> None:
    """Expire-by-canvas-id matches any depth of numeric suffixes, including reverse."""
    assert matches_loop_iteration_id("approval", "approval")
    assert matches_loop_iteration_id("approval_iter_1", "approval")
    assert matches_loop_iteration_id("approval_iter_1_iter_0", "approval")
    assert matches_loop_iteration_id("approval_iter_1_iter_0", "approval_iter_1_iter_0")
    assert matches_loop_iteration_id("approval", "approval_iter_1")
    assert not matches_loop_iteration_id("approval_iter_notanumber", "approval")
    assert not matches_loop_iteration_id("other_iter_1", "approval")
    assert not matches_loop_iteration_id("approval_iter_0", "approval_iter_1")
