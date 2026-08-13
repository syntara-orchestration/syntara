"""Unit tests for deterministic activity scheduling (AAP-87141).

Temporal requires workflow code to be fully deterministic: the same sequence of
commands (ScheduleActivity, etc.) must be produced on every replay.  Any
non-deterministic ordering of ``asyncio.create_task`` calls causes
``[TMPRL1100] Nondeterminism error``.

The tests here verify two sources of ordering that must be stable:

1. ``_process_pending_tasks`` — ``wait_tasks`` passed to ``workflow.wait`` must
   be in sorted node-ID order.  Temporal's ``workflow.wait`` preserves input
   order in its ``done`` list, so sorting the input is sufficient to guarantee
   that completed tasks are processed in a deterministic order on every replay.

2. ``_process_pending_tasks`` — ``_timed_out_converge_nodes`` is a ``set``; its
   iteration order must be deterministic when multiple converge nodes time out
   simultaneously.
"""

import asyncio
from collections.abc import Coroutine, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import NexusWorkflow
from syntara.workflows.workflow_engine.graph import WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend
from tests.unit.workflows.workflow_engine.conftest import init_workflow_runtime

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


def _build_parallel_graph(branch_ids: list[str]) -> WorkflowGraph:
    """Build: trigger -> [branch_0, branch_1, ...] (pure fan-out, no converge)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    for bid in branch_ids:
        backend.add_node(bid, {"id": bid, "type": "script", "parameters": {}})
        backend.add_edge("trigger", bid, None)
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


def _run_loop(coro: Coroutine[object, object, object]) -> object:
    """Execute a coroutine in a fresh event loop and return its result."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_capturing_wait(
    pending: dict[str, asyncio.Task[Any]],
    captured: list[list[asyncio.Task[Any]]],
) -> object:
    """Return a ``workflow.wait`` replacement that records ``wait_tasks`` once then exits.

    On the first call it records the argument and clears ``pending`` so the
    ``_process_pending_tasks`` while-loop terminates.  Subsequent calls (which
    should not occur in these tests) raise ``AssertionError``.
    """
    called = False

    async def _wait(wait_tasks: list[asyncio.Task[Any]], **_kwargs: object) -> tuple[list, list]:
        nonlocal called
        assert not called, "workflow.wait called more than once"
        called = True
        captured.append(list(wait_tasks))
        # Drain pending so the while-loop exits after this iteration.
        pending.clear()
        return [], []

    return _wait


# ---------------------------------------------------------------------------
# TestWaitTasksOrdering — wait_tasks passed to workflow.wait is sorted by node ID
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_mock_temporal_workflow")
class TestWaitTasksOrdering:
    """Verify that ``workflow.wait`` is called with pending tasks in sorted node-ID order.

    Temporal's ``workflow.wait`` preserves input order in its ``done`` list
    (it rebuilds done/pending by iterating the original ``fs`` list).  Sorting
    ``wait_tasks`` by node ID therefore guarantees that completed tasks are
    always processed in the same deterministic order on every replay, preventing
    ``TMPRL1100`` nondeterminism errors.
    """

    def test_two_pending_tasks_sorted_by_node_id(self, _mock_temporal_workflow: MagicMock) -> None:  # noqa: PT019
        """With two pending tasks inserted in reverse-alpha order, wait_tasks is alpha-sorted."""
        wf = _make_workflow()
        graph = _build_parallel_graph(["node_z", "node_a"])
        captured: list[list[asyncio.Task[Any]]] = []

        async def run() -> None:
            async def instant() -> dict[str, Any]:
                return {}

            task_z = asyncio.create_task(instant())
            task_a = asyncio.create_task(instant())
            # Deliberately insert in reverse-alpha order.
            pending: dict[str, asyncio.Task[Any]] = {"node_z": task_z, "node_a": task_a}

            _mock_temporal_workflow.wait = _make_capturing_wait(pending, captured)
            await wf._process_pending_tasks(pending, graph)

            assert captured[0][0] is task_a, "node_a must be first in wait_tasks"
            assert captured[0][1] is task_z, "node_z must be second in wait_tasks"

        _run_loop(run())

    def test_five_pending_tasks_sorted_by_node_id(self, _mock_temporal_workflow: MagicMock) -> None:  # noqa: PT019
        """Five pending tasks inserted in arbitrary order arrive at workflow.wait sorted."""
        # IDs matching the Jira bug report error evidence.
        branch_ids = ["b4_s1", "b2_s1", "b0_s1", "b1_s1", "b3_s1"]
        wf = _make_workflow()
        graph = _build_parallel_graph(branch_ids)
        captured: list[list[asyncio.Task[Any]]] = []

        async def run() -> None:
            async def instant() -> dict[str, Any]:
                return {}

            tasks = {bid: asyncio.create_task(instant()) for bid in branch_ids}
            pending = dict(tasks)

            _mock_temporal_workflow.wait = _make_capturing_wait(pending, captured)
            await wf._process_pending_tasks(pending, graph)

            expected_order = [tasks[nid] for nid in sorted(branch_ids)]
            assert captured[0] == expected_order

        _run_loop(run())

    def test_single_pending_task_passed_through(self, _mock_temporal_workflow: MagicMock) -> None:  # noqa: PT019
        """A single pending task is passed to workflow.wait unchanged."""
        wf = _make_workflow()
        graph = _build_parallel_graph(["only_node"])
        captured: list[list[asyncio.Task[Any]]] = []

        async def run() -> None:
            async def instant() -> dict[str, Any]:
                return {}

            task = asyncio.create_task(instant())
            pending: dict[str, asyncio.Task[Any]] = {"only_node": task}

            _mock_temporal_workflow.wait = _make_capturing_wait(pending, captured)
            await wf._process_pending_tasks(pending, graph)

            assert captured[0] == [task]

        _run_loop(run())

    def test_timeout_tasks_appended_after_sorted_pending_tasks(self, _mock_temporal_workflow: MagicMock) -> None:  # noqa: PT019
        """Timeout tasks are appended after the sorted pending tasks in wait_tasks."""
        wf = _make_workflow()
        graph = _build_parallel_graph(["node_b", "node_a"])
        captured: list[list[asyncio.Task[Any]]] = []

        async def run() -> None:
            async def instant() -> dict[str, Any]:
                return {}

            async def timeout_coro() -> None:
                await asyncio.sleep(9999)

            task_b = asyncio.create_task(instant())
            task_a = asyncio.create_task(instant())
            # Inserted in reverse-alpha order.
            pending: dict[str, asyncio.Task[Any]] = {"node_b": task_b, "node_a": task_a}

            timeout_task = asyncio.create_task(timeout_coro())
            wf._timeout_tasks["some_converge"] = timeout_task

            _mock_temporal_workflow.wait = _make_capturing_wait(pending, captured)
            try:
                await wf._process_pending_tasks(pending, graph)
            finally:
                timeout_task.cancel()

            # Pending tasks sorted (node_a, node_b), then the timeout task.
            assert captured[0][0] is task_a
            assert captured[0][1] is task_b
            assert captured[0][2] is timeout_task

        _run_loop(run())

    def test_wait_called_with_list_not_set(self, _mock_temporal_workflow: MagicMock) -> None:  # noqa: PT019
        """workflow.wait receives a list — sets have undefined iteration order."""
        wf = _make_workflow()
        graph = _build_parallel_graph(["node_a", "node_b"])

        async def run() -> None:
            async def instant() -> dict[str, Any]:
                return {}

            pending: dict[str, asyncio.Task[Any]] = {
                "node_a": asyncio.create_task(instant()),
                "node_b": asyncio.create_task(instant()),
            }

            captured_type: list[type] = []

            async def type_capturing_wait(wait_tasks: object, **_kwargs: object) -> tuple[list, list]:
                captured_type.append(type(wait_tasks))
                pending.clear()
                return [], []

            _mock_temporal_workflow.wait = type_capturing_wait
            await wf._process_pending_tasks(pending, graph)

            assert captured_type[0] is list, f"workflow.wait must receive a list, got {captured_type[0].__name__}"

        _run_loop(run())


# ---------------------------------------------------------------------------
# TestTimedOutConvergeOrdering — _timed_out_converge_nodes iterated in sorted order
# ---------------------------------------------------------------------------


class TestTimedOutConvergeOrdering:
    """Verify ``_timed_out_converge_nodes`` is drained in sorted node-ID order.

    When multiple converge nodes time out simultaneously the set must be
    iterated deterministically so that downstream ``_schedule_successors``
    calls are always issued in the same order on every Temporal replay.
    """

    def test_two_timed_out_converges_scheduled_in_node_id_order(self) -> None:
        """Two simultaneously timed-out converge nodes are scheduled in alpha order."""
        wf = _make_workflow()
        graph = _build_two_converge_graph()

        for cid in ("conv_alpha", "conv_beta"):
            wf._timed_out_converge_nodes.add(cid)
            wf._cof_failed_nodes.add(cid)
            wf.failed_nodes[cid] = "timed out"
            wf.resolver.set_namespace(cid, {"status": "failed"})

        schedule_order: list[str] = []

        async def fake_schedule_successors(completed_node_id: str, *_args: object, **_kwargs: object) -> None:
            schedule_order.append(completed_node_id)

        with patch.object(wf, "_schedule_successors", new_callable=AsyncMock, side_effect=fake_schedule_successors):
            _run_loop(wf._process_pending_tasks({}, graph))

        # conv_alpha < conv_beta alphabetically — must be scheduled first.
        assert schedule_order == ["conv_alpha", "conv_beta"]

    def test_five_timed_out_converges_scheduled_in_node_id_order(self) -> None:
        """Five simultaneously timed-out converge nodes are drained in sorted order."""
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
            wf._timed_out_converge_nodes.add(cid)
            wf._cof_failed_nodes.add(cid)
            wf.failed_nodes[cid] = "timed out"
            wf.resolver.set_namespace(cid, {"status": "failed"})

        schedule_order: list[str] = []

        async def fake_schedule_successors(completed_node_id: str, *_args: object, **_kwargs: object) -> None:
            schedule_order.append(completed_node_id)

        with patch.object(wf, "_schedule_successors", new_callable=AsyncMock, side_effect=fake_schedule_successors):
            _run_loop(wf._process_pending_tasks({}, graph))

        assert schedule_order == sorted(converge_ids)

    def test_timed_out_converge_nodes_cleared_after_processing(self) -> None:
        """All processed converge IDs are removed from ``_timed_out_converge_nodes``."""
        wf = _make_workflow()
        graph = _build_two_converge_graph()

        for cid in ("conv_alpha", "conv_beta"):
            wf._timed_out_converge_nodes.add(cid)
            wf._cof_failed_nodes.add(cid)
            wf.failed_nodes[cid] = "timed out"
            wf.resolver.set_namespace(cid, {"status": "failed"})

        with patch.object(wf, "_schedule_successors", new_callable=AsyncMock):
            _run_loop(wf._process_pending_tasks({}, graph))

        assert len(wf._timed_out_converge_nodes) == 0
