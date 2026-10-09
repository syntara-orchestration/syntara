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


def _two_loop_graph() -> WorkflowGraph:
    """loop_a { a_body } and loop_b { b_body }, independent."""
    backend = InMemoryGraphBackend()
    _add(backend, "loop_a", "loop")
    _add(backend, "a_body", "script")
    _add(backend, "loop_b", "loop")
    _add(backend, "b_body", "script")
    backend.add_edge("loop_a", "a_body", {"from_port": "iterate"})
    backend.add_edge("loop_b", "b_body", {"from_port": "iterate"})
    return WorkflowGraph(backend)


def _wf(retry_context: dict[str, Any] | None = None) -> OrchestratorWorkflow:
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.retry_context = retry_context or {}
    wf._retry_restorable_cache = None
    wf._retry_replay_candidates = set()
    wf._restored_node_timestamps = {}
    wf._restored_node_statuses = {}
    wf._restored_node_ports = {}
    wf._restored_node_outputs = {}
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
# 1. Loop body detection must walk the whole body
# ---------------------------------------------------------------------------


def test_loop_body_includes_every_body_node() -> None:
    """Every body node is found, not just the first.

    Only the loop's own exit edge carries ``from_port``; filtering on it at every
    hop stops the walk after one node.
    """
    assert OrchestratorWorkflow._loop_body_node_ids(_loop_body_graph()) == {"body_a", "body_b", "body_c"}


def test_loop_body_does_not_include_nodes_after_the_loop() -> None:
    """The walk must stop at the loop's complete port."""
    body = OrchestratorWorkflow._loop_body_node_ids(_loop_body_graph())

    assert "step_2" not in body
    assert "loop_1" not in body


def test_multi_node_body_is_not_restorable() -> None:
    """A multi-node loop body is not restorable.

    Regression guard: body_b and body_c were classified restorable and injected
    as a single scalar.
    """
    wf = _wf(_retry("step_2"))

    restorable = wf._retry_restorable_nodes(_loop_body_graph())

    assert restorable.isdisjoint({"body_a", "body_b", "body_c"})


# ---------------------------------------------------------------------------
# 2. Loop body lookup must be scoped to the loop being resumed
# ---------------------------------------------------------------------------


def test_loop_body_is_scoped_per_loop() -> None:
    """Every loop body is collected, and no loop adopts only one of them."""
    graph = _two_loop_graph()

    # Loop resume is a separate piece of work, so this now answers one question
    # only: which nodes must never be replayed as if they were ordinary nodes.
    # Both bodies are excluded, because a body node is one execution per
    # iteration and a single stored output cannot stand in for all of them.
    assert OrchestratorWorkflow._loop_body_node_ids(graph) == {"a_body", "b_body"}


# ---------------------------------------------------------------------------
# 3. A restored predecessor must satisfy a converge gate
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
    mock_wf.execute_activity = AsyncMock(return_value={"b1": {"v": 1}})
    node = ActivityNode(node_id="b1", node_type="script", parameters={})
    result = await wf._restore_node_output(node)
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
    mock_wf.execute_activity = AsyncMock(return_value={"b1": {"v": 1}})
    node = ActivityNode(node_id="b1", node_type="script", parameters={})
    result = await wf._restore_node_output(node)
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


def test_definition_validator_and_retry_share_loop_body_membership() -> None:
    """Raw edges and built-graph adapters agree across plain and feedback edges."""
    from syntara.workflows.validators.template_expressions import _identify_loop_body_nodes

    definition = {
        "nodes": [{"id": "loop_1", "type": "loop"}],
        "edges": [
            {"from": "trigger", "to": "loop_1"},
            {"from": "loop_1", "to": "body_a", "from_port": "iterate"},
            {"from": "body_a", "to": "body_b"},
            {"from": "body_b", "to": "body_c"},
            {"from": "body_c", "to": "loop_1", "to_port": "iterate"},
            {"from": "loop_1", "to": "step_2", "from_port": "complete"},
        ],
    }
    assert (
        set(_identify_loop_body_nodes(definition))
        == _wf()._loop_body_node_ids(_loop_body_graph())
        == {
            "body_a",
            "body_b",
            "body_c",
        }
    )
