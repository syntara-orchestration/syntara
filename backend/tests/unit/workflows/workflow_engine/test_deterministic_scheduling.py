"""Unit tests for deterministic activity scheduling in parallel workflows.

Temporal requires workflow code to produce identical command sequences on
every replay.  These tests verify that parallel task scheduling, converge
timeout draining, and converge timeout creation all follow a stable,
sorted node-ID order.
"""

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import NexusWorkflow
from syntara.workflows.workflow_engine.graph import WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend
from tests.unit.workflows.workflow_engine.conftest import init_workflow_runtime

type _Task = asyncio.Task[None]

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_temporal_workflow() -> Generator[MagicMock]:
    """Suppress 'Not in workflow event loop' errors from Temporal SDK calls."""
    with (
        patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf,
        patch("syntara.workflows.workflow_engine.converge_mixin.workflow", mock_wf),
    ):
        mock_wf.logger = MagicMock()
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id")
        mock_wf.wait = AsyncMock(return_value=([], []))
        yield mock_wf


def _make_workflow(
    skipped_nodes: set[str] | None = None,
    failed_nodes: dict[str, str] | None = None,
) -> NexusWorkflow:
    """Instantiate NexusWorkflow with minimal state, bypassing ``__init__``."""
    wf = NexusWorkflow.__new__(NexusWorkflow)
    wf.skipped_nodes = skipped_nodes if skipped_nodes is not None else set()
    wf.failed_nodes = failed_nodes if failed_nodes is not None else {}
    wf.resolver = NamespaceResolver()
    wf.node_inputs = {}
    wf.node_control_data = {}
    wf.loop_state = {}
    wf.loop_body_map = {}
    wf.loop_iteration_results = {}
    wf._timeout_tasks = {}
    wf._timed_out_converge_nodes = set()
    wf._detached_nodes = set()
    wf._cof_failed_nodes = set()
    wf._converge_branch_nodes = {}
    init_workflow_runtime(wf)
    wf.pre_resolved_outputs = {}
    wf.stop_after_nodes = set()
    return wf


def _new_task() -> _Task:
    return asyncio.create_task(asyncio.sleep(0))


def _mark_converge_timed_out(wf: NexusWorkflow, converge_id: str) -> None:
    wf._timed_out_converge_nodes.add(converge_id)
    wf._cof_failed_nodes.add(converge_id)
    wf.failed_nodes[converge_id] = "timed out"
    wf.resolver.set_namespace(converge_id, {"status": "failed"})


def _build_parallel_graph(branch_ids: list[str]) -> WorkflowGraph:
    """Build: trigger -> [branch_0, branch_1, ...] (pure fan-out, no converge)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    for bid in branch_ids:
        backend.add_node(bid, {"id": bid, "type": "script", "parameters": {}})
        backend.add_edge("trigger", bid, None)
    return WorkflowGraph(backend)


def _build_shared_branch_graph() -> WorkflowGraph:
    """Build a graph where one node feeds two converge nodes.

    trigger -> shared_node -> conv_alpha
                           -> conv_beta

    ``shared_node`` is a predecessor of both converge nodes, so
    ``_converge_branch_nodes["shared_node"]`` contains two IDs.
    """
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("shared_node", {"id": "shared_node", "type": "script", "parameters": {}})
    backend.add_node("conv_alpha", {"id": "conv_alpha", "type": "converge", "parameters": {}})
    backend.add_node("conv_beta", {"id": "conv_beta", "type": "converge", "parameters": {}})
    backend.add_edge("trigger", "shared_node", None)
    backend.add_edge("shared_node", "conv_alpha", None)
    backend.add_edge("shared_node", "conv_beta", None)
    return WorkflowGraph(backend)


def _build_two_converge_graph() -> WorkflowGraph:
    """Build two independent converge nodes fed by four branches.

    trigger -> [a0, a1] -> conv_alpha -> final_alpha
    trigger -> [b0, b1] -> conv_beta  -> final_beta
    """
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    for nid in ("a0", "a1", "b0", "b1"):
        backend.add_node(nid, {"id": nid, "type": "script", "parameters": {}})
    backend.add_node("conv_alpha", {"id": "conv_alpha", "type": "converge", "parameters": {}})
    backend.add_node("conv_beta", {"id": "conv_beta", "type": "converge", "parameters": {}})
    backend.add_node("final_alpha", {"id": "final_alpha", "type": "script", "parameters": {}})
    backend.add_node("final_beta", {"id": "final_beta", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "a0", None)
    backend.add_edge("trigger", "a1", None)
    backend.add_edge("trigger", "b0", None)
    backend.add_edge("trigger", "b1", None)
    backend.add_edge("a0", "conv_alpha", None)
    backend.add_edge("a1", "conv_alpha", None)
    backend.add_edge("b0", "conv_beta", None)
    backend.add_edge("b1", "conv_beta", None)
    backend.add_edge("conv_alpha", "final_alpha", None)
    backend.add_edge("conv_beta", "final_beta", None)
    return WorkflowGraph(backend)


def _make_capturing_wait(
    pending: dict[str, _Task],
    captured: list[list[_Task]],
) -> object:
    """Record ``wait_tasks`` on the first call and drain ``pending`` to exit the processing loop."""
    called = False

    async def _wait(wait_tasks: list[_Task], **_kwargs: object) -> tuple[list[_Task], list[_Task]]:
        nonlocal called
        assert not called, "workflow.wait called more than once"
        called = True
        captured.append(list(wait_tasks))
        pending.clear()
        return [], []

    return _wait


# ---------------------------------------------------------------------------
# TestWaitTasksOrdering — pending tasks arrive at workflow.wait in sorted node-ID order
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_mock_temporal_workflow")
class TestWaitTasksOrdering:
    """Pending tasks are passed to workflow.wait in sorted node-ID order."""

    def test_pending_tasks_sorted_by_node_id(self, _mock_temporal_workflow: MagicMock) -> None:  # noqa: PT019
        """Pending tasks are passed to workflow.wait in sorted node-ID order."""
        branch_ids = ["b4_s1", "b2_s1", "b0_s1", "b1_s1", "b3_s1"]
        wf = _make_workflow()
        graph = _build_parallel_graph(branch_ids)
        captured: list[list[_Task]] = []

        async def run() -> None:
            tasks = {bid: _new_task() for bid in branch_ids}
            pending = dict(tasks)

            _mock_temporal_workflow.wait = _make_capturing_wait(pending, captured)
            await wf._process_pending_tasks(pending, graph)

            expected_order = [tasks[nid] for nid in sorted(branch_ids)]
            assert captured[0] == expected_order

        asyncio.run(run())

    def test_timeout_tasks_appended_after_sorted_pending_tasks(self, _mock_temporal_workflow: MagicMock) -> None:  # noqa: PT019
        """Timeout tasks are appended after pending tasks in wait_tasks."""
        wf = _make_workflow()
        graph = _build_parallel_graph(["node_b", "node_a"])
        captured: list[list[_Task]] = []

        async def run() -> None:
            async def timeout_coro() -> None:
                await asyncio.sleep(9999)

            task_a, task_b = _new_task(), _new_task()
            pending: dict[str, _Task] = {"node_b": task_b, "node_a": task_a}

            timeout_task = asyncio.create_task(timeout_coro())
            wf._timeout_tasks["some_converge"] = timeout_task

            _mock_temporal_workflow.wait = _make_capturing_wait(pending, captured)
            try:
                await wf._process_pending_tasks(pending, graph)
            finally:
                timeout_task.cancel()

            assert captured[0][0] is task_a
            assert captured[0][1] is task_b
            assert captured[0][2] is timeout_task

        asyncio.run(run())


# ---------------------------------------------------------------------------
# TestTimedOutConvergeOrdering — timed-out converge nodes drained in sorted order
# ---------------------------------------------------------------------------


class TestTimedOutConvergeOrdering:
    """Simultaneously timed-out converge nodes schedule successors in sorted node-ID order."""

    def test_timed_out_converges_scheduled_in_node_id_order(self) -> None:
        """Timed-out converge nodes schedule successors in sorted node-ID order."""
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        converge_ids = ["conv_e", "conv_c", "conv_a", "conv_b", "conv_d"]
        for cid in converge_ids:
            branch = f"branch_{cid}"
            backend.add_node(branch, {"id": branch, "type": "script", "parameters": {}})
            backend.add_node(cid, {"id": cid, "type": "converge", "parameters": {}})
            backend.add_edge("trigger", branch, None)
            backend.add_edge(branch, cid, None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        for cid in converge_ids:
            _mark_converge_timed_out(wf, cid)

        schedule_order: list[str] = []

        async def fake_schedule_successors(completed_node_id: str, *_args: object, **_kwargs: object) -> None:
            schedule_order.append(completed_node_id)

        with patch.object(wf, "_schedule_successors", new_callable=AsyncMock, side_effect=fake_schedule_successors):
            asyncio.run(wf._process_pending_tasks({}, graph))

        assert schedule_order == sorted(converge_ids)

    def test_timed_out_converge_nodes_cleared_after_processing(self) -> None:
        """All processed converge IDs are removed from ``_timed_out_converge_nodes``."""
        wf = _make_workflow()
        graph = _build_two_converge_graph()

        for cid in ("conv_alpha", "conv_beta"):
            _mark_converge_timed_out(wf, cid)

        with patch.object(wf, "_schedule_successors", new_callable=AsyncMock):
            asyncio.run(wf._process_pending_tasks({}, graph))

        assert len(wf._timed_out_converge_nodes) == 0


# ---------------------------------------------------------------------------
# TestConvergeTimeoutCreationOrder — timeout tasks started in sorted converge-ID order
# ---------------------------------------------------------------------------


class TestConvergeTimeoutCreationOrder:
    """Converge timeout tasks are started in sorted converge-node-ID order."""

    def test_five_converge_timeouts_created_in_sorted_order(self) -> None:
        """Five converge timeout tasks are started in sorted converge-node-ID order."""
        converge_ids = ["conv_e", "conv_c", "conv_a", "conv_b", "conv_d"]
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node("shared_node", {"id": "shared_node", "type": "script", "parameters": {}})
        for cid in converge_ids:
            backend.add_node(cid, {"id": cid, "type": "converge", "parameters": {}})
            backend.add_edge("shared_node", cid, None)
        backend.add_edge("trigger", "shared_node", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow()
        wf._converge_branch_nodes = {"shared_node": set(converge_ids)}

        with patch("syntara.workflows.workflow_engine.converge_mixin.asyncio.create_task") as mock_create:
            mock_create.return_value = MagicMock(spec=asyncio.Task)
            wf._handle_converge_timeout("shared_node", graph, {})

        created_order = list(wf._timeout_tasks.keys())
        assert created_order == sorted(created_order)

    def test_already_started_timeout_not_duplicated(self) -> None:
        """A converge node whose timeout is already running is not started again."""
        wf = _make_workflow()
        graph = _build_shared_branch_graph()
        wf._converge_branch_nodes = {"shared_node": {"conv_alpha", "conv_beta"}}

        existing_task: MagicMock = MagicMock(spec=asyncio.Task)
        wf._timeout_tasks["conv_alpha"] = existing_task

        with patch("syntara.workflows.workflow_engine.converge_mixin.asyncio.create_task") as mock_create:
            mock_create.return_value = MagicMock(spec=asyncio.Task)
            wf._handle_converge_timeout("shared_node", graph, {})

        mock_create.assert_called_once()
        assert wf._timeout_tasks["conv_alpha"] is existing_task

    def test_failed_converge_does_not_get_timeout(self) -> None:
        """A converge node already in ``failed_nodes`` does not get a timeout task."""
        wf = _make_workflow()
        graph = _build_shared_branch_graph()
        wf._converge_branch_nodes = {"shared_node": {"conv_alpha", "conv_beta"}}
        wf.failed_nodes["conv_alpha"] = "upstream failure"

        with patch("syntara.workflows.workflow_engine.converge_mixin.asyncio.create_task") as mock_create:
            mock_create.return_value = MagicMock(spec=asyncio.Task)
            wf._handle_converge_timeout("shared_node", graph, {})

        mock_create.assert_called_once()
        assert "conv_alpha" not in wf._timeout_tasks
