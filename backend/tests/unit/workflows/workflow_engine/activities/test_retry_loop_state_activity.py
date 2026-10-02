"""Resume-point selection for retry loop state .

The resume iteration decides which iterations are skipped. Choosing it wrong is
the main correctness risk here in either direction: too early
replays side effects that already happened, too late skips the iteration that
actually failed.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.workflow_engine.activities.retry_output_activity import fetch_retry_loop_state_activity


class _Row:
    """Minimal stand-in for an ActivityExecution row."""

    def __init__(
        self,
        activity_name: str | None,
        status: ActivityStatus,
        iteration: int | None,
        output: dict[str, Any] | None,
    ) -> None:
        self.activity_name = activity_name
        self.status = status
        self.iteration = iteration
        self.output_data = output


def _mock_session(rows: list[Any]) -> AsyncMock:
    session = AsyncMock()
    # exec is awaited, but ``.all()`` on the result is synchronous.
    result = MagicMock()
    result.all.return_value = rows
    session.exec.return_value = result
    return session


async def _run(rows: list[Any], loops: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    session = _mock_session(rows)

    async def mock_get_db():  # noqa: ANN202
        yield session

    # The activity imports get_db into its own module namespace, so that is the
    # binding that has to be replaced.
    with patch(
        "syntara.workflows.workflow_engine.activities.retry_output_activity.get_db",
        mock_get_db,
    ):
        return await fetch_retry_loop_state_activity("src-1", loops)


@pytest.mark.asyncio
async def test_resumes_at_the_last_failed_iteration() -> None:
    """The iteration that stopped the loop is the one being retried."""
    rows = [
        _Row("body_a", ActivityStatus.COMPLETED, 0, {"receipt": "r0"}),
        _Row("body_a#iter-1", ActivityStatus.COMPLETED, 1, {"receipt": "r1"}),
        _Row("body_a#iter-2", ActivityStatus.FAILED, 2, None),
    ]

    result = await _run(rows, {"loop_1": ["body_a"]})

    assert result["loop_1"]["resume_iteration"] == 2
    assert result["loop_1"]["iteration_results"]["body_a.receipt"] == ["r0", "r1"]


@pytest.mark.asyncio
async def test_tolerated_early_failure_does_not_drag_the_resume_point_back() -> None:
    """A continue_on_failure iteration that the loop moved past is not replayed.

    The source run holds two FAILED rows: an early tolerated one and the later one
    that actually stopped the loop. Resuming from the earliest would re-run an
    iteration whose side effect already happened.
    """
    rows = [
        _Row("body_a", ActivityStatus.COMPLETED, 0, {"receipt": "r0"}),
        _Row("body_a#iter-1", ActivityStatus.FAILED, 1, None),
        _Row("body_a#iter-2", ActivityStatus.COMPLETED, 2, {"receipt": "r2"}),
        _Row("body_a#iter-3", ActivityStatus.FAILED, 3, None),
    ]

    result = await _run(rows, {"loop_1": ["body_a"]})

    assert result["loop_1"]["resume_iteration"] == 3
    # Iteration 1 is not replayed: r0 and r2 are restored, not r0/r1/r2.
    assert result["loop_1"]["iteration_results"]["body_a.receipt"] == ["r0", "r2"]


@pytest.mark.asyncio
async def test_restored_results_include_the_synthetic_status_key() -> None:
    """Rebuilt aggregation matches a live run, which stores ``status`` per iteration."""
    rows = [
        _Row("body_a", ActivityStatus.COMPLETED, 0, {"receipt": "r0"}),
        _Row("body_a#iter-1", ActivityStatus.FAILED, 1, None),
    ]

    result = await _run(rows, {"loop_1": ["body_a"]})

    assert result["loop_1"]["iteration_results"]["body_a.status"] == ["completed"]


@pytest.mark.asyncio
async def test_loop_with_no_failure_is_not_reported() -> None:
    """A loop that completed outright needs no resume state."""
    rows = [_Row("body_a", ActivityStatus.COMPLETED, 0, {"receipt": "r0"})]

    result = await _run(rows, {"loop_1": ["body_a"]})

    assert result == {}


@pytest.mark.asyncio
async def test_rows_outside_the_body_are_ignored() -> None:
    """An identically-named node elsewhere must not contribute."""
    rows = [
        _Row("body_a", ActivityStatus.COMPLETED, 0, {"receipt": "r0"}),
        _Row("other_node", ActivityStatus.FAILED, 5, None),
    ]

    result = await _run(rows, {"loop_1": ["body_a"]})

    assert result == {}


@pytest.mark.asyncio
async def test_missing_iteration_column_defaults_to_zero() -> None:
    """The original row carries iteration=0; a null must not shift the index."""
    rows = [
        _Row("body_a", ActivityStatus.COMPLETED, None, {"receipt": "r0"}),
        _Row("body_a#iter-1", ActivityStatus.FAILED, 1, None),
    ]

    result = await _run(rows, {"loop_1": ["body_a"]})

    assert result["loop_1"]["resume_iteration"] == 1
    assert result["loop_1"]["iteration_results"]["body_a.receipt"] == ["r0"]


@pytest.mark.asyncio
async def test_null_activity_name_is_skipped() -> None:
    """activity_name is nullable in the schema and must not raise."""
    rows = [
        _Row(None, ActivityStatus.COMPLETED, 0, {}),
        _Row("body_a", ActivityStatus.FAILED, 1, None),
    ]

    result = await _run(rows, {"loop_1": ["body_a"]})

    assert result["loop_1"]["resume_iteration"] == 1


@pytest.mark.asyncio
async def test_no_loops_short_circuits() -> None:
    """Nothing to look up means no query and no result."""
    assert await _run([], {}) == {}
