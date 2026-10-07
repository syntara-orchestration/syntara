"""Source-state reads for retry-from-failure.

The mapping this returns decides which nodes a retry may skip and what each one
gets injected, so a row read that is one node too broad would seed a node the
retry is about to re-execute with the previous run's output.
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.workflow_engine.activities.retry_source_state_activity import (
    fetch_retry_source_state_activity,
)


class _Row:
    """Minimal stand-in for an ActivityExecution row."""

    def __init__(
        self,
        activity_name: str,
        status: ActivityStatus = ActivityStatus.COMPLETED,
        output: dict[str, Any] | None = None,
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


async def _run(rows: list[_Row], node_ids: list[str] | None) -> dict[str, Any]:
    completed = [r for r in rows if r.status == ActivityStatus.COMPLETED]
    if node_ids is not None:
        wanted = set(node_ids)
        completed = [r for r in completed if r.activity_name in wanted]

    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = completed
    session.exec.return_value = result

    async def mock_get_db():  # noqa: ANN202
        yield session

    with patch(
        "syntara.workflows.workflow_engine.activities.retry_source_state_activity.get_db",
        mock_get_db,
    ):
        return await fetch_retry_source_state_activity("src-1", node_ids)


@pytest.mark.asyncio
async def test_returns_status_and_payloads_for_a_node() -> None:
    """One read has to serve both classification and restoration.

    Status alone is not enough: the caller skips a node based on it and injects the
    payload, so returning both from a single read is what keeps this to one call.
    """
    rows = [_Row("step_1", output={"result": "ok"}, input_data={"query": "select 1"})]

    result = await _run(rows, ["step_1"])

    assert result["step_1"] == {
        "status": "completed",
        "input_data": {"query": "select 1"},
        "output_data": {"result": "ok"},
        "started_at": None,
        "completed_at": None,
    }


@pytest.mark.asyncio
async def test_a_node_outside_the_requested_set_is_not_returned() -> None:
    """Only requested nodes come back.

    The caller passes the nodes it classified as restorable. Returning more would
    hand back payloads for nodes the retry is going to re-execute, which is both
    wasted and the mechanism by which a re-run node could inherit stale output.
    """
    rows = [_Row("step_1"), _Row("step_2"), _Row("step_3")]

    result = await _run(rows, ["step_1", "step_3"])

    assert set(result) == {"step_1", "step_3"}


@pytest.mark.asyncio
async def test_a_node_that_did_not_complete_is_absent() -> None:
    """Absent is not the same as empty output.

    A node with no completed record has nothing to inject, so it cannot be skipped
    and must run for real. A node that completed with no output can be skipped.
    """
    rows = [_Row("ran", ActivityStatus.FAILED, None), _Row("completed_empty", output=None)]

    result = await _run(rows, ["ran", "completed_empty"])

    assert "ran" not in result
    assert result["completed_empty"]["output_data"] == {}
    assert result["completed_empty"]["status"] == "completed"


@pytest.mark.asyncio
async def test_source_timestamps_are_carried() -> None:
    """A restored node must report when the work ran, not when it was restored."""
    rows = [
        _Row(
            "step_1",
            started_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
        )
    ]

    record = (await _run(rows, ["step_1"]))["step_1"]

    assert record["started_at"] == "2026-01-01T00:00:00+00:00"
    assert record["completed_at"] == "2026-01-01T00:05:00+00:00"


@pytest.mark.asyncio
async def test_no_requested_ids_returns_the_whole_run() -> None:
    """Omitting the filter is for callers that genuinely want every node."""
    rows = [_Row("step_1"), _Row("step_2")]

    result = await _run(rows, None)

    assert set(result) == {"step_1", "step_2"}
