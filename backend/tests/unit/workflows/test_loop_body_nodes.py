"""Tests for extracting loop bodies at each nesting level."""

from syntara.workflows.utils.loop_body_nodes import collect_loop_bodies


def test_loop_bodies_follow_iterate_seeds_and_include_nested_regions() -> None:
    adjacency = {
        "outer_step": ["inner"],
        "inner": ["inner_step"],
        "inner_step": ["after_inner"],
    }

    assert collect_loop_bodies(adjacency, {"outer": ["outer_step"], "inner": ["inner_step"]}) == {
        "outer": {"outer_step", "inner", "inner_step", "after_inner"},
        "inner": {"inner_step", "after_inner"},
    }


def test_loop_body_walk_handles_converging_paths() -> None:
    adjacency = {"body_a": ["body_b"], "body_b": []}

    assert collect_loop_bodies(adjacency, {"loop": ["body_a", "body_b"]}) == {"loop": {"body_a", "body_b"}}
