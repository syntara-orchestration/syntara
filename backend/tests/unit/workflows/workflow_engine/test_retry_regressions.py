"""Regression tests for defects found reviewing the retry-from-failure work.

Each test here reproduces a bug that shipped, using graph shapes the product
actually produces. Earlier tests missed these because they encoded assumptions
about the definition format rather than the format itself.
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend

# ---------------------------------------------------------------------------
# Helpers that build realistic definitions
# ---------------------------------------------------------------------------


def _add(backend: InMemoryGraphBackend, node_id: str, node_type: str, parameters: dict[str, Any] | None = None) -> None:
    backend.add_node(node_id, {"id": node_id, "type": node_type, "parameters": parameters or {}})


def _plain(backend: InMemoryGraphBackend, source: str, target: str) -> None:
    """A default-handle edge, as the builder emits for a single-output node.

    Only multi-output nodes carry ``from_port``. Body-internal edges do not.
    """
    backend.add_edge(source, target, None)


def _loop_body_graph() -> WorkflowGraph:
    """Build trigger -> loop_1 { body_a -> body_b -> body_c } -> step_2.

    Built the way the builder builds it: ``from_port`` only on the loop's own
    exit, feedback edge stripped, body-internal edges plain.
    """
    backend = InMemoryGraphBackend()
    _add(backend, "trigger", "manual_trigger")
    _add(backend, "loop_1", "loop")
    _add(backend, "body_a", "script")
    _add(backend, "body_b", "script")
    _add(backend, "body_c", "script")
    _add(backend, "step_2", "script")
    _plain(backend, "trigger", "loop_1")
    backend.add_edge("loop_1", "body_a", {"from_port": "iterate"})
    _plain(backend, "body_a", "body_b")
    _plain(backend, "body_b", "body_c")
    backend.add_edge("body_c", "loop_1", {"to_port": "iterate"})  # stripped as feedback
    backend.add_edge("loop_1", "step_2", {"from_port": "complete"})
    return WorkflowGraph(backend)


def _diamond_graph() -> WorkflowGraph:
    """Build split -> {fail_b, ok_c} -> join -> tail.

    ``join`` completed in the source run via the branch that succeeded, so it has
    a stored output even though it is downstream of the retry point.
    """
    backend = InMemoryGraphBackend()
    _add(backend, "split", "condition")
    _add(backend, "fail_b", "script")
    _add(backend, "ok_c", "script")
    _add(backend, "join", "script")
    _add(backend, "tail", "script")
    backend.add_edge("split", "fail_b", {"from_port": "true"})
    backend.add_edge("split", "ok_c", {"from_port": "false"})
    _plain(backend, "fail_b", "join")
    _plain(backend, "ok_c", "join")
    _plain(backend, "join", "tail")
    return WorkflowGraph(backend)


def _wf(retry_context: dict[str, Any] | None = None) -> OrchestratorWorkflow:
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.retry_context = retry_context or {}
    wf._retry_restorable_cache = None
    wf._retry_replay_candidates = set()
    # A deferred retry converge records its gate reason and upstream failure here
    # before the replay comparison runs; the gate helpers read them back.
    wf._retry_converge_failure_reasons = {}
    wf._retry_converge_upstream_failures = {}
    wf._restored_node_timestamps = {}
    wf._restored_node_statuses = {}
    wf._restored_node_outputs = {}
    # Persisted routing, read before classification. Empty means nothing was
    # recorded, so every control node falls back to inference — the pre-existing
    # behaviour for these tests.
    wf._restored_control_ports = {}
    wf._resolved_control_port_cache = {}
    # Branch inference reads it; empty means no control node is inferable, which is
    # the pre-existing behaviour for these tests.
    wf._retry_source_statuses = {}
    wf.resolver = NamespaceResolver()
    wf.skipped_nodes = set()
    wf.failed_nodes = {}
    wf._cof_failed_nodes = set()
    wf._runtime_settings = {}
    wf.loop_state = {}
    wf.loop_body_map = {}
    wf.loop_iteration_results = {}
    wf.node_inputs = {}
    # A converge reads this to tell whether a loop predecessor is still iterating,
    # so it must exist even on a workflow built without __init__.
    wf.node_control_data = {}
    # Set in __init__ for a real run and filled by _prepare_retry from the source
    # execution. The restore path consults it to decide whether a replay is worth
    # scheduling, so a workflow built by hand needs it too.
    wf._retry_source_statuses = {}
    wf._loop_bodies = {}
    wf._active_loop_iteration = {}
    return wf


def _retry(*eligible: str) -> dict[str, Any]:
    return {"retry_from_execution_id": "src-1", "eligible_point_ids": list(eligible)}


@pytest.fixture
def mock_wf() -> Generator[MagicMock, None, None]:
    with (
        patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as patched,
        patch("syntara.workflows.workflow_engine.retry_mixin.workflow", patched),
    ):
        patched.logger = MagicMock()
        yield patched


# ---------------------------------------------------------------------------
# Loop body nodes restore from their per-iteration source rows
# ---------------------------------------------------------------------------


def test_multi_node_body_remains_eligible_for_per_iteration_replay() -> None:
    """All nodes in a loop body remain eligible for per-iteration replay."""
    wf = _wf(_retry("step_2"))

    restorable = wf._retry_restorable_nodes(_loop_body_graph())

    # Bodies restore per iteration now, so they are eligible rather than excluded.
    assert {"body_a", "body_b", "body_c"} <= restorable


# ---------------------------------------------------------------------------
# A restored predecessor must satisfy a converge gate
# ---------------------------------------------------------------------------


def _converge_graph() -> WorkflowGraph:
    backend = InMemoryGraphBackend()
    _add(backend, "b1", "script")
    _add(backend, "b2", "script")
    _add(backend, "join", "converge", {"strategy": "any", "n_required": 2})
    _plain(backend, "b1", "join")
    _plain(backend, "b2", "join")
    return WorkflowGraph(backend)


@pytest.mark.asyncio
async def test_restored_predecessor_counts_toward_converge_gate(mock_wf: MagicMock) -> None:
    """A restored predecessor counts toward a converge gate.

    Drives the real restore path rather than simulating its state, so the test
    cannot drift from what the engine actually does.
    """
    wf = _wf(_retry("b2"))
    # The source run recorded b1 as completed, so the restore path schedules a
    # replay for it; that is what _prepare_retry would have loaded beforehand.
    wf._retry_source_statuses = {"b1": "completed"}
    mock_wf.execute_activity = AsyncMock(return_value={"b1": {"v": 1}})
    node = ActivityNode(node_id="b1", node_type="script", parameters={})
    graph = _converge_graph()
    result = await wf._restore_node_state(node, graph)
    from .conftest import complete_supplied_node

    assert result is not None

    await complete_supplied_node(wf, node, result, _converge_graph())
    wf.resolver.set_namespace("b2", {"v": 2, "status": "completed"})

    assert "b1" in wf._restored_node_timestamps
    assert "b1" not in wf.skipped_nodes, "a restored node did not get skipped; it ran"
    assert wf._are_predecessors_complete("join", _converge_graph()) is True


@pytest.mark.asyncio
async def test_converge_is_not_skipped_when_a_predecessor_was_restored(mock_wf: MagicMock) -> None:
    """The gate holds, so the skip branch must not be reachable."""
    wf = _wf(_retry("b2"))
    # The source run recorded b1 as completed, so the restore path schedules a
    # replay for it; that is what _prepare_retry would have loaded beforehand.
    wf._retry_source_statuses = {"b1": "completed"}
    mock_wf.execute_activity = AsyncMock(return_value={"b1": {"v": 1}})
    node = ActivityNode(node_id="b1", node_type="script", parameters={})
    graph = _converge_graph()
    result = await wf._restore_node_state(node, graph)
    from .conftest import complete_supplied_node

    assert result is not None

    await complete_supplied_node(wf, node, result, _converge_graph())
    wf.resolver.set_namespace("b2", {"v": 2, "status": "completed"})

    graph = _converge_graph()
    gate_ok = wf._are_predecessors_complete("join", graph)
    terminal = wf._all_predecessors_terminal(graph.get_predecessors("join"))

    assert not (not gate_ok and terminal), "converge would be skipped with all branches terminal"


def test_genuinely_skipped_predecessor_still_does_not_count() -> None:
    """A node that never ran is not a restored node, and must not satisfy the gate.

    Guards the fix against simply treating every skipped node as complete.
    """
    wf = _wf(_retry("b2"))
    wf.skipped_nodes.add("b1")  # never ran: no namespace, not restored
    wf.resolver.set_namespace("b2", {"v": 2, "status": "completed"})

    assert wf._are_predecessors_complete("join", _converge_graph()) is False


def test_plain_run_converge_behaviour_is_unchanged() -> None:
    """Outside a retry, skipped nodes must still not count."""
    wf = _wf()  # no retry context
    wf.skipped_nodes.add("b1")
    wf.resolver.set_namespace("b2", {"v": 2, "status": "completed"})

    assert wf._are_predecessors_complete("join", _converge_graph()) is False


# ---------------------------------------------------------------------------
# A quorum-satisfied retry converge must not wait for the branches it does not need
# ---------------------------------------------------------------------------


def _one_of_two_converge_graph() -> WorkflowGraph:
    """Build b1, b2 -> join, where join is a 1-of-2 (ANY, n_required=1) gate."""
    backend = InMemoryGraphBackend()
    _add(backend, "b1", "script")
    _add(backend, "b2", "script")
    _add(backend, "join", "converge", {"strategy": "any", "n_required": 1})
    _plain(backend, "b1", "join")
    _plain(backend, "b2", "join")
    return WorkflowGraph(backend)


def test_retry_converge_gate_proceeds_at_quorum_without_waiting_for_slow_branch() -> None:
    """A 1-of-2 retry converge proceeds as soon as one branch wins the quorum.

    Both branches failed in the source run, so retry reruns both in parallel.
    Whichever finishes first satisfies the 1-of-2 gate and must move the converge
    forward; the other branch is not needed to decide it. The restore guard used
    to gate on ``_all_predecessors_terminal``, which forces the wait to block on
    the slow branch — and the converge timeout handler cannot rescue it, because on
    the quorum path it resolves at ``n_required`` and returns without recording a
    "timed out after" reason. Gating on ``_retry_converge_gate_is_decided`` instead
    proceeds the moment the quorum is met.
    """
    wf = _wf(_retry("b1", "b2"))
    graph = _one_of_two_converge_graph()
    resolved_parameters = {"strategy": "any", "n_required": 1}
    predecessor_ids = graph.get_predecessors("join")

    # b1 won the rerun; b2 is still in flight (no namespace, not terminal).
    wf.resolver.set_namespace("b1", {"v": 1, "status": "completed"})

    # Quorum is met, so the gate is decided and the converge may proceed...
    assert wf._retry_converge_gate_is_decided("join", resolved_parameters, graph) is True
    # ...even though a branch the old guard waited for has not reached a terminal
    # state. The old ``_all_predecessors_terminal`` wait would still be blocked here.
    assert wf._all_predecessors_terminal(predecessor_ids) is False


def test_retry_converge_gate_waits_until_the_quorum_is_actually_met() -> None:
    """The fix must not proceed before any branch satisfies the gate.

    With both branches still in flight the 1-of-2 gate is undecided, so the
    converge must keep waiting rather than racing ahead to a stale restore.
    """
    wf = _wf(_retry("b1", "b2"))
    graph = _one_of_two_converge_graph()
    resolved_parameters = {"strategy": "any", "n_required": 1}

    assert wf._retry_converge_gate_is_decided("join", resolved_parameters, graph) is False


# ---------------------------------------------------------------------------
# 4. Nodes downstream of the retry point must re-execute
# ---------------------------------------------------------------------------


def test_downstream_of_retry_point_is_not_restorable() -> None:
    """Downstream of the retry point re-executes rather than restores.

    The control plane re-executes the failure point and every successor. Restoring
    a downstream node discards the retry point's fresh output, because the
    restored node never re-runs to consume it.
    """
    wf = _wf(_retry("fail_b"))

    restorable = wf._retry_restorable_nodes(_diamond_graph())

    assert "join" not in restorable
    assert "tail" not in restorable


def test_sibling_branch_of_the_retry_point_is_retained() -> None:
    """A succeeded sibling branch is retained.

    ``ok_c`` is not downstream of ``fail_b``, so the failure in the other branch
    does not invalidate it, and re-running it would repeat its side effects.
    """
    wf = _wf(_retry("fail_b"))

    assert "ok_c" in wf._retry_restorable_nodes(_diamond_graph())


def test_unrelated_upstream_node_is_still_restorable() -> None:
    """The fix must not over-reach: a node upstream of the retry point still restores."""
    backend = InMemoryGraphBackend()
    _add(backend, "prep", "script")
    _add(backend, "boom", "script")
    _plain(backend, "prep", "boom")
    graph = WorkflowGraph(backend)
    wf = _wf(_retry("boom"))

    assert "prep" in wf._retry_restorable_nodes(graph)


def test_an_unselected_failure_is_not_reported_as_skipped() -> None:
    """The failing node itself stays a failure; only its downstream is skipped.

    Regression guard. Marking the failing node skipped reported a failure as a clean
    skip and dropped the reason it failed. What has nothing to run against is
    everything downstream of it, and that is what gets skipped.
    """
    wf = _wf(_retry("b2"))
    wf._retry_source_statuses = {"b1": "failed", "b2": "failed"}
    graph = _converge_graph()
    wf._classify_unselected_branches(graph)

    # b1 failed but was not selected, so it is restored as FAILED by the replay
    # path rather than declared skipped here.
    assert "b1" not in wf.skipped_nodes
    assert wf._should_restore_node("b1", graph)
    # b2 is the selected point: it runs.
    assert "b2" not in wf.skipped_nodes
    assert "join" not in wf.skipped_nodes


def test_a_completed_converge_is_retained_but_never_restored() -> None:
    """R6c: the completed converge is not skipped, and it still has to run.

    It is excluded from the restorable set because a converge decides whether it
    has enough predecessors — restoring one would release its successors without
    that decision being made. It stays out of ``skipped_nodes`` so the R6c boundary
    holds and its descendants keep their results.
    """
    wf = _wf(_retry("unrelated"))
    wf._retry_source_statuses = {"b1": "failed", "b2": "completed", "join": "completed"}
    graph = _converge_graph()
    wf._classify_unselected_branches(graph)

    # b1 is restored as a failure, not skipped; the completed converge downstream of
    # it keeps its results under R6c either way.
    assert "b1" not in wf.skipped_nodes
    assert "join" not in wf.skipped_nodes
    # Not restorable: a converge must always evaluate its own gate.
    assert not wf._should_restore_node("join", graph)


class TestNoOverwrittenFailureNamespaceEntry:
    """The failure path must build its namespace exactly once.

    A rebase resolved this region by concatenating both sides of an additive
    conflict, which left the old assignment immediately above the new one. Nothing
    failed: the second line wins, so behaviour was correct, and neither mypy nor
    the rest of the suite could see it — an immediately overwritten local is legal
    Python and a valid call.

    Pinned here because the symptom it produces is silence. A future conflict
    resolution that put the surviving line *second* would instead drop
    ``restored_output`` and quietly return an empty namespace to a restored
    failure's successors, which is the bug the second line exists to prevent.
    """

    def test_the_namespace_comes_from_the_restored_output_builder(self) -> None:
        import inspect

        from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow

        source = inspect.getsource(OrchestratorWorkflow._handle_node_failure)
        assignments = [line.strip() for line in source.splitlines() if line.strip().startswith("namespace_entry =")]

        # Two are correct: the builder, then the empty-model fallback when it
        # returns nothing. Neither may be the plain extractor.
        assert "_extract_failure_output" not in source, (
            "the failure path must not read the plain extractor: it has no "
            f"restored_output source and overwrites what came before it. Assignments: {assignments}"
        )
        assert assignments[0] == "namespace_entry = self._failure_namespace_entry(app_error, restored_output)", (
            f"the first assignment must be the restored-output builder, got {assignments[0]}"
        )


# ---------------------------------------------------------------------------
# Converge gate messages and deferred retry-gate evaluation
# ---------------------------------------------------------------------------


def _two_branch_converge_graph(parameters: dict[str, Any] | None = None) -> WorkflowGraph:
    """Build b1, b2 -> join, where join is a converge with the given parameters."""
    backend = InMemoryGraphBackend()
    _add(backend, "b1", "script")
    _add(backend, "b2", "script")
    _add(backend, "join", "converge", parameters or {})
    _plain(backend, "b1", "join")
    _plain(backend, "b2", "join")
    return WorkflowGraph(backend)


def test_converge_failure_message_reports_a_failed_all_predecessor() -> None:
    """ALL strategy fails the gate as soon as a (non-COF) predecessor failed."""
    wf = _wf()
    graph = _two_branch_converge_graph()
    wf.failed_nodes = {"b1": "boom"}

    message = wf._converge_failure_message("join", graph.get_node("join"), graph)

    assert message is not None
    assert "b1" in message
    assert "ALL strategy" in message


def test_converge_failure_message_ignores_a_continue_on_failure_predecessor() -> None:
    """A failure marked continue-on-failure does not fail the ALL gate by itself."""
    wf = _wf()
    graph = _two_branch_converge_graph()
    wf.failed_nodes = {"b1": "boom"}
    wf._cof_failed_nodes = {"b1"}
    # The other branch has not finished, so nothing else proves a failure yet.
    assert wf._converge_failure_message("join", graph.get_node("join"), graph) is None


def test_converge_failure_message_reports_an_upstream_failure() -> None:
    """An upstream failure reached via BFS fails the ALL gate."""
    wf = _wf()
    graph = _two_branch_converge_graph()

    message = wf._converge_failure_message("join", graph.get_node("join"), graph, upstream_failure_id="way_upstream")

    assert message is not None
    assert "way_upstream" in message


def test_converge_failure_message_reports_an_unmet_quorum() -> None:
    """When every branch is terminal but the quorum is short, the gate fails."""
    wf = _wf()
    graph = _two_branch_converge_graph({"strategy": "any", "n_required": 2})
    # Both terminal: one succeeded, one skipped, so successes (1) < required (2).
    wf.resolver.set_namespace("b1", {"v": 1, "status": "completed"})
    wf.skipped_nodes.add("b2")

    message = wf._converge_failure_message("join", graph.get_node("join"), graph)

    assert message is not None
    assert "required 2 successful branches" in message


def test_evaluate_converge_failure_defers_a_retry_candidate() -> None:
    """A retry candidate's gate failure is deferred rather than failing immediately."""
    wf = _wf(_retry("join"))
    wf._retry_replay_candidates = {"join"}
    graph = _two_branch_converge_graph()
    wf.failed_nodes = {"b1": "boom"}
    fail = MagicMock()
    wf._fail_converge_node = fail  # type: ignore[method-assign]

    wf._evaluate_converge_failure("join", graph.get_node("join"), graph, pending_tasks={})

    # Deferred: the node is never failed here, it is compared against source first.
    fail.assert_not_called()


def test_evaluate_converge_failure_fails_a_plain_converge() -> None:
    """Outside a retry the gate failure is applied right away."""
    wf = _wf()
    graph = _two_branch_converge_graph()
    wf.failed_nodes = {"b1": "boom"}
    fail = MagicMock()
    wf._fail_converge_node = fail  # type: ignore[method-assign]

    wf._evaluate_converge_failure("join", graph.get_node("join"), graph)

    fail.assert_called_once()


def test_is_retry_converge_candidate_requires_both_context_and_membership() -> None:
    wf = _wf(_retry("join"))
    wf._retry_replay_candidates = {"join"}
    assert wf._is_retry_converge_candidate("join") is True
    assert wf._is_retry_converge_candidate("other") is False

    plain = _wf()  # no retry context
    plain._retry_replay_candidates = {"join"}
    assert plain._is_retry_converge_candidate("join") is False


def test_schedule_retry_converge_failure_records_reason_and_skips_a_running_node() -> None:
    """When the node is already running, the reason is recorded without rescheduling."""
    wf = _wf(_retry("join"))
    graph = _two_branch_converge_graph()
    running = object()
    pending: dict[str, Any] = {"join": running}

    wf._schedule_retry_converge_failure(
        "join",
        graph.get_node("join"),
        graph,
        pending,
        "gate failed",
        upstream_failure_id="b1",
    )

    assert wf._retry_converge_failure_reasons["join"] == "gate failed"
    assert wf._retry_converge_upstream_failures["join"] == "b1"
    # Already in flight, so the existing task is left untouched.
    assert pending["join"] is running


async def test_schedule_retry_converge_failure_schedules_the_replay() -> None:
    """A retry candidate that is not yet running is scheduled for comparison."""
    wf = _wf(_retry("join"))
    graph = _two_branch_converge_graph()
    wf._execute_node = AsyncMock(return_value={"output": {}})  # type: ignore[method-assign]
    pending: dict[str, Any] = {}

    wf._schedule_retry_converge_failure("join", graph.get_node("join"), graph, pending, "gate failed")

    assert "join" in pending
    await pending["join"]
    wf._execute_node.assert_awaited_once()


def test_retry_converge_gate_failure_reports_an_upstream_failure() -> None:
    wf = _wf()
    graph = _two_branch_converge_graph()
    message = wf._retry_converge_gate_failure("join", {"strategy": "all"}, graph, upstream_failure_id="b1")
    assert message is not None
    assert "upstream node b1 failed" in message


def test_retry_converge_gate_failure_reports_a_failed_branch() -> None:
    wf = _wf()
    graph = _two_branch_converge_graph()
    wf.failed_nodes = {"b1": "boom"}
    message = wf._retry_converge_gate_failure("join", {"strategy": "all"}, graph)
    assert message is not None
    assert "b1" in message
    assert "ALL strategy" in message


def test_retry_converge_gate_failure_waits_while_a_branch_is_in_flight() -> None:
    wf = _wf()
    graph = _two_branch_converge_graph()
    # Neither branch terminal and no failure, so the gate cannot yet be decided.
    assert wf._retry_converge_gate_failure("join", {"strategy": "all"}, graph) is None


def test_retry_converge_gate_failure_reports_an_unmet_any_quorum() -> None:
    wf = _wf()
    graph = _two_branch_converge_graph({"strategy": "any", "n_required": 2})
    wf.resolver.set_namespace("b1", {"v": 1, "status": "completed"})
    wf.skipped_nodes.add("b2")
    message = wf._retry_converge_gate_failure("join", {"strategy": "any", "n_required": 2}, graph)
    assert message is not None
    assert "required 2 successful branches, got 1" in message


def test_retry_converge_gate_failure_passes_when_the_quorum_is_met() -> None:
    wf = _wf()
    graph = _two_branch_converge_graph({"strategy": "any", "n_required": 1})
    wf.resolver.set_namespace("b1", {"v": 1, "status": "completed"})
    wf.skipped_nodes.add("b2")
    assert wf._retry_converge_gate_failure("join", {"strategy": "any", "n_required": 1}, graph) is None


def _bfs_converge_graph() -> WorkflowGraph:
    """fail_a -> mid -> join (converge); b2 -> join.

    ``mid`` sits between the failed node and the converge, so the converge is
    only reachable through BFS over a skipped/failed intermediate.
    """
    backend = InMemoryGraphBackend()
    _add(backend, "fail_a", "script")
    _add(backend, "mid", "script")
    _add(backend, "b2", "script")
    _add(backend, "join", "converge", {})
    _plain(backend, "fail_a", "mid")
    _plain(backend, "mid", "join")
    _plain(backend, "b2", "join")
    return WorkflowGraph(backend)


def test_check_converge_successors_fails_a_plain_converge_through_bfs() -> None:
    """A converge reached only through a skipped intermediate still fails."""
    wf = _wf()
    graph = _bfs_converge_graph()
    wf.failed_nodes = {"fail_a": "boom"}
    wf.skipped_nodes.add("mid")
    fail = MagicMock()
    wf._fail_converge_node = fail  # type: ignore[method-assign]

    wf._check_converge_successors("fail_a", graph, pending_tasks={})

    fail.assert_called_once()
    assert fail.call_args.args[0] == "join"


async def test_check_converge_successors_defers_a_retry_converge_through_bfs() -> None:
    """The same BFS defers the gate failure when the converge is a retry candidate."""
    wf = _wf(_retry("join"))
    wf._retry_replay_candidates = {"join"}
    graph = _bfs_converge_graph()
    wf.failed_nodes = {"fail_a": "boom"}
    wf.skipped_nodes.add("mid")
    wf._execute_node = AsyncMock(return_value={"output": {}})  # type: ignore[method-assign]
    pending: dict[str, Any] = {}

    wf._check_converge_successors("fail_a", graph, pending_tasks=pending)

    assert wf._retry_converge_failure_reasons.get("join")
    assert wf._retry_converge_upstream_failures.get("join") == "fail_a"
    assert "join" in pending
    await pending["join"]


def test_handle_converge_successor_defers_a_retry_candidate() -> None:
    """A retry candidate records its reason and is scheduled, not skipped."""
    wf = _wf(_retry("join"))
    wf._retry_replay_candidates = {"join"}
    graph = _two_branch_converge_graph()
    wf.failed_nodes = {"b1": "boom"}

    should_skip = wf._handle_converge_successor("join", graph.get_node("join"), graph, {})

    assert should_skip is False
    assert wf._retry_converge_failure_reasons.get("join")


def test_retry_converge_gate_is_decided_for_all_strategy() -> None:
    """ALL gates decide on an upstream failure, a failed branch, or all-terminal."""
    graph = _two_branch_converge_graph()
    resolved = {"strategy": "all"}

    upstream = _wf()
    upstream._retry_converge_upstream_failures = {"join": "b1"}
    assert upstream._retry_converge_gate_is_decided("join", resolved, graph) is True

    failed = _wf()
    failed.failed_nodes = {"b1": "boom"}
    assert failed._retry_converge_gate_is_decided("join", resolved, graph) is True

    waiting = _wf()
    assert waiting._retry_converge_gate_is_decided("join", resolved, graph) is False


def test_retry_converge_gate_failure_reports_an_unmet_all_quorum() -> None:
    """An ALL gate with a skipped branch fails on the short success count."""
    wf = _wf()
    graph = _two_branch_converge_graph()
    wf.resolver.set_namespace("b1", {"v": 1, "status": "completed"})
    wf.skipped_nodes.add("b2")

    message = wf._retry_converge_gate_failure("join", {"strategy": "all"}, graph)

    assert message is not None
    assert "required 2 successful branches, got 1" in message


# ---------------------------------------------------------------------------
# Comparing a retry converge against its source gate metadata
# ---------------------------------------------------------------------------


def _three_branch_converge_graph() -> WorkflowGraph:
    backend = InMemoryGraphBackend()
    for b in ("b1", "b2", "b3"):
        _add(backend, b, "script")
        _plain(backend, b, "join")
    _add(backend, "join", "converge", {})
    return WorkflowGraph(backend)


def test_metadata_match_rejects_a_non_dict_source_converge() -> None:
    wf = _wf()
    graph = _two_branch_converge_graph()
    preds = graph.get_predecessors("join")
    assert wf._retry_converge_metadata_matches({}, preds, {p: p for p in preds}, {"converge": None}, graph) is False


def test_metadata_match_rejects_a_non_terminal_source_converge() -> None:
    wf = _wf()
    graph = _two_branch_converge_graph()
    preds = graph.get_predecessors("join")
    source = {"converge": {"status": "running"}, "predecessors": {}}
    assert wf._retry_converge_metadata_matches({}, preds, {p: p for p in preds}, source, graph) is False


def test_metadata_match_rejects_a_branch_count_mismatch() -> None:
    wf = _wf()
    graph = _two_branch_converge_graph()
    preds = graph.get_predecessors("join")
    source = {
        "converge": {"status": "completed", "gate_metadata": {"total_branches": 99}},
        "predecessors": {},
    }
    assert wf._retry_converge_metadata_matches({}, preds, {p: p for p in preds}, source, graph) is False


def test_metadata_match_rejects_a_predecessor_set_mismatch() -> None:
    wf = _wf()
    graph = _two_branch_converge_graph()
    preds = graph.get_predecessors("join")
    source = {
        "converge": {"status": "completed", "gate_metadata": {"total_branches": len(preds)}},
        "predecessors": {"someone_else": {"status": "completed"}},
    }
    assert wf._retry_converge_metadata_matches({}, preds, {p: p for p in preds}, source, graph) is False


def test_metadata_match_walks_live_branches_and_detects_a_difference() -> None:
    """The full comparison walks every current and source branch.

    Each predecessor takes a different live path — completed, skipped, failed — and
    none replays (the source rows are non-restorable), so the comparison runs the
    live branch for all three and then reports a mismatch against the stale source
    metadata.
    """
    wf = _wf()
    graph = _three_branch_converge_graph()
    preds = graph.get_predecessors("join")

    wf.resolver.set_namespace("b1", {"v": 1, "status": "completed"})
    wf.skipped_nodes.add("b2")
    wf.failed_nodes = {"b3": "boom"}

    # Non-restorable source statuses force every branch down the live path.
    source = {
        "converge": {
            "status": "completed",
            "gate_metadata": {"total_branches": len(preds), "strategy": "all"},
        },
        "predecessors": {p: {"status": "pending", "result_digest": None} for p in preds},
    }

    matches = wf._retry_converge_metadata_matches({"strategy": "all"}, preds, {p: p for p in preds}, source, graph)

    assert matches is False
