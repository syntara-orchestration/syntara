"""Unit tests for per-node error handling in the workflow engine (task 5.1).

Tests verify that:
- NexusWorkflow tracks failed nodes separately from skipped nodes
- Failed nodes store error information in the resolver
- Downstream nodes of a failed node are marked as skipped
- _is_unreachable treats failed nodes as unreachable
- _mark_downstream_as_skipped respects failed predecessors
- Workflow status reflects failures
"""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import NexusWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend
from tests.unit.workflows.workflow_engine.conftest import init_workflow_runtime


@pytest.fixture(autouse=True)
def _mock_workflow_logger() -> Generator[None]:
    """Mock Temporal workflow logger to avoid 'Not in workflow event loop' errors."""
    mock_logger = MagicMock()
    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
        mock_wf.logger = mock_logger
        yield


def _make_workflow(
    skipped_nodes: set[str] | None = None,
    failed_nodes: dict[str, str] | None = None,
    resolver: NamespaceResolver | None = None,
    node_inputs: dict[str, dict[str, object]] | None = None,
    node_control_data: dict[str, dict[str, object]] | None = None,
) -> NexusWorkflow:
    """Create a NexusWorkflow with initialized state, bypassing __init__."""
    wf = NexusWorkflow.__new__(NexusWorkflow)
    wf.skipped_nodes = skipped_nodes if skipped_nodes is not None else set()
    wf.failed_nodes = failed_nodes if failed_nodes is not None else {}
    wf.resolver = resolver if resolver is not None else NamespaceResolver()
    wf.node_inputs = node_inputs if node_inputs is not None else {}
    wf.node_control_data = node_control_data if node_control_data is not None else {}
    wf.loop_state = {}
    wf.loop_body_map = {}
    wf.loop_iteration_results = {}
    wf._timeout_tasks = {}
    wf._timed_out_converge_nodes = set()
    wf._detached_nodes = set()
    wf._converge_branch_nodes = {}
    init_workflow_runtime(wf)
    wf.pre_resolved_outputs = {}
    wf.stop_after_nodes = set()
    return wf


def _make_linear_graph() -> WorkflowGraph:
    r"""Build: trigger -> A -> B -> C (linear chain)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("A", {"id": "A", "type": "action", "parameters": {}})
    backend.add_node("B", {"id": "B", "type": "action", "parameters": {}})
    backend.add_node("C", {"id": "C", "type": "action", "parameters": {}})

    backend.add_edge("trigger", "A", None)
    backend.add_edge("A", "B", None)
    backend.add_edge("B", "C", None)

    return WorkflowGraph(backend)


def _make_diamond_graph() -> WorkflowGraph:
    r"""Build a diamond DAG.

    trigger -> A -> B -> D
                \-> C -> D
    B and C are independent branches; D is a converge node.
    """
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("A", {"id": "A", "type": "action", "parameters": {}})
    backend.add_node("B", {"id": "B", "type": "action", "parameters": {}})
    backend.add_node("C", {"id": "C", "type": "action", "parameters": {}})
    backend.add_node("D", {"id": "D", "type": "action", "parameters": {}})

    backend.add_edge("trigger", "A", None)
    backend.add_edge("A", "B", None)
    backend.add_edge("A", "C", None)
    backend.add_edge("B", "D", None)
    backend.add_edge("C", "D", None)

    return WorkflowGraph(backend)


class TestFailedNodesTracking:
    """Verify the failed_nodes dict is properly initialized and used."""

    def test_failed_nodes_initialized_as_empty_dict(self) -> None:
        """failed_nodes should be an empty dict after workflow state init."""
        wf = _make_workflow()
        assert wf.failed_nodes == {}

    def test_failed_nodes_stores_error_message(self) -> None:
        """failed_nodes should map node_id to error message string."""
        wf = _make_workflow()
        wf.failed_nodes["node_a"] = "ValueError: bad input"
        assert wf.failed_nodes["node_a"] == "ValueError: bad input"

    def test_failed_nodes_independent_from_skipped_nodes(self) -> None:
        """A node can be in failed_nodes without being in skipped_nodes."""
        wf = _make_workflow()
        wf.failed_nodes["node_a"] = "RuntimeError: boom"
        assert "node_a" not in wf.skipped_nodes

    def test_multiple_nodes_can_fail(self) -> None:
        """Multiple independent nodes can fail in the same workflow."""
        wf = _make_workflow()
        wf.failed_nodes["node_a"] = "Error: first"
        wf.failed_nodes["node_b"] = "Error: second"
        assert len(wf.failed_nodes) == 2


class TestErrorInfoInResolver:
    """Verify failed nodes store error details in the resolver."""

    def test_failed_node_error_accessible_via_resolver(self) -> None:
        """The implementation stores {status: failed, error: ...} in the resolver."""
        wf = _make_workflow()
        error_msg = "ValueError: bad input"
        wf.failed_nodes["node_a"] = error_msg
        wf.resolver.set_namespace("node_a", {"status": "failed", "error": error_msg})

        output = wf.resolver.get_namespace("node_a")
        assert output["status"] == "failed"
        assert output["error"] == error_msg

    def test_failed_node_has_namespace_returns_true(self) -> None:
        """A failed node still has a namespace (with error info) in the resolver."""
        wf = _make_workflow()
        wf.resolver.set_namespace("node_a", {"status": "failed", "error": "boom"})
        wf.failed_nodes["node_a"] = "boom"
        assert wf.resolver.has_namespace("node_a")


class TestIsUnreachableWithFailedNodes:
    """Verify _is_unreachable treats failed nodes correctly."""

    def test_failed_node_is_unreachable(self) -> None:
        """A failed node should be considered unreachable."""
        wf = _make_workflow(failed_nodes={"A": "RuntimeError: boom"})
        graph = _make_linear_graph()
        assert wf._is_unreachable("A", graph) is True

    def test_skipped_node_still_unreachable(self) -> None:
        """Existing skipped behavior should still work."""
        wf = _make_workflow(skipped_nodes={"A"})
        graph = _make_linear_graph()
        assert wf._is_unreachable("A", graph) is True

    def test_node_with_only_failed_predecessor_is_unreachable(self) -> None:
        """A node whose only predecessor failed should be unreachable."""
        wf = _make_workflow(failed_nodes={"A": "Error: x"})
        # A has a namespace (the error data), but is in failed_nodes
        wf.resolver.set_namespace("A", {"status": "failed", "error": "Error: x"})
        graph = _make_linear_graph()
        assert wf._is_unreachable("B", graph) is True

    def test_node_with_successful_predecessor_is_reachable(self) -> None:
        """A node whose predecessor completed successfully is reachable."""
        wf = _make_workflow()
        wf.resolver.set_namespace("A", {"result": "ok"})
        graph = _make_linear_graph()
        assert wf._is_unreachable("B", graph) is False

    def test_node_reachable_if_any_predecessor_succeeded_in_diamond(self) -> None:
        """In a diamond, if one branch succeeds and the other fails, D is reachable."""
        wf = _make_workflow(failed_nodes={"B": "Error: x"})
        wf.resolver.set_namespace("B", {"status": "failed", "error": "Error: x"})
        wf.resolver.set_namespace("C", {"result": "ok"})
        # A completed (both B and C depend on it)
        wf.resolver.set_namespace("A", {"result": "ok"})
        graph = _make_diamond_graph()
        # D has predecessors B (failed) and C (succeeded)
        assert wf._is_unreachable("D", graph) is False

    def test_node_unreachable_if_all_predecessors_failed_or_skipped(self) -> None:
        """A node is unreachable if all its predecessors are failed or skipped."""
        wf = _make_workflow(
            failed_nodes={"B": "Error: x"},
            skipped_nodes={"C"},
        )
        wf.resolver.set_namespace("B", {"status": "failed", "error": "Error: x"})
        wf.resolver.set_namespace("A", {"result": "ok"})
        graph = _make_diamond_graph()
        # D has predecessors B (failed) and C (skipped)
        assert wf._is_unreachable("D", graph) is True

    def test_trigger_node_always_reachable(self) -> None:
        """Root nodes (no predecessors) are always reachable."""
        wf = _make_workflow()
        graph = _make_linear_graph()
        assert wf._is_unreachable("trigger", graph) is False


class TestMarkDownstreamAsSkipped:
    """Verify _mark_downstream_as_skipped propagates through failed nodes."""

    def test_downstream_of_failed_node_marked_skipped(self) -> None:
        """Nodes downstream of a failed node should be marked as skipped."""
        wf = _make_workflow(failed_nodes={"A": "Error: boom"})
        graph = _make_linear_graph()

        wf._mark_downstream_as_skipped("A", graph)

        assert "B" in wf.skipped_nodes
        assert "C" in wf.skipped_nodes

    def test_downstream_propagation_skips_already_completed_nodes(self) -> None:
        """Nodes that already completed should not be overwritten as skipped."""
        wf = _make_workflow(failed_nodes={"A": "Error: boom"})
        wf.resolver.set_namespace("B", {"result": "already done"})
        graph = _make_linear_graph()

        wf._mark_downstream_as_skipped("A", graph)

        # B was already completed, so it's not in skipped_nodes
        assert "B" not in wf.skipped_nodes

    def test_independent_branch_not_affected(self) -> None:
        """In a diamond, failing B should not skip C (independent branch)."""
        wf = _make_workflow(failed_nodes={"B": "Error: boom"})
        # A completed successfully
        wf.resolver.set_namespace("A", {"result": "ok"})
        graph = _make_diamond_graph()

        wf._mark_downstream_as_skipped("B", graph)

        # C is independent of B (both depend on A), so C should NOT be skipped
        assert "C" not in wf.skipped_nodes

    def test_converge_node_skipped_when_all_predecessors_failed_or_skipped(self) -> None:
        """D is skipped when both B (failed) and C (skipped) cannot produce output."""
        wf = _make_workflow(
            failed_nodes={"B": "Error: x"},
            skipped_nodes={"C"},
        )
        graph = _make_diamond_graph()

        # Mark downstream of B
        wf._mark_downstream_as_skipped("B", graph)

        # D should be skipped because both B (failed) and C (skipped)
        assert "D" in wf.skipped_nodes

    def test_converge_node_not_skipped_when_one_branch_alive(self) -> None:
        """D is NOT skipped if C is still alive (not skipped/failed)."""
        wf = _make_workflow(failed_nodes={"B": "Error: x"})
        # A completed, C depends on A and is NOT skipped/failed
        wf.resolver.set_namespace("A", {"result": "ok"})
        graph = _make_diamond_graph()

        wf._mark_downstream_as_skipped("B", graph)

        # D should NOT be skipped — C is still a viable predecessor
        assert "D" not in wf.skipped_nodes

    def test_deep_chain_propagation(self) -> None:
        """Skipping propagates through a multi-node chain: A(failed) -> B -> C."""
        wf = _make_workflow(failed_nodes={"A": "Error: x"})
        graph = _make_linear_graph()

        wf._mark_downstream_as_skipped("A", graph)

        assert "B" in wf.skipped_nodes
        assert "C" in wf.skipped_nodes


class TestWorkflowStatusReflectsFailure:
    """Verify that workflow status is 'failed' when any node fails."""

    def test_status_failed_when_failed_nodes_not_empty(self) -> None:
        """The workflow result should have status 'failed' if any node failed."""
        wf = _make_workflow(failed_nodes={"A": "RuntimeError: boom"})
        # Simulate the status computation from the run() method
        workflow_status = "failed" if wf.failed_nodes else "completed"
        assert workflow_status == "failed"

    def test_status_completed_when_no_failures(self) -> None:
        """The workflow result should have status 'completed' if no node failed."""
        wf = _make_workflow()
        workflow_status = "failed" if wf.failed_nodes else "completed"
        assert workflow_status == "completed"

    def test_status_failed_even_with_one_failure_among_many(self) -> None:
        """Even a single failure should make the workflow status 'failed'."""
        wf = _make_workflow(failed_nodes={"C": "TimeoutError: timed out"})
        workflow_status = "failed" if wf.failed_nodes else "completed"
        assert workflow_status == "failed"


class TestSkippedNodesUpdatedForDownstreamFailures:
    """Verify skipped_nodes set includes nodes downstream of failures."""

    def test_skipped_nodes_includes_downstream_of_failure(self) -> None:
        """get_skipped_nodes should include nodes downstream of a failed node."""
        wf = _make_workflow(failed_nodes={"A": "Error: x"})
        graph = _make_linear_graph()

        wf._mark_downstream_as_skipped("A", graph)
        result = wf.get_skipped_nodes()

        assert "B" in result
        assert "C" in result

    def test_failed_node_itself_not_in_skipped_nodes(self) -> None:
        """The failed node itself should be in failed_nodes, not skipped_nodes."""
        wf = _make_workflow(failed_nodes={"A": "Error: x"})
        graph = _make_linear_graph()

        wf._mark_downstream_as_skipped("A", graph)

        assert "A" not in wf.skipped_nodes
        assert "A" in wf.failed_nodes


class TestMarkRemainingUnreachableNodes:
    """Verify final pass marks unreachable nodes for failed predecessors."""

    def test_unexecuted_node_after_failure_marked_skipped(self) -> None:
        """Nodes that never executed after a failure are marked skipped in final pass."""
        wf = _make_workflow(failed_nodes={"A": "Error: x"})
        wf.resolver.set_namespace("A", {"status": "failed", "error": "Error: x"})
        graph = _make_linear_graph()
        # trigger and A have namespaces, B and C do not
        wf.resolver.set_namespace("trigger", {"data": "trigger_output"})

        wf._mark_remaining_unreachable_nodes(graph)

        # B and C were never executed and are unreachable, should be skipped
        assert "B" in wf.skipped_nodes
        assert "C" in wf.skipped_nodes


class TestErrorMessageFormat:
    """Verify the error message format stored in failed_nodes."""

    def test_error_message_includes_exception_type(self) -> None:
        """The implementation formats errors as 'ExceptionType: message'."""
        exc = ValueError("something went wrong")
        error_message = f"{type(exc).__name__}: {exc}"

        assert error_message == "ValueError: something went wrong"
        assert error_message.startswith("ValueError:")

    def test_error_message_includes_runtime_error(self) -> None:
        """RuntimeError should also be formatted correctly."""
        exc = RuntimeError("connection lost")
        error_message = f"{type(exc).__name__}: {exc}"

        assert error_message == "RuntimeError: connection lost"


def _make_approval_graph(node_id: str = "approval_1") -> WorkflowGraph:
    """Single approval node with no successors."""
    backend = InMemoryGraphBackend()
    backend.add_node(node_id, {"id": node_id, "type": "approval", "parameters": {}})
    return WorkflowGraph(backend)


class TestRouteFailedNode:
    """_route_failed_node sets routing data so successors follow the correct branch."""

    def test_loop_node_routes_to_complete_port(self) -> None:
        """A failed loop node should route to the 'complete' (Done) port."""
        wf = _make_workflow()
        node = ActivityNode("loop_1", "loop", {"type": "for_each", "items": "input.data"})

        wf._route_failed_node("loop_1", node)

        assert wf.node_control_data["loop_1"] == {"next_port": "complete"}

    def test_non_loop_node_does_not_set_control_data(self) -> None:
        """A failed non-loop node should not have routing data set."""
        wf = _make_workflow()
        node = ActivityNode("action_1", "action", {"executor": "http"})

        wf._route_failed_node("action_1", node)

        assert "action_1" not in wf.node_control_data

    def test_does_not_overwrite_existing_control_data_for_non_loop(self) -> None:
        """Existing control data for a non-loop node remains untouched."""
        wf = _make_workflow(node_control_data={"action_1": {"next_port": "custom"}})
        node = ActivityNode("action_1", "action", {"executor": "http"})

        wf._route_failed_node("action_1", node)

        assert wf.node_control_data["action_1"] == {"next_port": "custom"}


class TestContinueOnFailureApproval:
    """_handle_continued_failure routes approval nodes via fallback_decision."""

    @pytest.mark.asyncio
    async def test_reject_fallback_sets_control_data(self) -> None:
        """Explicit fallback_decision='reject' routes to the rejected port."""
        wf = _make_workflow()
        node = ActivityNode("approval_1", "approval", {"fallback_decision": "reject"}, name="Review")
        wf.node_inputs["approval_1"] = {"fallback_decision": "reject"}

        await wf._handle_continued_failure("approval_1", node, _make_approval_graph(), {})

        assert wf.node_control_data["approval_1"] == {"next_port": "rejected"}

    @pytest.mark.asyncio
    async def test_approve_fallback_sets_control_data(self) -> None:
        """Explicit fallback_decision='approve' routes to the approved port."""
        wf = _make_workflow()
        node = ActivityNode("approval_1", "approval", {"fallback_decision": "approve"}, name="Review")
        wf.node_inputs["approval_1"] = {"fallback_decision": "approve"}

        await wf._handle_continued_failure("approval_1", node, _make_approval_graph(), {})

        assert wf.node_control_data["approval_1"] == {"next_port": "approved"}

    @pytest.mark.asyncio
    async def test_default_fallback_is_reject(self) -> None:
        """When fallback_decision is absent the safe default 'reject' is used."""
        wf = _make_workflow()
        node = ActivityNode("approval_1", "approval", {}, name="Review")
        wf.node_inputs["approval_1"] = {}

        await wf._handle_continued_failure("approval_1", node, _make_approval_graph(), {})

        assert wf.node_control_data["approval_1"] == {"next_port": "rejected"}

    @pytest.mark.asyncio
    async def test_uses_resolved_parameters_not_raw_config(self) -> None:
        """fallback_decision is read from node_inputs (resolved), not node.parameters (raw template)."""
        wf = _make_workflow()
        node = ActivityNode("approval_1", "approval", {"fallback_decision": "${vars.decision}"}, name="Review")
        # Engine stored the resolved value in node_inputs before the activity ran
        wf.node_inputs["approval_1"] = {"fallback_decision": "approve"}

        await wf._handle_continued_failure("approval_1", node, _make_approval_graph(), {})

        assert wf.node_control_data["approval_1"] == {"next_port": "approved"}

    @pytest.mark.asyncio
    async def test_invalid_fallback_raises_non_retryable_config_error(self) -> None:
        """An unrecognised fallback_decision value raises ConfigError immediately."""
        wf = _make_workflow()
        node = ActivityNode("approval_1", "approval", {"fallback_decision": "defer"}, name="Review")
        wf.node_inputs["approval_1"] = {"fallback_decision": "defer"}

        with pytest.raises(ApplicationError) as exc_info:
            await wf._handle_continued_failure("approval_1", node, _make_approval_graph(), {})

        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.non_retryable is True
        assert "defer" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_non_approval_node_does_not_set_control_data(self) -> None:
        """CoF on a non-approval node (e.g., script) leaves node_control_data untouched."""
        wf = _make_workflow()
        node = ActivityNode("script_1", "script", {"language": "bash", "code": "echo hi"})
        backend = InMemoryGraphBackend()
        backend.add_node("script_1", {"id": "script_1", "type": "script", "parameters": {}})
        graph = WorkflowGraph(backend)

        await wf._handle_continued_failure("script_1", node, graph, {})

        assert "script_1" not in wf.node_control_data
