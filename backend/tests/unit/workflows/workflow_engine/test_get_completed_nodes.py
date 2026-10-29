"""Unit tests for OrchestratorWorkflow.get_completed_nodes query method.

The query derives successfully-completed node IDs from the resolver's positive
completion marker (namespace ``status == "completed"``), excluding failed
(``status == "failed"``) and skipped (empty namespace) nodes. It is consumed by
the completion finalizer to mark sub-workflow activity rows COMPLETED.
"""

from unittest.mock import Mock

from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow


def _make_workflow(namespaces: dict[str, object]) -> OrchestratorWorkflow:
    """Build an OrchestratorWorkflow whose resolver returns the given namespaces."""
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    resolver = Mock()
    resolver.get_all_namespaces.return_value = namespaces
    wf.resolver = resolver
    return wf


class TestGetCompletedNodes:
    """Return values for various namespace states."""

    def test_returns_only_completed_status_nodes(self) -> None:
        """Only nodes whose namespace status is 'completed' are returned."""
        wf = _make_workflow(
            {
                "node_ok": {"status": "completed", "out": 1},
                "node_fail": {"status": "failed", "error": "boom"},
                "node_skip": {},
            }
        )
        assert sorted(wf.get_completed_nodes()) == ["node_ok"]

    def test_excludes_failed_and_skipped(self) -> None:
        """Failed (status failed) and skipped (empty) namespaces are excluded."""
        wf = _make_workflow({"a": {"status": "failed"}, "b": {}})
        assert wf.get_completed_nodes() == []

    def test_returns_all_completed(self) -> None:
        """Multiple completed nodes are all returned."""
        wf = _make_workflow({"a": {"status": "completed"}, "b": {"status": "completed"}, "c": {"status": "failed"}})
        assert sorted(wf.get_completed_nodes()) == ["a", "b"]

    def test_returns_list_type(self) -> None:
        """The query must return a list (query-serializable), not a set."""
        wf = _make_workflow({"a": {"status": "completed"}})
        assert isinstance(wf.get_completed_nodes(), list)

    def test_empty_when_no_namespaces(self) -> None:
        """No namespaces yields an empty list."""
        wf = _make_workflow({})
        assert wf.get_completed_nodes() == []

    def test_defensive_against_non_dict_namespace(self) -> None:
        """Non-dict namespace values are ignored, not crashed on."""
        wf = _make_workflow({"a": {"status": "completed"}, "b": "not-a-dict", "c": None})
        assert wf.get_completed_nodes() == ["a"]

    def test_status_must_be_exactly_completed(self) -> None:
        """A different status value (e.g. 'running') is not treated as completed."""
        wf = _make_workflow({"a": {"status": "running"}, "b": {"other": "completed"}})
        assert wf.get_completed_nodes() == []
