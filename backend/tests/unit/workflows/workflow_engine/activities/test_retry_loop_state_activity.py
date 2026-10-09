"""Per-iteration state for resuming a loop on retry.

A loop body node is one execution per iteration, so its results are a list keyed by
iteration rather than a single record. These cover the two rules that are easy to get
wrong: where the loop resumes, and whether the rebuilt aggregation matches the shape
the engine produced on the original run.
"""

from typing import Any

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.workflow_engine.activities.retry_node_replay_activity import (
    _LOOP_ITERATION_STATUSES,
    _exceeds_size_limit,
    _rebuild_iteration_results,
    fetch_retry_loop_state_activity,
)


class _Row:
    """Minimal stand-in for an ActivityExecution row."""

    def __init__(
        self,
        name: str,
        status: ActivityStatus,
        iteration: int | None,
        output: dict[str, Any] | None = None,
    ) -> None:
        self.activity_name = name
        self.status = status
        self.iteration = iteration
        self.output_data = output


def _row(
    name: str,
    status: ActivityStatus,
    iteration: int | None,
    output: dict[str, Any] | None = None,
) -> _Row:
    return _Row(name, status, iteration, output)


def _run(rows: list[Any], loops: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    """Run the activity over an in-memory row set."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    kept = [r for r in rows if r.status in _LOOP_ITERATION_STATUSES]

    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = kept
    session.exec.return_value = result

    async def get_db():  # noqa: ANN202
        yield session

    with patch(
        "syntara.workflows.workflow_engine.activities.retry_node_replay_activity.get_db",
        get_db,
    ):
        return asyncio.run(fetch_retry_loop_state_activity("src-1", loops))


class TestResumePoint:
    """Where a resumed loop restarts."""

    def test_resumes_at_the_failed_iteration(self) -> None:
        rows = [
            _row("body_a", ActivityStatus.COMPLETED, 0, {"v": "a0"}),
            _row("body_a#iter-1", ActivityStatus.FAILED, 1, None),
        ]

        assert _run(rows, {"loop_1": ["body_a"]})["loop_1"]["resume_iteration"] == 1

    def test_resumes_at_the_last_failed_iteration_not_the_first(self) -> None:
        """A tolerated early failure must not be re-run.

        A continue_on_failure body node can fail on an early iteration while the loop
        carries on, so the source run holds several FAILED rows for one loop. Only the
        last one stopped the workflow; earlier failures were tolerated and their side
        effects already happened. Resuming from the earliest would repeat them.
        """
        rows = [
            _row("body_a", ActivityStatus.FAILED, 0, None),
            _row("body_a#iter-1", ActivityStatus.COMPLETED, 1, {"v": "a1"}),
            _row("body_a#iter-2", ActivityStatus.COMPLETED, 2, {"v": "a2"}),
            _row("body_a#iter-3", ActivityStatus.FAILED, 3, None),
        ]

        assert _run(rows, {"loop_1": ["body_a"]})["loop_1"]["resume_iteration"] == 3

    def test_a_loop_with_no_failure_is_absent(self) -> None:
        """Nothing failed inside it, so there is nothing to resume."""
        rows = [_row("body_a", ActivityStatus.COMPLETED, 0, {"v": "a0"})]

        assert _run(rows, {"loop_1": ["body_a"]}) == {}

    def test_a_node_outside_the_loop_is_ignored(self) -> None:
        """An identically-named node elsewhere must not set the resume point."""
        rows = [
            _row("elsewhere", ActivityStatus.FAILED, 5, None),
            _row("body_a", ActivityStatus.COMPLETED, 0, {"v": "a0"}),
        ]

        assert _run(rows, {"loop_1": ["body_a"]}) == {}

    def test_no_loops_is_a_no_op(self) -> None:
        assert _run([_row("body_a", ActivityStatus.FAILED, 0, None)], {}) == {}


class TestIterationResultsFidelity:
    """The rebuilt aggregation has to match what the engine produced originally."""

    def test_the_synthetic_status_key_is_re_added(self) -> None:
        """The engine's namespace entry carries status; ``output_data`` never does.

        Without re-adding it the rebuilt aggregation silently lacks
        ``"{node}.status"``, and a loop body reading that gets nothing.
        """
        rows = [
            _row("body_a", ActivityStatus.COMPLETED, 0, {"receipt": "r0"}),
            _row("body_a#iter-1", ActivityStatus.FAILED, 1, None),
        ]

        results = _run(rows, {"loop_1": ["body_a"]})["loop_1"]["iteration_results"]

        assert results["body_a.receipt"] == ["r0"]
        assert results["body_a.status"] == ["completed"]

    def test_only_iterations_below_the_resume_point_are_rebuilt(self) -> None:
        rows = [
            _row("body_a", ActivityStatus.COMPLETED, 0, {"v": "a0"}),
            _row("body_a#iter-1", ActivityStatus.COMPLETED, 1, {"v": "a1"}),
            _row("body_a#iter-2", ActivityStatus.FAILED, 2, None),
        ]

        results = _run(rows, {"loop_1": ["body_a"]})["loop_1"]["iteration_results"]

        assert results["body_a.v"] == ["a0", "a1"]

    def test_lists_stay_ragged(self) -> None:
        """A node returning different fields per iteration keeps its original shape.

        Zipping against a fixed iteration range would pad the shorter list and
        misalign every value after the gap.
        """
        results = _rebuild_iteration_results(
            [
                (0, "body_a", {"receipt": "r0"}),
                (1, "body_a", {"receipt": "r1", "extra": "e1"}),
            ],
            resume_iteration=2,
        )

        assert results["body_a.receipt"] == ["r0", "r1"]
        assert results["body_a.extra"] == ["e1"]
        assert results["body_a.status"] == ["completed", "completed"]

    def test_results_are_ordered_by_node_then_iteration(self) -> None:
        results = _rebuild_iteration_results(
            [
                (1, "body_b", {"v": "b1"}),
                (0, "body_a", {"v": "a0"}),
                (0, "body_b", {"v": "b0"}),
            ],
            resume_iteration=2,
        )

        assert results["body_a.v"] == ["a0"]
        assert results["body_b.v"] == ["b0", "b1"]


class TestAggregateSizeGuard:
    """The cost is in the whole per-loop payload, not in one iteration."""

    def test_a_large_aggregate_is_refused_rather_than_truncated(self) -> None:
        rows = [
            _row("body_a#iter-0", ActivityStatus.COMPLETED, 0, {"blob": "x" * 2_000_000}),
            _row("body_a#iter-1", ActivityStatus.FAILED, 1, None),
        ]

        with pytest.raises(SafeValueError, match="exceeds"):
            _run(rows, {"loop_1": ["body_a"]})

    def test_a_payload_within_the_limit_is_returned(self) -> None:
        rows = [
            _row("body_a#iter-0", ActivityStatus.COMPLETED, 0, {"blob": "x" * 1000}),
            _row("body_a#iter-1", ActivityStatus.FAILED, 1, None),
        ]

        state = _run(rows, {"loop_1": ["body_a"]})

        assert state["loop_1"]["iteration_results"]["body_a.blob"] == ["x" * 1000]

    def test_the_limit_is_measured_on_serialized_json_not_repr(self) -> None:
        """``len(str(...))`` measures Python's repr, which is a different number."""
        assert _exceeds_size_limit({"k": ["x" * 100]}) is False
