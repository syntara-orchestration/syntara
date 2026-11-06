"""Supplementary tests for OrchestratorWorkflow execution engine (task 6.3 — TEST).

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
from syntara.workflows.workflow_engine.constants import INTERNAL_ACTIVITY_HEARTBEAT_TIMEOUT_SECONDS
from syntara.workflows.workflow_engine.dynamic_workflow import (
    ALLOWED_TRIGGER_TYPES,
    OrchestratorWorkflow,
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
) -> OrchestratorWorkflow:
    """Create an OrchestratorWorkflow with initialized state, bypassing __init__."""
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
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
    wf._cof_failed_nodes = set()
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


class TestExecuteExecutorNodeHeartbeatTimeout:
    """Internal activities must be scheduled with a heartbeat_timeout.

    Temporal delivers activity cancellation only through heartbeats, and only when
    the schedule carries a heartbeat_timeout -- without one the beats are dropped
    and cancelling the workflow leaves the agent run executing until
    start_to_close_timeout. Ref: AAP-88614.
    """

    @staticmethod
    async def _schedule(node_type: str) -> dict[str, Any]:
        wf = _make_workflow()
        node = ActivityNode("n1", node_type, {})
        with (
            patch(
                "syntara.workflows.workflow_engine.dynamic_workflow.workflow.execute_activity",
                new=AsyncMock(return_value={"output": {}}),
            ) as mock_exec,
            patch(
                "syntara.workflows.workflow_engine.dynamic_workflow.resolve_retry_policy",
                return_value=None,
            ),
        ):
            await wf._execute_executor_node(
                node=node,
                node_type=node_type,
                resolved_parameters={},
                outputs=None,
                timeout_seconds=3600,
            )
        assert mock_exec.await_args is not None, "the activity should have been scheduled"
        return dict(mock_exec.await_args.kwargs)

    @pytest.mark.asyncio
    async def test_internal_activity_gets_a_heartbeat_timeout(self) -> None:
        """Without this the heartbeat loop is inert and a cancel never reaches the agent."""
        kwargs = await self._schedule(NodeType.INTERNAL_ACTIVITY)
        assert kwargs["heartbeat_timeout"] == timedelta(seconds=INTERNAL_ACTIVITY_HEARTBEAT_TIMEOUT_SECONDS)

    @pytest.mark.asyncio
    async def test_non_heartbeating_executors_get_no_heartbeat_timeout(self) -> None:
        """The other executor activities never beat; a timeout would fail them spuriously."""
        for node_type in (NodeType.HTTP_REQUEST, NodeType.SCRIPT, NodeType.AGENTIC):
            kwargs = await self._schedule(node_type)
            assert kwargs["heartbeat_timeout"] is None, f"{node_type} must not get a heartbeat timeout"


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

    @pytest.mark.asyncio
    async def test_trigger_payload_not_registered_as_input_aliases(self) -> None:
        """${input.*} and ${inputs.*} are not registered unless a node uses that id."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
        backend.add_edge("trigger", "node_a", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        with patch(
            "syntara.workflows.workflow_engine.dynamic_workflow.workflow.execute_activity",
            new_callable=AsyncMock,
            return_value={"output": {"env": "prod"}},
        ):
            await wf._execute_trigger(
                trigger_node_id="trigger",
                trigger_inputs={"env": "prod"},
                graph=graph,
                pending_tasks={},
            )

        assert wf.resolver.resolve_value("${trigger.env}") == "prod"
        with pytest.raises(KeyError, match="input"):
            wf.resolver.resolve_value("${input.env}")
        with pytest.raises(KeyError, match="inputs"):
            wf.resolver.resolve_value("${inputs.env}")


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


class TestCheckLoopBodyCompletionGuard:
    """Failed parent loops must not be re-iterated.

    When a loop body has parallel nodes and one fails, _propagate_loop_body_failure
    marks the parent loop as failed and schedules its successors. However the body
    entries remain in loop_body_map. If the other parallel body node completes
    afterward, _check_loop_body_completion must NOT re-execute the loop.
    """

    def test_failed_parent_loop_not_reiterated(self) -> None:
        """Completing a sibling body node after another failed must not re-execute the loop."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node(
            "loop_node",
            {"id": "loop_node", "type": "loop", "parameters": {"type": "for_each", "items": ["a"]}},
        )
        backend.add_node("body_a", {"id": "body_a", "type": "script", "parameters": {}})
        backend.add_node("body_b", {"id": "body_b", "type": "script", "parameters": {}})
        backend.add_edge("trigger", "loop_node")
        backend.add_edge("loop_node", "body_a", {"from_port": "iterate"})
        backend.add_edge("loop_node", "body_b", {"from_port": "iterate"})
        backend.add_edge("body_a", "loop_node", {"to_port": "iterate"})
        backend.add_edge("body_b", "loop_node", {"to_port": "iterate"})
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        wf.loop_body_map["body_a"] = "loop_node"
        wf.loop_body_map["body_b"] = "loop_node"

        # body_a failed → parent loop marked failed
        wf.failed_nodes["loop_node"] = "Loop body node 'body_a' failed"
        wf.resolver.set_namespace("body_a", {"status": "failed", "error": "boom"})

        # body_b completes afterward — both namespaces now populated
        wf.resolver.set_namespace("body_b", {"status": "completed", "result": "ok"})
        pending: dict[str, asyncio.Task[Any]] = {}

        wf._check_loop_body_completion("body_b", graph, pending)

        assert "loop_node" not in pending, "Failed loop must not be re-executed"

    @pytest.mark.asyncio
    async def test_healthy_loop_still_reiterates(self) -> None:
        """A non-failed loop whose body is complete should still be re-scheduled."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node(
            "loop_node",
            {"id": "loop_node", "type": "loop", "parameters": {"type": "for_each", "items": ["a", "b"]}},
        )
        backend.add_node("body", {"id": "body", "type": "script", "parameters": {}})
        backend.add_edge("trigger", "loop_node")
        backend.add_edge("loop_node", "body", {"from_port": "iterate"})
        backend.add_edge("body", "loop_node", {"to_port": "iterate"})
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        wf.loop_body_map["body"] = "loop_node"
        wf.resolver.set_namespace("body", {"status": "completed"})
        pending: dict[str, asyncio.Task[Any]] = {}

        with patch.object(wf, "_execute_node", new_callable=AsyncMock):
            wf._check_loop_body_completion("body", graph, pending)

        for task in pending.values():
            task.cancel()

        assert "loop_node" in pending, "Healthy loop should be re-scheduled"


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


class TestLoopStillIteratingConverge:
    """A loop routing to 'iterate' must not count as terminal or successful."""

    def test_is_loop_still_iterating_true(self) -> None:
        wf = _make_workflow()
        wf.node_control_data["loop_1"] = {"next_port": "iterate"}
        assert wf._is_loop_still_iterating("loop_1") is True

    def test_is_loop_still_iterating_false_on_complete(self) -> None:
        wf = _make_workflow()
        wf.node_control_data["loop_1"] = {"next_port": "complete"}
        assert wf._is_loop_still_iterating("loop_1") is False

    def test_is_loop_still_iterating_false_no_control_data(self) -> None:
        wf = _make_workflow()
        assert wf._is_loop_still_iterating("node_x") is False

    def test_all_predecessors_terminal_excludes_iterating_loop(self) -> None:
        wf = _make_workflow()
        wf.resolver.set_namespace("loop_1", {"status": "completed"})
        wf.node_control_data["loop_1"] = {"next_port": "iterate"}
        assert wf._all_predecessors_terminal(["loop_1"]) is False

    def test_all_predecessors_terminal_includes_completed_loop(self) -> None:
        wf = _make_workflow()
        wf.resolver.set_namespace("loop_1", {"status": "completed"})
        wf.node_control_data["loop_1"] = {"next_port": "complete"}
        assert wf._all_predecessors_terminal(["loop_1"]) is True

    def test_count_successful_excludes_iterating_loop(self) -> None:
        wf = _make_workflow()
        wf.resolver.set_namespace("loop_1", {"status": "completed"})
        wf.node_control_data["loop_1"] = {"next_port": "iterate"}
        wf.resolver.set_namespace("step_a", {"result": "ok"})
        assert wf._count_successful_predecessors(["loop_1", "step_a"]) == 1

    def test_count_successful_includes_completed_loop(self) -> None:
        wf = _make_workflow()
        wf.resolver.set_namespace("loop_1", {"status": "completed"})
        wf.node_control_data["loop_1"] = {"next_port": "complete"}
        wf.resolver.set_namespace("step_a", {"result": "ok"})
        assert wf._count_successful_predecessors(["loop_1", "step_a"]) == 2


class TestPropagateLoopBodyFailure:
    """Body failure must propagate to parent loop and downstream converge."""

    def test_marks_parent_loop_as_failed(self) -> None:
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node(
            "loop_node", {"id": "loop_node", "type": "loop", "parameters": {"type": "for_each", "items": ["a"]}}
        )
        backend.add_node("body", {"id": "body", "type": "script", "parameters": {}})
        backend.add_node("join", {"id": "join", "type": "converge", "parameters": {}})
        backend.add_edge("trigger", "loop_node")
        backend.add_edge("loop_node", "body", {"from_port": "iterate"})
        backend.add_edge("body", "loop_node", {"to_port": "iterate"})
        backend.add_edge("loop_node", "join", {"from_port": "complete"})
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        wf.loop_body_map["body"] = "loop_node"
        wf.resolver.set_namespace("loop_node", {"status": "completed"})
        wf.node_control_data["loop_node"] = {"next_port": "iterate"}
        wf._build_converge_branch_nodes_index(graph)

        wf._propagate_loop_body_failure("body", graph)

        assert "loop_node" in wf.failed_nodes
        ns = wf.resolver.get_namespace("loop_node")
        assert ns["status"] == "failed"

    def test_no_op_when_node_not_in_loop(self) -> None:
        graph = _build_chain_graph()
        wf = _make_workflow()

        wf._propagate_loop_body_failure("node_a", graph)

        assert not wf.failed_nodes

    def test_no_op_when_loop_already_failed(self) -> None:
        graph = _build_chain_graph()
        wf = _make_workflow(failed_nodes={"loop_1": "already failed"})
        wf.loop_body_map["body"] = "loop_1"

        wf._propagate_loop_body_failure("body", graph)

        assert wf.failed_nodes["loop_1"] == "already failed"

    def test_loop_continue_on_failure_routes_through_cof(self) -> None:
        """Loop with continue_on_failure=True: body failure adds loop to _cof_failed_nodes.

        Verifies that a CoF loop does not break downstream ALL converge nodes.
        """
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node(
            "loop_node",
            {
                "id": "loop_node",
                "type": "loop",
                "parameters": {"type": "for_each", "items": ["a", "b"]},
                "settings": {"continue_on_failure": True},
            },
        )
        backend.add_node("body", {"id": "body", "type": "script", "parameters": {}})
        backend.add_node("other", {"id": "other", "type": "script", "parameters": {}})
        backend.add_node("join", {"id": "join", "type": "converge", "parameters": {"strategy": "all"}})
        backend.add_node("downstream", {"id": "downstream", "type": "script", "parameters": {}})
        backend.add_edge("trigger", "loop_node")
        backend.add_edge("trigger", "other")
        backend.add_edge("loop_node", "body", {"from_port": "iterate"})
        backend.add_edge("body", "loop_node", {"to_port": "iterate"})
        backend.add_edge("loop_node", "join", {"from_port": "complete"})
        backend.add_edge("other", "join")
        backend.add_edge("join", "downstream")
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        wf.loop_body_map["body"] = "loop_node"
        wf.resolver.set_namespace("loop_node", {"status": "completed"})
        wf.node_control_data["loop_node"] = {"next_port": "iterate"}
        wf._build_converge_branch_nodes_index(graph)

        wf._propagate_loop_body_failure("body", graph)

        assert "loop_node" in wf.failed_nodes
        assert "loop_node" in wf._cof_failed_nodes
        assert wf.node_control_data["loop_node"]["next_port"] == "complete"
        assert "loop_node" in wf._timed_out_converge_nodes
        assert wf._has_unhandled_failure is False
        assert "join" not in wf.failed_nodes
        assert "join" not in wf.skipped_nodes
        assert "downstream" not in wf.skipped_nodes


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


_TEMPORAL_MARGIN = OrchestratorWorkflow._TEMPORAL_MARGIN


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


class TestNestedLoopControlActivityId:
    """Inner loop Temporal IDs include enclosing loop indices so IDs are not reused."""

    @pytest.mark.asyncio
    async def test_top_level_loop_uses_single_iter_suffix(
        self,
        _mock_temporal_workflow: MagicMock,  # noqa: PT019
    ) -> None:
        _mock_temporal_workflow.execute_activity = AsyncMock(
            return_value={"output": {}, "control": {"next_port": "iterate", "next_index": 1, "current_index": 0}}
        )
        wf = _make_workflow()
        node = ActivityNode(
            node_id="outer",
            node_type="loop",
            parameters={"type": "for_each", "items": ["a", "b"]},
        )
        wf.loop_state["outer"] = ForEachLoopState(items=["a", "b"], current_index=0)
        wf.loop_iteration_results["outer"] = {}

        await wf._execute_loop_node("outer", node, node.parameters)

        assert _mock_temporal_workflow.execute_activity.call_args.kwargs["activity_id"] == "outer_iter_0"

    @pytest.mark.asyncio
    async def test_nested_inner_loop_includes_outer_index(
        self,
        _mock_temporal_workflow: MagicMock,  # noqa: PT019
    ) -> None:
        _mock_temporal_workflow.execute_activity = AsyncMock(
            return_value={"output": {}, "control": {"next_port": "iterate", "next_index": 1, "current_index": 0}}
        )
        wf = _make_workflow()
        wf.loop_body_map["inner"] = "outer"
        wf.node_control_data["outer"] = {"current_index": 2}
        node = ActivityNode(
            node_id="inner",
            node_type="loop",
            parameters={"type": "for_each", "items": ["x"]},
        )
        wf.loop_state["inner"] = ForEachLoopState(items=["x"], current_index=0)
        wf.loop_iteration_results["inner"] = {}

        await wf._execute_loop_node("inner", node, node.parameters)

        assert _mock_temporal_workflow.execute_activity.call_args.kwargs["activity_id"] == "inner_iter_2_iter_0"

    @pytest.mark.asyncio
    async def test_same_inner_index_next_outer_uses_distinct_activity_id(
        self,
        _mock_temporal_workflow: MagicMock,  # noqa: PT019
    ) -> None:
        _mock_temporal_workflow.execute_activity = AsyncMock(
            return_value={"output": {}, "control": {"next_port": "iterate", "next_index": 1, "current_index": 0}}
        )
        wf = _make_workflow()
        wf.loop_body_map["inner"] = "outer"
        node = ActivityNode(
            node_id="inner",
            node_type="loop",
            parameters={"type": "for_each", "items": ["x"]},
        )
        wf.loop_iteration_results["inner"] = {}

        wf.node_control_data["outer"] = {"current_index": 0}
        wf.loop_state["inner"] = ForEachLoopState(items=["x"], current_index=0)
        await wf._execute_loop_node("inner", node, node.parameters)
        first = _mock_temporal_workflow.execute_activity.call_args.kwargs["activity_id"]

        wf.node_control_data["outer"] = {"current_index": 1}
        wf.loop_state["inner"] = ForEachLoopState(items=["x"], current_index=0)
        await wf._execute_loop_node("inner", node, node.parameters)
        second = _mock_temporal_workflow.execute_activity.call_args.kwargs["activity_id"]

        assert first == "inner_iter_0_iter_0"
        assert second == "inner_iter_1_iter_0"
        assert first != second


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


class TestExtractFailureOutput:
    """Tests for _extract_failure_output — extracts output from ApplicationError or falls back."""

    def test_extracts_output_from_app_error_details(self) -> None:
        """When app_error.details contains an 'output' dict, return it."""
        wf = _make_workflow()
        graph = _build_chain_graph()
        app_error = ApplicationError("boom", {"output": {"response_code": 500, "body": "err"}}, type="TaskError")

        result = wf._extract_failure_output("node_a", app_error, graph)

        assert result == {"response_code": 500, "body": "err"}

    def test_returns_empty_model_when_no_app_error(self) -> None:
        """When app_error is None, fall back to _build_empty_node_output."""
        wf = _make_workflow()
        graph = _build_chain_graph()

        result = wf._extract_failure_output("node_a", None, graph)

        assert isinstance(result, dict)

    def test_returns_empty_model_when_details_lack_output_key(self) -> None:
        """When app_error.details has no 'output' key, fall back to empty model."""
        wf = _make_workflow()
        graph = _build_chain_graph()
        app_error = ApplicationError("boom", {"error": "some error"}, type="TaskError")

        result = wf._extract_failure_output("node_a", app_error, graph)

        assert isinstance(result, dict)
        assert "response_code" not in result


class TestEvaluatePredecessor:
    """Tests for _evaluate_predecessor — all return paths."""

    def test_skipped_predecessor_returns_none(self) -> None:
        wf = _make_workflow(skipped_nodes={"node_a"})
        graph = _build_chain_graph()

        assert wf._evaluate_predecessor("node_a", graph) is None

    def test_cof_failed_predecessor_returns_true(self) -> None:
        wf = _make_workflow(failed_nodes={"node_a": "error"})
        wf._cof_failed_nodes.add("node_a")
        graph = _build_chain_graph()

        assert wf._evaluate_predecessor("node_a", graph) is True

    def test_failed_non_cof_predecessor_returns_none(self) -> None:
        wf = _make_workflow(failed_nodes={"node_a": "error"})
        graph = _build_chain_graph()

        assert wf._evaluate_predecessor("node_a", graph) is None

    def test_completed_predecessor_returns_true(self) -> None:
        wf = _make_workflow()
        wf.resolver.set_namespace("node_a", {"status": "completed"})
        graph = _build_chain_graph()

        assert wf._evaluate_predecessor("node_a", graph) is True

    def test_iterating_loop_predecessor_returns_false(self) -> None:
        wf = _make_workflow()
        wf.resolver.set_namespace("node_a", {"status": "iterating"})
        wf.node_control_data["node_a"] = {"next_port": "iterate"}
        graph = _build_chain_graph()

        assert wf._evaluate_predecessor("node_a", graph) is False

    def test_unreachable_predecessor_marked_skipped_returns_none(self) -> None:
        graph = _build_chain_graph()
        wf = _make_workflow(skipped_nodes={"node_a"})

        result = wf._evaluate_predecessor("node_b", graph)

        assert result is None
        assert "node_b" in wf.skipped_nodes

    def test_pending_predecessor_returns_false(self) -> None:
        wf = _make_workflow()
        graph = _build_chain_graph()
        wf.resolver.set_namespace("trigger", {"status": "completed"})

        assert wf._evaluate_predecessor("node_a", graph) is False


class TestPropagateLoopBodyFailureExtended:
    """Extended coverage: nested recursion and no-namespace edge case."""

    def test_nested_loop_failure_propagates_to_outer_loop(self) -> None:
        """Inner body fails → inner loop marked failed → recursion marks outer loop failed."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node(
            "outer_loop",
            {"id": "outer_loop", "type": "loop", "parameters": {"type": "for_each", "items": ["a"]}},
        )
        backend.add_node(
            "inner_loop",
            {"id": "inner_loop", "type": "loop", "parameters": {"type": "for_each", "items": ["x"]}},
        )
        backend.add_node("inner_body", {"id": "inner_body", "type": "script", "parameters": {}})
        backend.add_edge("trigger", "outer_loop")
        backend.add_edge("outer_loop", "inner_loop", {"from_port": "iterate"})
        backend.add_edge("inner_loop", "inner_body", {"from_port": "iterate"})
        backend.add_edge("inner_body", "inner_loop", {"to_port": "iterate"})
        backend.add_edge("inner_loop", "outer_loop", {"to_port": "iterate"})
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        wf.loop_body_map["inner_body"] = "inner_loop"
        wf.loop_body_map["inner_loop"] = "outer_loop"
        wf.resolver.set_namespace("outer_loop", {"status": "iterating"})
        wf.resolver.set_namespace("inner_loop", {"status": "iterating"})
        wf.node_control_data["outer_loop"] = {"next_port": "iterate"}
        wf.node_control_data["inner_loop"] = {"next_port": "iterate"}
        wf._build_converge_branch_nodes_index(graph)

        wf._propagate_loop_body_failure("inner_body", graph)

        assert "inner_loop" in wf.failed_nodes
        assert "outer_loop" in wf.failed_nodes

    def test_propagation_when_parent_loop_has_no_namespace(self) -> None:
        """Parent loop has no namespace yet — failure still marks it without crashing."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node(
            "loop_node",
            {"id": "loop_node", "type": "loop", "parameters": {"type": "for_each", "items": ["a"]}},
        )
        backend.add_node("body", {"id": "body", "type": "script", "parameters": {}})
        backend.add_edge("trigger", "loop_node")
        backend.add_edge("loop_node", "body", {"from_port": "iterate"})
        backend.add_edge("body", "loop_node", {"to_port": "iterate"})
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        wf.loop_body_map["body"] = "loop_node"
        wf._build_converge_branch_nodes_index(graph)

        wf._propagate_loop_body_failure("body", graph)

        assert "loop_node" in wf.failed_nodes


class TestHandleNodeFailureLoopPropagation:
    """Verify _handle_node_failure respects cancellation/CoF guards for loop propagation."""

    def _build_loop_with_body(self) -> tuple[WorkflowGraph, OrchestratorWorkflow]:
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node(
            "loop_node",
            {"id": "loop_node", "type": "loop", "parameters": {"type": "for_each", "items": ["a"]}},
        )
        backend.add_node("body", {"id": "body", "type": "script", "parameters": {}})
        backend.add_edge("trigger", "loop_node")
        backend.add_edge("loop_node", "body", {"from_port": "iterate"})
        backend.add_edge("body", "loop_node", {"to_port": "iterate"})
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        wf.loop_body_map["body"] = "loop_node"
        wf.resolver.set_namespace("loop_node", {"status": "iterating"})
        wf.node_control_data["loop_node"] = {"next_port": "iterate"}
        wf._build_converge_branch_nodes_index(graph)
        return graph, wf

    def test_cancelled_body_node_does_not_propagate_to_parent_loop(self) -> None:
        """Cancellation should NOT mark the parent loop as failed."""
        graph, wf = self._build_loop_with_body()
        error = ApplicationError("cancelled", type="InvocationCancelledError")

        wf._handle_node_failure("body", error, graph)

        assert "loop_node" not in wf.failed_nodes

    def test_cof_body_failure_does_not_propagate_to_parent_loop(self) -> None:
        """Body node with continue_on_failure=True should NOT propagate failure to parent loop."""
        graph, wf = self._build_loop_with_body()
        error = Exception("body failed")

        wf._handle_node_failure("body", error, graph, continue_on_failure=True)

        assert "loop_node" not in wf.failed_nodes
        assert "body" in wf._cof_failed_nodes

    def test_non_cof_body_failure_propagates_to_parent_loop(self) -> None:
        """Body node failure without CoF DOES propagate failure to parent loop."""
        graph, wf = self._build_loop_with_body()
        error = Exception("body failed")

        wf._handle_node_failure("body", error, graph)

        assert "loop_node" in wf.failed_nodes


class TestArePredecessorsCompleteAnyStrategy:
    """ANY strategy with failed non-CoF predecessor still converges when n_required met."""

    def test_any_strategy_converges_despite_failed_non_cof_predecessor(self) -> None:
        """A failed non-CoF predecessor should not block ANY convergence."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
        backend.add_node("node_b", {"id": "node_b", "type": "script", "parameters": {}})
        backend.add_node("node_c", {"id": "node_c", "type": "script", "parameters": {}})
        backend.add_node(
            "converge",
            {"id": "converge", "type": "converge", "parameters": {"strategy": "any", "n_required": 1}},
        )
        backend.add_edge("trigger", "node_a")
        backend.add_edge("trigger", "node_b")
        backend.add_edge("trigger", "node_c")
        backend.add_edge("node_a", "converge")
        backend.add_edge("node_b", "converge")
        backend.add_edge("node_c", "converge")
        graph = WorkflowGraph(backend)

        wf = _make_workflow(failed_nodes={"node_b": "error"})
        wf.resolver.set_namespace("node_a", {"status": "completed"})
        wf.resolver.set_namespace("node_b", {"status": "failed"})

        assert wf._are_predecessors_complete("converge", graph) is True
