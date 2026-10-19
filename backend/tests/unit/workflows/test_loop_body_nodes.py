"""Tests for extracting loop bodies at each nesting level."""

from syntara.workflows.utils.loop_body_nodes import collect_direct_loop_bodies


def test_direct_loop_bodies_keep_nested_controller_but_drop_its_descendants() -> None:
    loop_bodies = {
        "outer": {"outer_step", "inner", "inner_step", "deep", "deep_step"},
        "inner": {"inner_step", "deep", "deep_step"},
        "deep": {"deep_step"},
    }

    assert collect_direct_loop_bodies(loop_bodies, {"outer", "inner", "deep"}) == {
        "outer": {"outer_step", "inner"},
        "inner": {"inner_step", "deep"},
        "deep": {"deep_step"},
    }
