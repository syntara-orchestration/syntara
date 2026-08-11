"""Unit tests for NexusWorkflow.get_skipped_nodes query method.

Verifies that only one get_skipped_nodes method exists on NexusWorkflow,
that it directly accesses self.skipped_nodes (no hasattr guard),
and that it returns the correct data.
"""

import inspect

import pytest

from syntara.workflows.workflow_engine.dynamic_workflow import NexusWorkflow


class TestGetSkippedNodesUniqueness:
    """Verify only one get_skipped_nodes definition exists."""

    def test_only_one_get_skipped_nodes_method_defined_in_source(self) -> None:
        """The source file should contain exactly one definition of get_skipped_nodes."""
        source = inspect.getsource(NexusWorkflow)
        count = source.count("def get_skipped_nodes")
        assert count == 1, f"Expected exactly 1 definition of get_skipped_nodes, found {count}"

    def test_get_skipped_nodes_is_callable(self) -> None:
        """get_skipped_nodes should be a callable method on the class."""
        assert hasattr(NexusWorkflow, "get_skipped_nodes")
        assert callable(NexusWorkflow.get_skipped_nodes)


class TestGetSkippedNodesNoHasattrGuard:
    """Verify the remaining method directly accesses self.skipped_nodes."""

    def test_no_hasattr_guard_in_get_skipped_nodes_source(self) -> None:
        """The method body should not contain a hasattr check."""
        source = inspect.getsource(NexusWorkflow.get_skipped_nodes)
        assert "hasattr" not in source, (
            "get_skipped_nodes should directly access self.skipped_nodes without a hasattr guard"
        )

    def test_raises_attribute_error_when_skipped_nodes_not_initialized(self) -> None:
        """Calling get_skipped_nodes before run() should raise AttributeError.

        This confirms the hasattr guard was removed — the method directly
        accesses self.skipped_nodes which is only set during run().
        """
        wf = NexusWorkflow.__new__(NexusWorkflow)
        # Do NOT call __init__ or run() — skipped_nodes won't exist
        with pytest.raises(AttributeError):
            wf.get_skipped_nodes()


class TestGetSkippedNodesReturnValue:
    """Verify correct return values for various skipped_nodes states."""

    def _make_workflow_with_skipped_nodes(self, skipped: set[str]) -> NexusWorkflow:
        """Create a NexusWorkflow instance with skipped_nodes set directly."""
        wf = NexusWorkflow.__new__(NexusWorkflow)
        wf.skipped_nodes = skipped
        return wf

    def test_returns_empty_list_when_no_nodes_skipped(self) -> None:
        """get_skipped_nodes should return an empty list when skipped_nodes is empty."""
        wf = self._make_workflow_with_skipped_nodes(set())
        result = wf.get_skipped_nodes()
        assert result == []

    def test_returns_list_type_not_set(self) -> None:
        """get_skipped_nodes must return a list, not a set."""
        wf = self._make_workflow_with_skipped_nodes({"node_a"})
        result = wf.get_skipped_nodes()
        assert isinstance(result, list), f"Expected list, got {type(result).__name__}"

    def test_returns_all_skipped_node_ids(self) -> None:
        """get_skipped_nodes should return all node IDs that were skipped."""
        skipped = {"node_a", "node_b", "node_c"}
        wf = self._make_workflow_with_skipped_nodes(skipped)
        result = wf.get_skipped_nodes()
        assert sorted(result) == sorted(skipped)

    def test_returns_single_skipped_node(self) -> None:
        """get_skipped_nodes should work with a single skipped node."""
        wf = self._make_workflow_with_skipped_nodes({"only_node"})
        result = wf.get_skipped_nodes()
        assert result == ["only_node"]

    def test_returns_fresh_list_each_call(self) -> None:
        """Each call should return a new list (not a reference to internal state)."""
        wf = self._make_workflow_with_skipped_nodes({"node_x"})
        result1 = wf.get_skipped_nodes()
        result2 = wf.get_skipped_nodes()
        assert result1 == result2
        assert result1 is not result2, "Should return a new list each time, not the same object"

    def test_reflects_mutations_to_skipped_nodes(self) -> None:
        """If skipped_nodes is mutated between calls, the query reflects the change."""
        wf = self._make_workflow_with_skipped_nodes({"node_a"})
        assert wf.get_skipped_nodes() == ["node_a"]

        wf.skipped_nodes.add("node_b")
        result = wf.get_skipped_nodes()
        assert sorted(result) == ["node_a", "node_b"]

    def test_does_not_contain_duplicates(self) -> None:
        """Since skipped_nodes is a set, result should never contain duplicates."""
        wf = self._make_workflow_with_skipped_nodes(set())
        wf.skipped_nodes.add("node_a")
        wf.skipped_nodes.add("node_a")  # Adding same ID twice
        result = wf.get_skipped_nodes()
        assert result == ["node_a"]
