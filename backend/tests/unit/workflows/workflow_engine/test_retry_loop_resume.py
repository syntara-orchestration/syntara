"""Per-iteration loop resume for retry-from-failure .

A retry that re-enters a loop must resume at the failed iteration rather than
restarting from zero. Restarting repeats the side effects of every iteration that
already succeeded, which the restart design treats as a correctness risk.
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.workflow_engine.activities.retry_output_activity import _rebuild_iteration_results
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode
from syntara.workflows.workflow_engine.models.workflow_definition import LoopType
from tests.unit.workflows.workflow_engine.test_retry_classification import _loop_graph, _retry


def _make_workflow(retry_context: dict[str, Any] | None = None) -> OrchestratorWorkflow:
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.retry_context = retry_context or {}
    wf._retry_restorable_cache = None
    wf._restored_nodes = set()
    wf._resumed_loops = set()
    wf.loop_state = {}
    wf.loop_body_map = {}
    wf.loop_iteration_results = {}
    wf._runtime_settings = {}
    return wf


# ---------------------------------------------------------------------------
# _rebuild_iteration_results: fidelity with the engine's own accumulation
# ---------------------------------------------------------------------------


def test_rebuild_matches_engine_accumulation_shape() -> None:
    """Rebuilding from stored rows reproduces what _clear_loop_body assembles.

    _clear_loop_body appends every field of a body node's resolver namespace, and
    that namespace is ``{**output, "status": "completed"}``. ``output_data`` in the
    database is the bare activity output and never carries that synthetic key, so
    it must be re-added or the rebuilt aggregation silently differs from the
    original run's.
    """
    completed = [
        (0, "body_a", {"receipt": "r0"}),
        (1, "body_a", {"receipt": "r1"}),
        (2, "body_a", {"receipt": "r2"}),
    ]

    rebuilt = _rebuild_iteration_results(completed, resume_iteration=2)

    assert rebuilt == {"body_a.receipt": ["r0", "r1"], "body_a.status": ["completed", "completed"]}


def test_rebuild_is_ragged_not_zipped() -> None:
    """A node returning different fields per iteration stays ragged.

    Zipping against a fixed iteration range would misalign the list, so a later
    iteration's value would be attributed to the wrong position.
    """
    completed: list[tuple[int, str, dict[str, Any]]] = [
        (0, "body_a", {"receipt": "r0"}),
        (1, "body_a", {"amount": 42}),
        (2, "body_a", {"receipt": "r2", "amount": 43}),
    ]

    rebuilt = _rebuild_iteration_results(completed, resume_iteration=3)

    assert rebuilt["body_a.receipt"] == ["r0", "r2"]
    assert rebuilt["body_a.amount"] == [42, 43]


def test_rebuild_excludes_the_failed_iteration_and_later() -> None:
    """Only iterations strictly below the resume point are restored."""
    completed = [(index, "body_a", {"receipt": f"r{index}"}) for index in range(5)]

    rebuilt = _rebuild_iteration_results(completed, resume_iteration=2)

    assert rebuilt["body_a.receipt"] == ["r0", "r1"]


def test_rebuild_orders_by_node_then_iteration() -> None:
    """Rows can arrive in any order; each node's list must stay iteration-ordered."""
    completed = [
        (1, "body_b", {"v": "b1"}),
        (0, "body_a", {"v": "a0"}),
        (1, "body_a", {"v": "a1"}),
        (0, "body_b", {"v": "b0"}),
    ]

    rebuilt = _rebuild_iteration_results(completed, resume_iteration=2)

    assert rebuilt["body_a.v"] == ["a0", "a1"]
    assert rebuilt["body_b.v"] == ["b0", "b1"]


def test_rebuild_of_nothing_is_empty() -> None:
    """Resuming at iteration 0 leaves no completed iterations to restore."""
    assert _rebuild_iteration_results([(0, "body_a", {"v": 1})], resume_iteration=0) == {}


# ---------------------------------------------------------------------------
# _maybe_resume_loop: which loop gets resumed, and with what
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_wf() -> Generator[MagicMock, None, None]:
    """Patch the Temporal workflow module so execute_activity is awaitable."""
    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as patched:
        patched.logger = MagicMock()
        yield patched


@pytest.mark.asyncio
async def test_loop_is_resumed_at_the_failed_iteration(mock_wf: MagicMock) -> None:
    """The loop counter starts at the failed iteration, not zero."""
    wf = _make_workflow(_retry("body_a"))
    node = _loop_node()
    mock_wf.execute_activity = AsyncMock(
        return_value={"loop_1": {"resume_iteration": 3, "iteration_results": {"body_a.receipt": ["r0", "r1", "r2"]}}}
    )

    await wf._maybe_resume_loop(node, _loop_graph())

    source, loops = mock_wf.execute_activity.call_args.kwargs["args"]
    assert source == "src-1"
    assert loops == {"loop_1": ["body_a"]}

    assert wf.loop_state["loop_1"].current_index == 3
    assert wf.loop_iteration_results["loop_1"]["body_a.receipt"] == ["r0", "r1", "r2"]


@pytest.mark.asyncio
async def test_loop_resume_seeds_the_synthetic_status_key(mock_wf: MagicMock) -> None:
    """The seeded aggregation carries ``status``, matching a live run."""
    wf = _make_workflow(_retry("body_a"))
    node = _loop_node()
    mock_wf.execute_activity = AsyncMock(
        return_value={
            "loop_1": {
                "resume_iteration": 2,
                "iteration_results": {"body_a.receipt": ["r0", "r1"], "body_a.status": ["completed", "completed"]},
            }
        }
    )

    await wf._maybe_resume_loop(node, _loop_graph())

    assert wf.loop_iteration_results["loop_1"]["body_a.status"] == ["completed", "completed"]


@pytest.mark.asyncio
async def test_loop_with_no_retry_point_in_its_body_is_not_resumed(mock_wf: MagicMock) -> None:
    """A loop whose body has no retry point runs from iteration 0 as usual."""
    mock_wf.execute_activity = AsyncMock(side_effect=AssertionError("must not be called"))

    # step_2 is outside loop_1's body.
    wf = _make_workflow(_retry("step_2"))
    await wf._maybe_resume_loop(_loop_node(), _loop_graph())

    assert wf.loop_state == {}
    assert wf.loop_iteration_results == {}


@pytest.mark.asyncio
async def test_non_retry_run_resumes_nothing(mock_wf: MagicMock) -> None:
    """A normal run must not touch loop state at all."""
    mock_wf.execute_activity = AsyncMock(side_effect=AssertionError("must not be called"))

    wf = _make_workflow()
    await wf._maybe_resume_loop(_loop_node(), _loop_graph())

    assert wf.loop_state == {}


@pytest.mark.asyncio
async def test_source_run_reports_no_failure_leaves_state_untouched(mock_wf: MagicMock) -> None:
    """A loop with nothing to resume must not create half-built state."""
    wf = _make_workflow(_retry("body_a"))
    node = _loop_node()
    mock_wf.execute_activity = AsyncMock(return_value={})

    await wf._maybe_resume_loop(node, _loop_graph())

    assert wf.loop_state == {}


@pytest.mark.asyncio
async def test_loop_is_resumed_at_most_once(mock_wf: MagicMock) -> None:
    """The loop is dispatched once per iteration, so resume must not re-run.

    Re-fetching on a later iteration would re-append the same results into
    ``loop_iteration_results`` and double every restored field.
    """
    wf = _make_workflow(_retry("body_a"))
    node = _loop_node()
    mock_wf.execute_activity = AsyncMock(
        return_value={"loop_1": {"resume_iteration": 1, "iteration_results": {"body_a.receipt": ["r0"]}}}
    )

    graph = _loop_graph()
    await wf._maybe_resume_loop(node, graph)
    await wf._maybe_resume_loop(node, graph)

    assert mock_wf.execute_activity.await_count == 1
    assert wf.loop_iteration_results["loop_1"]["body_a.receipt"] == ["r0"]


@pytest.mark.asyncio
async def test_missing_graph_warns_and_does_not_silently_restart(mock_wf: MagicMock) -> None:
    """Without a graph the loop body cannot be resolved, and that must be loud."""
    wf = _make_workflow(_retry("body_a"))
    mock_wf.execute_activity = AsyncMock(side_effect=AssertionError("must not be called"))

    await wf._maybe_resume_loop(_loop_node(), None)

    assert wf.loop_state == {}
    assert mock_wf.logger.warning.called


def _loop_node() -> ActivityNode:
    from syntara.workflows.workflow_engine.graph import ActivityNode

    return ActivityNode(
        node_id="loop_1",
        node_type="loop",
        parameters={"type": LoopType.FOR_EACH, "items": ["a", "b", "c", "d"]},
    )


# ---------------------------------------------------------------------------
# Resume-point selection: the off-by-one the design calls out
# ---------------------------------------------------------------------------


def _source_rows(*, failed_at: list[int], completed_upto: int) -> list[tuple[int, str, dict[str, Any]]]:
    """Build the rows a source run leaves behind, one per iteration."""
    rows: list[tuple[int, str, dict[str, Any]]] = []
    for index in range(completed_upto + 1):
        if index in failed_at:
            rows.append((index, "body_a", {}))
        else:
            rows.append((index, "body_a", {"receipt": f"r{index}"}))
    return rows


def test_failed_iteration_is_the_last_one_resumes_there_only() -> None:
    """When the failed iteration is the last, only it re-runs."""
    # Iterations 0-2 completed, iteration 3 failed and stopped the loop.
    completed = _source_rows(failed_at=[], completed_upto=2)
    resume_iteration = 3

    rebuilt = _rebuild_iteration_results(completed, resume_iteration=resume_iteration)

    assert rebuilt["body_a.receipt"] == ["r0", "r1", "r2"]
    # Iterations 0, 1, 2 are skipped and only 3 runs.
    assert len(rebuilt["body_a.receipt"]) == resume_iteration


def test_iteration_zero_failed_resumes_from_zero() -> None:
    """A failure on iteration 0 leaves nothing to skip, so the loop re-runs whole."""
    completed: list[tuple[int, str, dict[str, Any]]] = []
    resume_iteration = 0

    rebuilt = _rebuild_iteration_results(completed, resume_iteration=resume_iteration)

    assert rebuilt == {}
    assert resume_iteration == 0


def test_continue_on_failure_earlier_failure_does_not_drag_resume_back() -> None:
    """A tolerated early failure must not cause its iterations to run again.

    A ``continue_on_failure`` body node can fail on an early iteration while the
    loop carries on, leaving several FAILED rows for one loop. Only the last one
    stopped the workflow. Resuming from the earliest would re-run iterations that
    already completed and repeat their side effects, which is the worst outcome
    this design can produce.
    """
    completed: list[tuple[int, str, dict[str, Any]]] = [
        (0, "body_a", {"receipt": "r0"}),  # completed
        (2, "body_a", {"receipt": "r2"}),  # completed
    ]
    # Iteration 1 failed but was tolerated (continue_on_failure); iteration 3
    # failed and stopped the loop.
    failed_indices = [1, 3]

    resume_iteration = max(failed_indices)

    completed_rows = completed
    rebuilt = _rebuild_iteration_results(completed_rows, resume_iteration=resume_iteration)
    # Iteration 1's side effect already happened; it is not replayed.
    assert rebuilt["body_a.receipt"] == ["r0", "r2"]
    assert 1 not in [int(r.split("r")[1]) for r in rebuilt["body_a.receipt"]]
