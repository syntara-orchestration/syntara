"""Supplementary tests for NexusWorkflow execution engine (task 6.3 — TEST).

Covers gaps not addressed by the DEV tests:
- _is_unreachable: transitive unreachability detection
- activity_signal: signal storage for async callbacks
- _execute_executor_node: unknown executor type fallback
- _mark_downstream_as_skipped: already-completed successor not re-skipped
- _mark_remaining_unreachable_nodes: final pass catches un-executed nodes
- _loop_body_complete: empty body and nested-loop-still-iterating edge cases
- _clear_loop_body: non-dict results, multiple-iteration accumulation
- get_skipped_nodes: includes failed-downstream nodes
- per-node timeout: settings.timeout overrides the per-type catalog default
"""

import asyncio
from collections.abc import Generator
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.core.exceptions import SafeValueError
from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import (
    ALLOWED_TRIGGER_TYPES,
    NexusWorkflow,
)
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ActivityName,
    DoWhileLoopState,
    ForEachLoopState,
    NodeSettingsNoRetry,
    NodeType,
)
from syntara.workflows.workflow_engine.node_settings_resolver import get_default_timeout
from tests.unit.workflows.workflow_engine.conftest import init_workflow_runtime


@pytest.fixture(autouse=True)
def _mock_temporal_workflow() -> Generator[MagicMock]:
    """Mock the Temporal workflow module to avoid 'Not in workflow event loop' errors."""
    mock_logger = MagicMock()
    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
        mock_wf.logger = mock_logger
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id")
        mock_wf.execute_activity = AsyncMock(return_value={"output": {}})
        yield mock_wf


def _make_workflow(
    skipped_nodes: set[str] | None = None,
    failed_nodes: dict[str, str] | None = None,
    resolver: NamespaceResolver | None = None,
) -> NexusWorkflow:
    """Create a NexusWorkflow with initialized state, bypassing __init__."""
    wf = NexusWorkflow.__new__(NexusWorkflow)
    wf.skipped_nodes = skipped_nodes if skipped_nodes is not None else set()
    wf.failed_nodes = failed_nodes if failed_nodes is not None else {}
    wf.resolver = resolver if resolver is not None else NamespaceResolver()
    wf.node_inputs = {}
    wf.node_control_data = {}
    wf.loop_state = {}
    wf.loop_body_map = {}
    wf.loop_iteration_results = {}
    wf._timeout_tasks = {}
    wf._timed_out_converge_nodes = set()
    wf._detached_nodes = set()
    wf._converge_branch_nodes = {}
    init_workflow_runtime(wf)
    wf.execution_id = "test-execution-id"
    wf._created_by_user_id = ""
    wf.request_id = None
    wf.pre_resolved_outputs = {}
    wf.stop_after_nodes = set()
    return wf


def _build_diamond_graph() -> WorkflowGraph:
    """Build: trigger -> A + B -> C (diamond, C has two predecessors)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
    backend.add_node("node_b", {"id": "node_b", "type": "script", "parameters": {}})
    backend.add_node("node_c", {"id": "node_c", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "node_a", None)
    backend.add_edge("trigger", "node_b", None)
    backend.add_edge("node_a", "node_c", None)
    backend.add_edge("node_b", "node_c", None)
    return WorkflowGraph(backend)


def _build_chain_graph() -> WorkflowGraph:
    """Build: trigger -> A -> B -> C (three-node chain)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
    backend.add_node("node_b", {"id": "node_b", "type": "script", "parameters": {}})
    backend.add_node("node_c", {"id": "node_c", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "node_a", None)
    backend.add_edge("node_a", "node_b", None)
    backend.add_edge("node_b", "node_c", None)
    return WorkflowGraph(backend)


class TestIsUnreachable:
    """Test transitive unreachability detection."""

    def test_trigger_node_is_always_reachable(self) -> None:
        """Root nodes (no predecessors) are never unreachable."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        graph = WorkflowGraph(backend)
        wf = _make_workflow()

        assert wf._is_unreachable("trigger", graph) is False

    def test_node_with_completed_predecessor_is_reachable(self) -> None:
        """A node whose predecessor completed is reachable."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
        backend.add_edge("trigger", "node_a", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        wf.resolver.set_namespace("trigger", {"done": True})

        assert wf._is_unreachable("node_a", graph) is False

    def test_node_with_all_predecessors_skipped_is_unreachable(self) -> None:
        """A node is unreachable when all predecessors are skipped."""
        graph = _build_diamond_graph()
        wf = _make_workflow(skipped_nodes={"node_a", "node_b"})

        assert wf._is_unreachable("node_c", graph) is True

    def test_node_with_one_predecessor_skipped_one_completed_is_reachable(self) -> None:
        """A node is reachable if any predecessor completed."""
        graph = _build_diamond_graph()
        wf = _make_workflow(skipped_nodes={"node_a"})
        wf.resolver.set_namespace("node_b", {"result": "ok"})

        assert wf._is_unreachable("node_c", graph) is False

    def test_transitive_unreachability_through_chain(self) -> None:
        """A node is unreachable if its predecessor is transitively unreachable."""
        graph = _build_chain_graph()
        wf = _make_workflow(skipped_nodes={"node_a"})

        assert wf._is_unreachable("node_b", graph) is True
        assert wf._is_unreachable("node_c", graph) is True

    def test_already_skipped_node_is_unreachable(self) -> None:
        """Nodes already in skipped_nodes return True."""
        graph = _build_chain_graph()
        wf = _make_workflow(skipped_nodes={"node_b"})

        assert wf._is_unreachable("node_b", graph) is True

    def test_failed_node_is_unreachable(self) -> None:
        """Nodes in failed_nodes return True."""
        graph = _build_chain_graph()
        wf = _make_workflow(failed_nodes={"node_a": "Error"})

        assert wf._is_unreachable("node_a", graph) is True

    def test_node_with_failed_predecessor_is_unreachable(self) -> None:
        """A node whose only predecessor failed is unreachable.

        node_a has a namespace but IS in failed_nodes, so it doesn't
        count as completed successfully.
        """
        graph = _build_chain_graph()
        wf = _make_workflow(failed_nodes={"node_a": "Error"})
        wf.resolver.set_namespace("node_a", {"status": "failed", "error": "Error"})

        assert wf._is_unreachable("node_b", graph) is True


class TestExecuteExecutorNodeUnknownType:
    """Test the executor fallback for unknown node types."""

    @pytest.mark.asyncio
    async def test_unknown_executor_type_returns_skipped(self) -> None:
        """An unknown executor type should return a skipped result."""
        wf = _make_workflow()
        node = ActivityNode("bad_node", "totally_unknown", {})
        result = await wf._execute_executor_node(
            node=node,
            node_type="totally_unknown",
            resolved_parameters={"some": "parameters"},
            outputs=None,
            timeout_seconds=30,
        )
        assert result["output"]["status"] == "skipped"
        assert "Unknown executor type" in result["output"]["reason"]
        assert "totally_unknown" in result["output"]["reason"]


class TestMarkDownstreamEdgeCases:
    """Additional edge cases for downstream skipping."""

    def test_already_completed_successor_not_marked_skipped(self) -> None:
        """A successor that already has output should not be re-marked as skipped."""
        graph = _build_chain_graph()
        wf = _make_workflow(skipped_nodes={"node_a"})
        wf.resolver.set_namespace("node_b", {"result": "done"})

        wf._mark_downstream_as_skipped("node_a", graph)

        assert "node_b" not in wf.skipped_nodes

    def test_already_skipped_successor_not_re_processed(self) -> None:
        """A successor already in skipped_nodes should not be processed again."""
        graph = _build_chain_graph()
        wf = _make_workflow(skipped_nodes={"node_a", "node_b"})

        wf._mark_downstream_as_skipped("node_a", graph)

        assert "node_b" in wf.skipped_nodes

    def test_diamond_skip_only_when_all_predecessors_skipped(self) -> None:
        """In a diamond, a node is only skipped if ALL predecessors are skipped/failed."""
        graph = _build_diamond_graph()
        wf = _make_workflow(skipped_nodes={"node_a"})

        wf._mark_downstream_as_skipped("node_a", graph)

        assert "node_c" not in wf.skipped_nodes

    def test_diamond_skip_when_all_predecessors_failed_or_skipped(self) -> None:
        """In a diamond, node is skipped when preds are a mix of skipped and failed."""
        graph = _build_diamond_graph()
        wf = _make_workflow(skipped_nodes={"node_a"}, failed_nodes={"node_b": "Error"})

        wf._mark_downstream_as_skipped("node_a", graph)

        assert "node_c" in wf.skipped_nodes


class TestMarkRemainingUnreachableNodes:
    """Test the final-pass cleanup of unreachable nodes."""

    def test_unexecuted_nodes_marked_skipped_in_final_pass(self) -> None:
        """Nodes that never executed should be marked as skipped."""
        graph = _build_chain_graph()
        wf = _make_workflow()
        wf.resolver.set_namespace("trigger", {})
        wf.resolver.set_namespace("node_a", {"result": "ok"})

        wf._mark_remaining_unreachable_nodes(graph)

        assert "node_b" in wf.skipped_nodes
        assert "node_c" in wf.skipped_nodes

    def test_already_completed_nodes_not_marked_skipped(self) -> None:
        """Already-executed nodes should not be marked skipped."""
        graph = _build_chain_graph()
        wf = _make_workflow()
        wf.resolver.set_namespace("trigger", {})
        wf.resolver.set_namespace("node_a", {"result": "ok"})
        wf.resolver.set_namespace("node_b", {"result": "ok"})
        wf.resolver.set_namespace("node_c", {"result": "ok"})

        wf._mark_remaining_unreachable_nodes(graph)

        assert "node_a" not in wf.skipped_nodes
        assert "node_b" not in wf.skipped_nodes
        assert "node_c" not in wf.skipped_nodes

    def test_trigger_not_marked_skipped(self) -> None:
        """Trigger nodes (manual_trigger type) are excluded from the final pass."""
        graph = _build_chain_graph()
        wf = _make_workflow()

        wf._mark_remaining_unreachable_nodes(graph)

        assert "trigger" not in wf.skipped_nodes
        assert "node_a" in wf.skipped_nodes

    def test_non_manual_trigger_types_not_marked_skipped(self) -> None:
        """All trigger types (webhook_trigger, schedule_trigger, etc.) are excluded."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "webhook_trigger", "parameters": {}})
        backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
        backend.add_node("node_b", {"id": "node_b", "type": "script", "parameters": {}})
        backend.add_edge("trigger", "node_a", None)
        backend.add_edge("node_a", "node_b", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        wf.resolver.set_namespace("trigger", {})
        wf.resolver.set_namespace("node_a", {"result": "ok"})
        wf.resolver.set_namespace("node_b", {"result": "ok"})

        wf._mark_remaining_unreachable_nodes(graph)

        assert "trigger" not in wf.skipped_nodes
        assert "node_a" not in wf.skipped_nodes
        assert "node_b" not in wf.skipped_nodes


class TestUnselectedTriggerSkipping:
    """Tests for marking unselected triggers and their downstream nodes as skipped."""

    @pytest.fixture(autouse=True)
    def _async_execute_activity(self, _mock_temporal_workflow: MagicMock) -> None:
        """Make workflow.execute_activity awaitable for trigger execution tests."""
        _mock_temporal_workflow.execute_activity = AsyncMock(return_value={"output": {"status": "ok"}})

    @pytest.mark.asyncio
    async def test_unselected_triggers_marked_skipped(self) -> None:
        """Unselected trigger nodes are added to skipped_nodes."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger_a", {"id": "trigger_a", "type": "manual_trigger", "parameters": {}})
        backend.add_node("trigger_b", {"id": "trigger_b", "type": "manual_trigger", "parameters": {}})
        backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
        backend.add_node("node_b", {"id": "node_b", "type": "script", "parameters": {}})
        backend.add_edge("trigger_a", "node_a", None)
        backend.add_edge("trigger_b", "node_b", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        await wf._execute_trigger(
            trigger_node_id="trigger_a",
            trigger_inputs={"key": "value"},
            graph=graph,
            pending_tasks={},
        )

        assert "trigger_b" in wf.skipped_nodes
        assert "trigger_a" not in wf.skipped_nodes

    @pytest.mark.asyncio
    async def test_exclusive_downstream_of_unselected_trigger_skipped(self) -> None:
        """Downstream nodes exclusive to an unselected trigger are skipped."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger_a", {"id": "trigger_a", "type": "manual_trigger", "parameters": {}})
        backend.add_node("trigger_b", {"id": "trigger_b", "type": "manual_trigger", "parameters": {}})
        backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
        backend.add_node("exclusive_b", {"id": "exclusive_b", "type": "script", "parameters": {}})
        backend.add_edge("trigger_a", "node_a", None)
        backend.add_edge("trigger_b", "exclusive_b", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        await wf._execute_trigger(
            trigger_node_id="trigger_a",
            trigger_inputs={},
            graph=graph,
            pending_tasks={},
        )

        assert "trigger_b" in wf.skipped_nodes
        assert "exclusive_b" in wf.skipped_nodes

    @pytest.mark.asyncio
    async def test_shared_downstream_not_skipped(self) -> None:
        """Nodes reachable from the active trigger are NOT skipped."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger_a", {"id": "trigger_a", "type": "manual_trigger", "parameters": {}})
        backend.add_node("trigger_b", {"id": "trigger_b", "type": "manual_trigger", "parameters": {}})
        backend.add_node("shared_node", {"id": "shared_node", "type": "script", "parameters": {}})
        backend.add_edge("trigger_a", "shared_node", None)
        backend.add_edge("trigger_b", "shared_node", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        await wf._execute_trigger(
            trigger_node_id="trigger_a",
            trigger_inputs={},
            graph=graph,
            pending_tasks={},
        )

        assert "trigger_b" in wf.skipped_nodes
        assert "shared_node" not in wf.skipped_nodes

    @pytest.mark.asyncio
    async def test_single_trigger_no_skipping(self) -> None:
        """With only one trigger, nothing is skipped."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
        backend.add_edge("trigger", "node_a", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        await wf._execute_trigger(
            trigger_node_id="trigger",
            trigger_inputs={},
            graph=graph,
            pending_tasks={},
        )

        assert len(wf.skipped_nodes) == 0


class TestAllowedTriggerTypes:
    """Tests for trigger type allowlist security control."""

    @pytest.mark.asyncio
    async def test_invalid_trigger_type_raises_safe_value_error(self) -> None:
        """Trigger type not in ALLOWED_TRIGGER_TYPES raises SafeValueError."""
        backend = InMemoryGraphBackend()
        backend.add_node(
            "trigger",
            {"id": "trigger", "type": "malicious_trigger", "parameters": {}},
        )
        backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
        backend.add_edge("trigger", "node_a", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        with pytest.raises(SafeValueError, match="Invalid trigger type"):
            await wf._execute_trigger(
                trigger_node_id="trigger",
                trigger_inputs={},
                graph=graph,
                pending_tasks={},
            )

    @pytest.mark.asyncio
    async def test_three_triggers_only_selected_runs(self) -> None:
        """With 3 triggers, all non-selected triggers and their exclusive downstream are skipped."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger_a", {"id": "trigger_a", "type": "manual_trigger", "parameters": {}})
        backend.add_node("trigger_b", {"id": "trigger_b", "type": "manual_trigger", "parameters": {}})
        backend.add_node("trigger_c", {"id": "trigger_c", "type": "manual_trigger", "parameters": {}})
        backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
        backend.add_node("exclusive_b", {"id": "exclusive_b", "type": "script", "parameters": {}})
        backend.add_node("exclusive_c", {"id": "exclusive_c", "type": "script", "parameters": {}})
        backend.add_node("shared_bc", {"id": "shared_bc", "type": "script", "parameters": {}})
        backend.add_edge("trigger_a", "node_a", None)
        backend.add_edge("trigger_b", "exclusive_b", None)
        backend.add_edge("trigger_b", "shared_bc", None)
        backend.add_edge("trigger_c", "exclusive_c", None)
        backend.add_edge("trigger_c", "shared_bc", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        await wf._execute_trigger(
            trigger_node_id="trigger_a",
            trigger_inputs={},
            graph=graph,
            pending_tasks={},
        )

        assert "trigger_b" in wf.skipped_nodes
        assert "trigger_c" in wf.skipped_nodes
        assert "exclusive_b" in wf.skipped_nodes
        assert "exclusive_c" in wf.skipped_nodes
        # shared_bc has ALL predecessors (trigger_b, trigger_c) skipped, so it is also skipped
        assert "shared_bc" in wf.skipped_nodes
        assert "trigger_a" not in wf.skipped_nodes
        assert "node_a" not in wf.skipped_nodes

    @pytest.mark.asyncio
    async def test_allowed_trigger_types_contains_expected_entries(self) -> None:
        """ALLOWED_TRIGGER_TYPES matches the expected trigger activity set."""
        assert {
            ActivityName.MANUAL_TRIGGER,
            ActivityName.EDA_TRIGGER,
            ActivityName.SCHEDULED_TRIGGER,
            ActivityName.WEBHOOK_TRIGGER,
        } == ALLOWED_TRIGGER_TYPES


class TestLoopBodyCompleteEdgeCases:
    """Additional edge cases for loop body completion checks."""

    def test_empty_loop_body_returns_false(self) -> None:
        """A loop with no body nodes mapped should return False."""
        wf = _make_workflow()
        assert wf._loop_body_complete("nonexistent_loop") is False

    def test_nested_loop_still_iterating_blocks_parent(self) -> None:
        """If a body node is a loop still iterating, parent body is NOT complete."""
        wf = _make_workflow()
        wf.loop_body_map["inner_loop"] = "outer_loop"
        wf.resolver.set_namespace("inner_loop", {"status": "iterating"})
        wf.node_control_data["inner_loop"] = {"next_port": "iterate"}

        assert wf._loop_body_complete("outer_loop") is False

    def test_nested_loop_completed_allows_parent(self) -> None:
        """If a body node routed to 'complete', parent body IS complete."""
        wf = _make_workflow()
        wf.loop_body_map["inner_loop"] = "outer_loop"
        wf.resolver.set_namespace("inner_loop", {"status": "done"})
        wf.node_control_data["inner_loop"] = {"next_port": "complete"}

        assert wf._loop_body_complete("outer_loop") is True


class TestClearLoopBodyEdgeCases:
    """Additional edge cases for clearing loop body state."""

    def test_clear_loop_body_with_non_dict_result_does_not_crash(self) -> None:
        """Non-dict namespace results should not crash _clear_loop_body."""
        wf = _make_workflow()
        wf.loop_body_map["body_node"] = "loop_1"
        # Directly set a non-dict value in the resolver's internal storage
        wf.resolver.namespaces["body_node"] = "raw_string_result"  # type: ignore[assignment]

        wf._clear_loop_body("loop_1")

        assert "body_node" not in wf.loop_body_map
        assert wf.loop_iteration_results.get("loop_1") == {}

    def test_multiple_iterations_accumulate_results(self) -> None:
        """Calling _clear_loop_body multiple times should accumulate results."""
        wf = _make_workflow()

        wf.loop_body_map["body_node"] = "loop_1"
        wf.resolver.set_namespace("body_node", {"value": 10})
        wf._clear_loop_body("loop_1")

        wf.loop_body_map["body_node"] = "loop_1"
        wf.resolver.set_namespace("body_node", {"value": 20})
        wf._clear_loop_body("loop_1")

        wf.loop_body_map["body_node"] = "loop_1"
        wf.resolver.set_namespace("body_node", {"value": 30})
        wf._clear_loop_body("loop_1")

        assert wf.loop_iteration_results["loop_1"]["body_node.value"] == [10, 20, 30]

    def test_clear_loop_body_with_multiple_body_nodes(self) -> None:
        """All body nodes mapped to the same loop should be cleared."""
        wf = _make_workflow()
        wf.loop_body_map["body_a"] = "loop_1"
        wf.loop_body_map["body_b"] = "loop_1"
        wf.loop_body_map["unrelated"] = "loop_2"
        wf.resolver.set_namespace("body_a", {"x": 1})
        wf.resolver.set_namespace("body_b", {"y": 2})

        wf._clear_loop_body("loop_1")

        assert "body_a" not in wf.loop_body_map
        assert "body_b" not in wf.loop_body_map
        assert "unrelated" in wf.loop_body_map
        assert wf.loop_iteration_results["loop_1"]["body_a.x"] == [1]
        assert wf.loop_iteration_results["loop_1"]["body_b.y"] == [2]


class TestScheduleSuccessorsSkipBehavior:
    """Test that _schedule_successors respects pending state."""

    def test_already_executed_node_not_rescheduled(self) -> None:
        """A successor that already has output should not be re-scheduled."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
        backend.add_edge("trigger", "node_a", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        wf.resolver.set_namespace("trigger", {})
        wf.resolver.set_namespace("node_a", {"result": "already done"})
        pending: dict[str, asyncio.Task[Any]] = {}

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(wf._schedule_successors("trigger", graph, pending))
        finally:
            for task in pending.values():
                task.cancel()
            loop.close()

        assert "node_a" not in pending


class TestGetSkippedNodesQuerySupplementary:
    """Supplementary tests for get_skipped_nodes behavior."""

    def test_returns_failed_downstream_as_skipped(self) -> None:
        """Nodes marked skipped due to upstream failure should appear in query."""
        graph = _build_chain_graph()
        wf = _make_workflow(failed_nodes={"node_a": "Error"})
        wf._mark_downstream_as_skipped("node_a", graph)

        skipped = wf.get_skipped_nodes()
        assert "node_b" in skipped
        assert "node_c" in skipped
        assert "node_a" not in skipped

    def test_empty_state_returns_empty_list(self) -> None:
        """Fresh workflow with no skips returns empty list."""
        wf = _make_workflow()
        assert wf.get_skipped_nodes() == []

    def test_single_skipped_node(self) -> None:
        """Single skipped node returns that node."""
        wf = _make_workflow(skipped_nodes={"only_node"})
        assert wf.get_skipped_nodes() == ["only_node"]


class TestGetActivityInputEdgeCases:
    """Additional edge cases for get_activity_input."""

    def test_returns_empty_dict_input(self) -> None:
        """An activity with empty dict input should return empty dict, not None."""
        wf = _make_workflow()
        wf.node_inputs["node_a"] = {}
        assert wf.get_activity_input("node_a") == {}

    def test_multiple_activities_independent(self) -> None:
        """Different activities have independent inputs."""
        wf = _make_workflow()
        wf.node_inputs["node_a"] = {"url": "http://a.com"}
        wf.node_inputs["node_b"] = {"url": "http://b.com"}

        assert wf.get_activity_input("node_a") == {"url": "http://a.com"}
        assert wf.get_activity_input("node_b") == {"url": "http://b.com"}


class TestGetActivityOutputEdgeCases:
    """Additional edge cases for get_activity_output."""

    def test_returns_empty_dict_output(self) -> None:
        """An activity with empty dict output should return empty dict, not None."""
        wf = _make_workflow()
        wf.resolver.set_namespace("node_a", {})
        assert wf.get_activity_output("node_a") == {}

    def test_output_reflects_latest_namespace_value(self) -> None:
        """Output should reflect the latest value set in the namespace."""
        wf = _make_workflow()
        wf.resolver.set_namespace("node_a", {"version": 1})
        wf.resolver.set_namespace("node_a", {"version": 2})
        result = wf.get_activity_output("node_a")
        assert result is not None
        assert result["version"] == 2


_TEMPORAL_MARGIN = NexusWorkflow._TEMPORAL_MARGIN


class TestPerNodeTimeout:
    """Test that settings.timeout overrides the per-type catalog default."""

    @pytest.mark.asyncio
    async def test_custom_timeout_passed_to_executor_node(
        self,
        _mock_temporal_workflow: MagicMock,  # noqa: PT019
    ) -> None:
        """settings.timeout=60 on a script node → Temporal gets 60 + margin."""
        _mock_temporal_workflow.execute_activity = AsyncMock(return_value={"output": {"result": "ok"}})

        wf = _make_workflow()
        node = ActivityNode(
            node_id="node_custom",
            node_type="script",
            parameters={"script": "echo hello"},
            settings=NodeSettingsNoRetry(timeout=60),
        )
        graph = _build_chain_graph()

        await wf._execute_node(node=node, graph=graph)

        _mock_temporal_workflow.execute_activity.assert_called_once()
        call_kwargs = _mock_temporal_workflow.execute_activity.call_args
        assert call_kwargs.kwargs["start_to_close_timeout"] == timedelta(seconds=60 + _TEMPORAL_MARGIN)

    @pytest.mark.asyncio
    async def test_default_timeout_used_when_not_specified(
        self,
        _mock_temporal_workflow: MagicMock,  # noqa: PT019
    ) -> None:
        """Script node with no settings.timeout → catalog default + margin."""
        _mock_temporal_workflow.execute_activity = AsyncMock(return_value={"output": {"result": "ok"}})

        wf = _make_workflow()
        node = ActivityNode(node_id="node_default", node_type="script", parameters={"script": "echo hello"})
        graph = _build_chain_graph()

        await wf._execute_node(node=node, graph=graph)

        _mock_temporal_workflow.execute_activity.assert_called_once()
        call_kwargs = _mock_temporal_workflow.execute_activity.call_args
        expected = get_default_timeout(NodeType.SCRIPT, wf._runtime_settings) + _TEMPORAL_MARGIN
        assert call_kwargs.kwargs["start_to_close_timeout"] == timedelta(seconds=expected)

    @pytest.mark.asyncio
    async def test_timeout_preserved_in_config_for_activity(
        self,
        _mock_temporal_workflow: MagicMock,  # noqa: PT019
    ) -> None:
        """The timeout key should remain in resolved_parameters (not popped)."""
        _mock_temporal_workflow.execute_activity = AsyncMock(return_value={"output": {"result": "ok"}})

        wf = _make_workflow()
        node = ActivityNode(node_id="node_keep", node_type="script", parameters={"timeout": 90, "script": "echo hello"})
        graph = _build_chain_graph()

        await wf._execute_node(node=node, graph=graph)

        # Verify timeout is still in the stored node_inputs (config wasn't mutated)
        assert wf.node_inputs["node_keep"]["timeout"] == 90

    @pytest.mark.asyncio
    async def test_aap_job_template_uses_aap_default_timeout(
        self,
        _mock_temporal_workflow: MagicMock,  # noqa: PT019
    ) -> None:
        """AAP node with no settings.timeout → catalog default + margin."""
        _mock_temporal_workflow.execute_activity = AsyncMock(return_value={"output": {"result": "ok"}})

        wf = _make_workflow()
        node = ActivityNode(node_id="launch_job", node_type="aap_job_template", parameters={"job_template_id": 6})
        graph = _build_chain_graph()

        await wf._execute_node(node=node, graph=graph)

        _mock_temporal_workflow.execute_activity.assert_called_once()
        call_kwargs = _mock_temporal_workflow.execute_activity.call_args
        expected = get_default_timeout(NodeType.AAP_JOB_TEMPLATE, wf._runtime_settings) + _TEMPORAL_MARGIN
        assert call_kwargs.kwargs["start_to_close_timeout"] == timedelta(seconds=expected)


class TestLoopMaxIterationsEnforcement:
    """max_iterations raises ApplicationError in the workflow before the activity is called.

    Node config takes priority over the runtime setting. Both for_each and do_while
    raise ApplicationError (MaxIterationsError) — do_while only when the condition is
    still True (loop wants to keep running), not on a natural condition=False exit.
    """

    @pytest.mark.asyncio
    async def test_for_each_raises_when_node_config_max_iterations_exceeded(self) -> None:
        wf = _make_workflow()
        node = ActivityNode(
            node_id="loop_1",
            node_type="loop",
            parameters={"type": "for_each", "items": ["a", "b", "c"], "max_iterations": 2},
        )
        wf.loop_state["loop_1"] = ForEachLoopState(items=["a", "b", "c"], current_index=2)
        wf.loop_iteration_results["loop_1"] = {}

        with pytest.raises(ApplicationError) as exc_info:
            await wf._execute_loop_node("loop_1", node, node.parameters)

        assert exc_info.value.type == "MaxIterationsError"
        assert "exceeded max_iterations (2)" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_for_each_raises_using_runtime_setting_when_no_node_config(self) -> None:
        wf = _make_workflow()
        wf._runtime_settings["workflow_engine.max_loop_iterations"] = 3
        node = ActivityNode(
            node_id="loop_1",
            node_type="loop",
            parameters={"type": "for_each", "items": ["a", "b", "c", "d"]},
        )
        wf.loop_state["loop_1"] = ForEachLoopState(items=["a", "b", "c", "d"], current_index=3)
        wf.loop_iteration_results["loop_1"] = {}

        with pytest.raises(ApplicationError) as exc_info:
            await wf._execute_loop_node("loop_1", node, node.parameters)

        assert exc_info.value.type == "MaxIterationsError"
        assert "exceeded max_iterations (3)" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_do_while_raises_when_condition_true_and_max_iterations_exceeded(self) -> None:
        wf = _make_workflow()
        node = ActivityNode(
            node_id="loop_1",
            node_type="loop",
            parameters={"type": "do_while", "condition": "${converged}", "max_iterations": 5},
        )
        wf.loop_state["loop_1"] = DoWhileLoopState(condition="${converged}", max_iterations=5, current_index=5)
        wf.loop_iteration_results["loop_1"] = {}

        with (
            patch(
                "syntara.workflows.workflow_engine.dynamic_workflow.safe_eval_with_namespace",
                return_value=True,
            ),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await wf._execute_loop_node("loop_1", node, node.parameters)

        assert exc_info.value.type == "MaxIterationsError"
        assert "exceeded max_iterations (5)" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_do_while_does_not_raise_when_condition_false_at_max_iterations(
        self,
        _mock_temporal_workflow: MagicMock,  # noqa: PT019
    ) -> None:
        """Condition became False exactly at max_iterations — natural exit, not an error."""
        _mock_temporal_workflow.execute_activity = AsyncMock(
            return_value={"output": {}, "control": {"next_port": "complete", "next_index": 5}}
        )
        wf = _make_workflow()
        node = ActivityNode(
            node_id="loop_1",
            node_type="loop",
            parameters={"type": "do_while", "condition": "${converged}", "max_iterations": 5},
        )
        wf.loop_state["loop_1"] = DoWhileLoopState(condition="${converged}", max_iterations=5, current_index=5)
        wf.loop_iteration_results["loop_1"] = {}

        with patch(
            "syntara.workflows.workflow_engine.dynamic_workflow.safe_eval_with_namespace",
            return_value=False,
        ):
            result = await wf._execute_loop_node("loop_1", node, node.parameters)

        assert result["control"]["next_port"] == "complete"


class TestResolveAndInjectUniqueActivityIds:
    """Credential and integration resolution must use per-node activity IDs.

    When two AAP nodes fan out in parallel from the same predecessor, both call
    _resolve_and_inject_credentials / _resolve_and_inject_integration concurrently.
    Temporal requires activity IDs to be unique within a workflow execution, so
    hardcoded IDs cause a collision that silently blocks the second node.
    """

    @pytest.mark.asyncio
    async def test_credential_resolution_uses_node_specific_activity_id(
        self,
        _mock_temporal_workflow: MagicMock,  # noqa: PT019
    ) -> None:
        """Each credential resolution call must include the node ID in its activity_id."""
        _mock_temporal_workflow.execute_activity = AsyncMock(return_value={"node_a": {"token": "t"}})

        wf = _make_workflow()
        wf._project_id = "proj-1"
        wf._secret_values = set()
        node = ActivityNode("node_a", "aap_job_template", {"credential_id": "cred-1"})

        await wf._resolve_and_inject_credentials(node, dict(node.parameters))

        call_kwargs = _mock_temporal_workflow.execute_activity.call_args
        assert call_kwargs.kwargs["activity_id"] == "__internal__resolve_credentials_node_a"

    @pytest.mark.asyncio
    async def test_integration_resolution_uses_node_specific_activity_id(
        self,
        _mock_temporal_workflow: MagicMock,  # noqa: PT019
    ) -> None:
        """Each integration resolution call must include the node ID in its activity_id."""
        _mock_temporal_workflow.execute_activity = AsyncMock(
            return_value={"base_url": "https://aap.example.com", "verify_ssl": True}
        )

        wf = _make_workflow()
        node = ActivityNode("node_b", "aap_job_template", {"integration_id": "int-1"})

        await wf._resolve_and_inject_integration(node, dict(node.parameters))

        call_kwargs = _mock_temporal_workflow.execute_activity.call_args
        assert call_kwargs.kwargs["activity_id"] == "__internal__resolve_integration_node_b"

    @pytest.mark.asyncio
    async def test_parallel_aap_nodes_get_distinct_credential_activity_ids(
        self,
        _mock_temporal_workflow: MagicMock,  # noqa: PT019
    ) -> None:
        """Two concurrent AAP nodes must not collide on credential activity IDs."""
        _mock_temporal_workflow.execute_activity = AsyncMock(
            side_effect=[
                {"aap_1": {"token": "t1"}},
                {"aap_2": {"token": "t2"}},
            ]
        )

        wf = _make_workflow()
        wf._project_id = "proj-1"
        wf._secret_values = set()

        node_1 = ActivityNode("aap_1", "aap_job_template", {"credential_id": "cred-1"})
        node_2 = ActivityNode("aap_2", "aap_job_template", {"credential_id": "cred-2"})

        await asyncio.gather(
            wf._resolve_and_inject_credentials(node_1, dict(node_1.parameters)),
            wf._resolve_and_inject_credentials(node_2, dict(node_2.parameters)),
        )

        activity_ids = [call.kwargs["activity_id"] for call in _mock_temporal_workflow.execute_activity.call_args_list]
        assert "__internal__resolve_credentials_aap_1" in activity_ids
        assert "__internal__resolve_credentials_aap_2" in activity_ids
        assert len(set(activity_ids)) == 2
