"""Unit tests for pre-resolved outputs and stop-after-nodes primitives.

Tests cover:
- Pre-resolved outputs short-circuit node execution
- Pre-resolved nodes set node_inputs with __pre_resolved marker
- Pre-resolved condition nodes route correctly based on control data
- stop_after_nodes prevents scheduling of successors
- Empty pre_resolved_outputs and stop_after_nodes (standard execution)
- NamespaceResolver snapshot() and restore() roundtrip
"""

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import NexusWorkflow
from syntara.workflows.workflow_engine.graph import WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend
from tests.unit.workflows.workflow_engine.conftest import init_workflow_runtime


@pytest.fixture(autouse=True)
def mock_temporal_workflow() -> Generator[MagicMock]:
    """Mock the Temporal workflow module to avoid 'Not in workflow event loop' errors."""
    mock_logger = MagicMock()
    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
        mock_wf.logger = mock_logger
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id")
        mock_wf.execute_activity = AsyncMock()
        yield mock_wf


def _make_workflow(
    pre_resolved_outputs: dict[str, dict[str, Any]] | None = None,
    stop_after_nodes: set[str] | None = None,
    resolver: NamespaceResolver | None = None,
) -> NexusWorkflow:
    """Create a NexusWorkflow with initialized state, bypassing __init__."""
    wf = NexusWorkflow.__new__(NexusWorkflow)
    wf.skipped_nodes = set()
    wf.failed_nodes = {}
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
    wf.pre_resolved_outputs = pre_resolved_outputs if pre_resolved_outputs is not None else {}
    wf.stop_after_nodes = stop_after_nodes if stop_after_nodes is not None else set()
    wf.execution_id = "test-exec-id"
    wf.request_id = None
    return wf


def _build_linear_graph() -> WorkflowGraph:
    """Build: trigger -> node_a -> node_b -> node_c (linear chain)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {"command": "echo A"}})
    backend.add_node("node_b", {"id": "node_b", "type": "script", "parameters": {"command": "echo B"}})
    backend.add_node("node_c", {"id": "node_c", "type": "script", "parameters": {"command": "echo C"}})
    backend.add_edge("trigger", "node_a", None)
    backend.add_edge("node_a", "node_b", None)
    backend.add_edge("node_b", "node_c", None)
    return WorkflowGraph(backend)


def _build_condition_graph() -> WorkflowGraph:
    """Build: trigger -> condition -> (true: node_a, false: node_b)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("cond", {"id": "cond", "type": "condition", "parameters": {"condition": "true"}})
    backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {"command": "echo A"}})
    backend.add_node("node_b", {"id": "node_b", "type": "script", "parameters": {"command": "echo B"}})
    backend.add_edge("trigger", "cond", None)
    backend.add_edge("cond", "node_a", {"from_port": "true"})
    backend.add_edge("cond", "node_b", {"from_port": "false"})
    return WorkflowGraph(backend)


async def test_pre_resolved_node_skips_execution(mock_temporal_workflow: MagicMock) -> None:
    """Test that pre-resolved nodes skip actual execution and use the mocked output."""
    graph = _build_linear_graph()
    resolver = NamespaceResolver()
    resolver.set_namespace("trigger", {"input": "test"})
    resolver.set_namespace("node_a", {"stdout": "A output"})

    # Pre-resolve node_b
    pre_resolved = {"node_b": {"output": {"stdout": "B mocked"}}}
    wf = _make_workflow(pre_resolved_outputs=pre_resolved, resolver=resolver)

    node_b = graph.get_node("node_b")

    # Execute node_b
    result = await wf._execute_node(node=node_b, graph=graph)

    # Verify the result is the mocked output
    assert result == {"stdout": "B mocked"}

    # Verify node_inputs has the __pre_resolved marker
    assert wf.node_inputs["node_b"] == {"__pre_resolved": True}

    # Verify the Temporal activity was NOT invoked
    mock_temporal_workflow.execute_activity.assert_not_called()


async def test_pre_resolved_condition_routes_correctly(mock_temporal_workflow: MagicMock) -> None:
    """Test that pre-resolved condition nodes route based on control data."""
    graph = _build_condition_graph()
    resolver = NamespaceResolver()
    resolver.set_namespace("trigger", {"input": "test"})

    # Pre-resolve condition to route to "true" branch
    pre_resolved = {
        "cond": {
            "output": {"result": True},
            "control": {"next_port": "true"},
        }
    }
    wf = _make_workflow(pre_resolved_outputs=pre_resolved, resolver=resolver)

    cond_node = graph.get_node("cond")

    # Execute condition node
    result = await wf._execute_node(node=cond_node, graph=graph)

    # Verify the result is the mocked output
    assert result == {"result": True}

    # Verify control data was extracted and stored
    assert wf.node_control_data["cond"] == {"next_port": "true"}

    # Verify _determine_output_port returns "true"
    assert wf._determine_output_port("cond") == "true"

    # Verify the Temporal activity was NOT invoked
    mock_temporal_workflow.execute_activity.assert_not_called()


async def test_stop_after_nodes_prevents_successor_scheduling() -> None:
    """Test that stop_after_nodes prevents scheduling of successors."""
    graph = _build_linear_graph()
    resolver = NamespaceResolver()
    resolver.set_namespace("node_a", {"stdout": "A output"})

    # Stop after node_a
    wf = _make_workflow(stop_after_nodes={"node_a"}, resolver=resolver)

    pending_tasks: dict[str, asyncio.Task[Any]] = {}

    # Schedule successors of node_a
    await wf._schedule_successors(
        completed_node_id="node_a",
        graph=graph,
        pending_tasks=pending_tasks,
    )

    # Verify no successors were scheduled
    assert len(pending_tasks) == 0


async def test_stop_after_nodes_allows_execution_before_stop(
    mock_temporal_workflow: MagicMock,
) -> None:
    """Test that stop_after_nodes still allows the target node to execute."""
    graph = _build_linear_graph()
    resolver = NamespaceResolver()
    resolver.set_namespace("trigger", {"input": "test"})

    # Stop after node_a - node_a should still execute
    wf = _make_workflow(stop_after_nodes={"node_a"}, resolver=resolver)

    node_a = graph.get_node("node_a")

    # Configure the async mock
    mock_temporal_workflow.execute_activity.return_value = {"output": {"stdout": "A executed"}}

    result = await wf._execute_node(node=node_a, graph=graph)

    # Verify node_a executed normally
    assert result == {"stdout": "A executed"}
    assert mock_temporal_workflow.execute_activity.called


async def test_empty_pre_resolved_outputs_standard_execution(
    mock_temporal_workflow: MagicMock,
) -> None:
    """Test that empty pre_resolved_outputs doesn't affect normal execution."""
    graph = _build_linear_graph()
    resolver = NamespaceResolver()
    resolver.set_namespace("trigger", {"input": "test"})

    # No pre-resolved outputs
    wf = _make_workflow(pre_resolved_outputs={}, resolver=resolver)

    node_a = graph.get_node("node_a")

    # Configure the async mock
    mock_temporal_workflow.execute_activity.return_value = {"output": {"stdout": "A executed"}}

    result = await wf._execute_node(node=node_a, graph=graph)

    # Verify node_a executed normally (not skipped)
    assert result == {"stdout": "A executed"}
    assert mock_temporal_workflow.execute_activity.called

    # Verify node_inputs does NOT have __pre_resolved marker
    assert "__pre_resolved" not in wf.node_inputs.get("node_a", {})


async def test_empty_stop_after_nodes_standard_execution() -> None:
    """Test that empty stop_after_nodes doesn't prevent successor scheduling."""
    graph = _build_linear_graph()
    resolver = NamespaceResolver()
    resolver.set_namespace("node_a", {"stdout": "A output"})

    # No stop-after-nodes
    wf = _make_workflow(stop_after_nodes=set(), resolver=resolver)

    pending_tasks: dict[str, asyncio.Task[Any]] = {}

    # Mock asyncio.create_task to track scheduled nodes
    scheduled_nodes: list[str] = []

    def mock_create_task(coro: Any) -> MagicMock:  # noqa: ANN401
        # Extract node_id from coro (it's an _execute_node call)
        task_mock = MagicMock()
        # Track that we created a task
        scheduled_nodes.append("successor")
        return task_mock

    with patch("asyncio.create_task", side_effect=mock_create_task):
        # Schedule successors of node_a
        await wf._schedule_successors(
            completed_node_id="node_a",
            graph=graph,
            pending_tasks=pending_tasks,
        )

        # Verify a successor was scheduled (node_b should be scheduled)
        assert len(pending_tasks) > 0


def test_namespace_resolver_snapshot_restore_roundtrip() -> None:
    """Test that NamespaceResolver snapshot() and restore() work correctly."""
    resolver = NamespaceResolver()

    # Set up some namespaces and loop context
    resolver.set_namespace("trigger", {"url": "https://example.com", "method": "GET"})
    resolver.set_namespace("node_a", {"stdout": "output A", "exit_code": 0})
    resolver.set_namespace("node_b", {"data": {"nested": {"key": "value"}}, "count": 42})
    resolver.set_context(loop_node_id="loop_1")

    # Take a snapshot
    snapshot = resolver.snapshot()

    # Verify snapshot contains namespaces and loop context
    assert snapshot["namespaces"] == resolver.namespaces
    assert snapshot["namespaces"] is not resolver.namespaces
    assert snapshot["loop_node_id"] == "loop_1"

    # Modify the resolver
    resolver.set_namespace("node_c", {"new": "data"})
    resolver.remove_namespace("node_a")
    resolver.set_context(loop_node_id="loop_2")

    # Verify the snapshot wasn't affected
    assert "node_c" not in snapshot["namespaces"]
    assert "node_a" in snapshot["namespaces"]
    assert snapshot["loop_node_id"] == "loop_1"

    # Restore from snapshot
    resolver.restore(snapshot)

    # Verify the resolver state matches the snapshot
    assert resolver.namespaces == snapshot["namespaces"]
    assert resolver.has_namespace("node_a")
    assert not resolver.has_namespace("node_c")
    assert resolver.get_namespace("trigger") == {"url": "https://example.com", "method": "GET"}
    assert resolver._find_upstream_loop() == "loop_1"


def test_namespace_resolver_snapshot_deep_copy_isolation() -> None:
    """Test that snapshot() returns a deep copy to prevent mutation."""
    resolver = NamespaceResolver()
    resolver.set_namespace("node_a", {"data": {"nested": "value"}})

    # Take a snapshot
    snapshot = resolver.snapshot()

    # Mutate the snapshot
    snapshot["namespaces"]["node_a"]["data"]["nested"] = "MUTATED"

    # Verify the resolver wasn't affected
    assert resolver.get_namespace("node_a")["data"]["nested"] == "value"


async def test_pre_resolved_with_stop_after_combined() -> None:
    """Test combining pre_resolved_outputs and stop_after_nodes."""
    graph = _build_linear_graph()
    resolver = NamespaceResolver()
    resolver.set_namespace("trigger", {"input": "test"})

    # Pre-resolve node_a and stop after it
    pre_resolved = {"node_a": {"output": {"stdout": "A mocked"}}}
    wf = _make_workflow(pre_resolved_outputs=pre_resolved, stop_after_nodes={"node_a"}, resolver=resolver)

    node_a = graph.get_node("node_a")

    # Execute node_a
    result = await wf._execute_node(node=node_a, graph=graph)

    # Verify pre-resolved output was used
    assert result == {"stdout": "A mocked"}
    assert wf.node_inputs["node_a"] == {"__pre_resolved": True}

    # Try to schedule successors
    pending_tasks: dict[str, asyncio.Task[Any]] = {}
    await wf._schedule_successors(
        completed_node_id="node_a",
        graph=graph,
        pending_tasks=pending_tasks,
    )

    # Verify stop_after_nodes prevented scheduling
    assert len(pending_tasks) == 0


async def test_pre_resolved_multiple_nodes_in_chain(
    mock_temporal_workflow: MagicMock,
) -> None:
    """Test pre-resolving multiple nodes in a linear chain."""
    graph = _build_linear_graph()
    resolver = NamespaceResolver()
    resolver.set_namespace("trigger", {"input": "test"})

    # Pre-resolve node_a and node_b, but not node_c
    pre_resolved = {
        "node_a": {"output": {"stdout": "A mocked"}},
        "node_b": {"output": {"stdout": "B mocked"}},
    }
    wf = _make_workflow(pre_resolved_outputs=pre_resolved, resolver=resolver)

    # Execute node_a
    node_a = graph.get_node("node_a")
    result_a = await wf._execute_node(node=node_a, graph=graph)
    assert result_a == {"stdout": "A mocked"}
    assert wf.node_inputs["node_a"] == {"__pre_resolved": True}

    # Set the result in resolver (simulating _process_pending_tasks behavior)
    resolver.set_namespace("node_a", result_a)

    # Execute node_b
    node_b = graph.get_node("node_b")
    result_b = await wf._execute_node(node=node_b, graph=graph)
    assert result_b == {"stdout": "B mocked"}
    assert wf.node_inputs["node_b"] == {"__pre_resolved": True}

    # Set the result in resolver
    resolver.set_namespace("node_b", result_b)

    # Execute node_c (should execute normally, not pre-resolved)
    node_c = graph.get_node("node_c")

    # Configure the async mock for node_c execution
    mock_temporal_workflow.execute_activity.return_value = {"output": {"stdout": "C executed"}}

    result_c = await wf._execute_node(node=node_c, graph=graph)

    # Verify node_c executed normally
    assert result_c == {"stdout": "C executed"}
    assert mock_temporal_workflow.execute_activity.called
    # node_c should NOT have __pre_resolved marker
    assert wf.node_inputs.get("node_c", {}).get("__pre_resolved") is not True


async def test_pre_resolved_condition_routes_to_false_branch() -> None:
    """Test that pre-resolved condition can route to false branch."""
    graph = _build_condition_graph()
    resolver = NamespaceResolver()
    resolver.set_namespace("trigger", {"input": "test"})

    # Pre-resolve condition to route to "false" branch
    pre_resolved = {
        "cond": {
            "output": {"result": False},
            "control": {"next_port": "false"},
        }
    }
    wf = _make_workflow(pre_resolved_outputs=pre_resolved, resolver=resolver)

    cond_node = graph.get_node("cond")

    # Execute condition node
    result = await wf._execute_node(node=cond_node, graph=graph)

    # Verify the result is the mocked output
    assert result == {"result": False}

    # Verify control data was extracted and stored
    assert wf.node_control_data["cond"] == {"next_port": "false"}

    # Verify _determine_output_port returns "false"
    assert wf._determine_output_port("cond") == "false"


def test_get_pre_resolved_nodes_returns_pre_resolved_ids() -> None:
    """Test get_pre_resolved_nodes returns list of pre-resolved node IDs."""
    pre_resolved: dict[str, dict[str, Any]] = {"node_a": {"output": {}}, "node_b": {"output": {}}}
    wf = _make_workflow(pre_resolved_outputs=pre_resolved)
    result = wf.get_pre_resolved_nodes()
    assert sorted(result) == ["node_a", "node_b"]


def test_get_pre_resolved_nodes_empty_when_none() -> None:
    """Test get_pre_resolved_nodes returns empty list when no pre-resolved nodes."""
    wf = _make_workflow()
    result = wf.get_pre_resolved_nodes()
    assert result == []
