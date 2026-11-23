"""Unit tests for shared Execution Plane utilities."""

from syntara.execution_plane import utils


def test_supported_node_types_are_the_two_script_types() -> None:
    assert utils.execution_plane_supported_node_types() == frozenset({"script_python", "script_bash"})
