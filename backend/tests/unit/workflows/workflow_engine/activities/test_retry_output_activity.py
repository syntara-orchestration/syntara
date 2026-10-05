"""Stored-output resolution for retry-from-failure .

These outputs are injected into a run in place of the nodes it skipped, so a
wrong one is a silently wrong result rather than a failure.
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.workflow_engine.activities.retry_output_activity import fetch_retry_outputs_activity


class _Row:
    """Minimal stand-in for an ActivityExecution row."""

    def __init__(
        self,
        activity_name: str,
        status: ActivityStatus,
        output: dict[str, Any] | None,
        input_data: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        self.activity_name = activity_name
        self.status = status
        self.output_data = output
        self.input_data = input_data
        self.started_at = started_at
        self.completed_at = completed_at


def _mock_session(rows: list[Any]) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    session.exec.return_value = result
    return session


async def _run(rows: list[Any], node_ids: list[str]) -> dict[str, dict[str, Any]]:
    # The mock session does not execute SQL, so the activity's
    # ``status == COMPLETED`` predicate is applied here to keep these tests
    # meaningful. The integration test for this activity covers the real query.
    session = _mock_session([row for row in rows if row.status == ActivityStatus.COMPLETED])

    async def mock_get_db():  # noqa: ANN202
        yield session

    with patch(
        "syntara.workflows.workflow_engine.activities.retry_output_activity.get_db",
        mock_get_db,
    ):
        return await fetch_retry_outputs_activity("src-1", node_ids)


@pytest.mark.asyncio
async def test_returns_completed_output_for_a_node() -> None:
    """A completed node's stored output is what gets injected in its place."""
    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"})]

    assert await _run(rows, ["step_1"]) == {
        "step_1": {"input_data": {}, "output_data": {"result": "ok"}, "started_at": None, "completed_at": None}
    }


@pytest.mark.asyncio
async def test_only_requested_nodes_are_returned() -> None:
    """Unrelated rows in the execution must not be pulled in."""
    rows = [
        _Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"}),
        _Row("step_2", ActivityStatus.COMPLETED, {"result": "other"}),
    ]

    assert await _run(rows, ["step_1"]) == {
        "step_1": {"input_data": {}, "output_data": {"result": "ok"}, "started_at": None, "completed_at": None}
    }


@pytest.mark.asyncio
async def test_node_with_no_completed_activity_is_absent_not_empty() -> None:
    """Absent distinguishes "never ran" from "ran and produced nothing".

    A node that never completed cannot be skipped, because there would be nothing
    to inject. Returning an empty dict for it would let the caller skip it and
    leave downstream expressions unresolved.
    """
    rows = [_Row("step_1", ActivityStatus.FAILED, None)]

    assert await _run(rows, ["step_1"]) == {}


@pytest.mark.asyncio
async def test_completed_node_with_no_output_returns_empty_dict() -> None:
    """A node that completed but produced nothing is an empty output, not absent."""
    rows = [_Row("step_1", ActivityStatus.COMPLETED, None)]

    assert await _run(rows, ["step_1"]) == {
        "step_1": {"input_data": {}, "output_data": {}, "started_at": None, "completed_at": None}
    }


@pytest.mark.asyncio
async def test_iteration_suffixed_request_resolves_to_the_base_node() -> None:
    """``step_1#iter-2`` asks for node step_1, and gets step_1's output."""
    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"})]

    assert await _run(rows, ["step_1#iter-2"]) == {
        "step_1": {"input_data": {}, "output_data": {"result": "ok"}, "started_at": None, "completed_at": None}
    }


@pytest.mark.asyncio
async def test_loop_iteration_rows_resolve_to_the_most_recent_one() -> None:
    """The base node id maps to its latest completed iteration."""
    rows = [
        _Row("step_1", ActivityStatus.COMPLETED, {"result": "iter-0"}),
        _Row("step_1#iter-1", ActivityStatus.COMPLETED, {"result": "iter-1"}),
    ]

    assert await _run(rows, ["step_1"]) == {
        "step_1": {"input_data": {}, "output_data": {"result": "iter-1"}, "started_at": None, "completed_at": None}
    }


@pytest.mark.asyncio
async def test_empty_request_short_circuits() -> None:
    """Nothing requested means no query and no result."""
    assert await _run([], []) == {}


@pytest.mark.asyncio
async def test_blank_ids_are_ignored() -> None:
    """Whitespace-only ids are not node ids."""
    assert await _run([], ["", "   "]) == {}


@pytest.mark.asyncio
async def test_ids_are_whitespace_trimmed() -> None:
    """A padded id still resolves to its node."""
    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"})]

    assert await _run(rows, ["  step_1  "]) == {
        "step_1": {"input_data": {}, "output_data": {"result": "ok"}, "started_at": None, "completed_at": None}
    }


@pytest.mark.asyncio
async def test_oversized_result_is_refused_rather_than_truncated() -> None:
    """An oversized payload raises instead of being silently cut.

    The engine would otherwise inject a truncated value that the source run never
    produced, which is worse than refusing the retry: a truncated output is
    indistinguishable from a real one downstream.
    """
    from syntara.core.exceptions import SafeValueError

    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"blob": "x" * 2_000_000})]

    with pytest.raises(SafeValueError, match="over the"):
        await _run(rows, ["step_1"])


@pytest.mark.asyncio
async def test_size_within_the_limit_is_returned() -> None:
    """A payload under the limit passes through untouched."""
    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"blob": "x" * 1000})]

    result = await _run(rows, ["step_1"])

    assert result["step_1"]["output_data"]["blob"] == "x" * 1000


@pytest.mark.asyncio
async def test_returns_stored_input_alongside_output() -> None:
    """Both halves of the stored record come back.

    A restored node has to be indistinguishable from one that executed, and the
    sync service resolves input through ``get_activity_input``, which reads
    ``node_inputs``. Returning output alone leaves drill-down with a blank input.
    """
    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"}, input_data={"query": "select 1"})]

    result = await _run(rows, ["step_1"])

    assert result["step_1"] == {
        "input_data": {"query": "select 1"},
        "output_data": {"result": "ok"},
        "started_at": None,
        "completed_at": None,
    }


@pytest.mark.asyncio
async def test_returns_source_timestamps_as_iso_strings() -> None:
    """The source row's timestamps come back as ISO strings.

    The replayed node is recorded through the normal sync path with this run's
    event times; the sync service applies these source timestamps over them so the
    row reports when the work actually ran rather than the restore time.
    """
    started = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    completed = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    rows = [
        _Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"}, started_at=started, completed_at=completed),
    ]

    result = await _run(rows, ["step_1"])

    assert result["step_1"]["started_at"] == started.isoformat()
    assert result["step_1"]["completed_at"] == completed.isoformat()


@pytest.mark.asyncio
async def test_node_with_no_stored_input_returns_empty_not_missing() -> None:
    """A node with no recorded input yields ``{}``, so the key is always present.

    The caller writes ``node_inputs[node.id]`` unconditionally; a missing key
    would have to be special-cased for no benefit.
    """
    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"})]

    result = await _run(rows, ["step_1"])

    assert result["step_1"]["input_data"] == {}
