"""Source-state reads for retry-from-failure.

The mapping this returns decides which nodes a retry may skip, so a row read that
is one node too broad seeds a node the retry is about to re-execute with the
previous run's state.
"""

from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.workflow_engine.activities.retry_node_replay_activity import (
    fetch_retry_source_state_activity,
)


async def _run(
    rows: list[tuple[str | None, str, str | None]],
    *,
    trigger_timestamps: list[tuple[str | None, datetime | None, datetime | None]] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[Any]]:
    """Run the activity, returning its state mapping and projected SQL statements."""
    session = AsyncMock()
    status_result = MagicMock()
    # Preserve display names to ensure source identity comes only from the
    # canonical Temporal ID.
    status_result.all.return_value = [(status, temporal_id) for _, status, temporal_id in rows]
    trigger_result = MagicMock()
    trigger_result.all.return_value = trigger_timestamps or []
    session.exec.side_effect = [status_result, trigger_result]

    async def mock_get_db():  # noqa: ANN202
        yield session

    with patch(
        "syntara.workflows.workflow_engine.activities.retry_node_replay_activity.get_db",
        mock_get_db,
    ):
        states = await fetch_retry_source_state_activity("src-1")

    queries = [call.args[0] for call in session.exec.await_args_list]
    return states, queries


@pytest.mark.asyncio
async def test_returns_the_status_for_a_node() -> None:
    states, _ = await _run([("step_1", "completed", "step_1")])

    assert states["activity_statuses"] == {"step_1": "completed"}
    assert states["temporal_activity_statuses"] == {"step_1": "completed"}


@pytest.mark.asyncio
async def test_returns_timestamps_keyed_by_temporal_activity_id() -> None:
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    completed_at = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    states, queries = await _run(
        [("trigger", "completed", "trigger")],
        trigger_timestamps=[("trigger", started_at, completed_at)],
    )

    assert states["temporal_activity_timestamps"] == {
        "trigger": {
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
        }
    }
    assert "node_type" in str(queries[1])
    assert "started_at" in str(queries[1])
    assert "completed_at" in str(queries[1])


@pytest.mark.asyncio
async def test_keeps_missing_times_and_ignores_rows_without_temporal_activity_id() -> None:
    states, _ = await _run(
        [],
        trigger_timestamps=[
            ("trigger", None, None),
            (None, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, 0, 5, tzinfo=UTC)),
        ],
    )

    assert states["temporal_activity_timestamps"] == {"trigger": {"started_at": None, "completed_at": None}}


@pytest.mark.asyncio
async def test_a_failed_node_keeps_its_failed_status() -> None:
    """The whole point of the read: a retry needs to see *which* nodes failed."""
    states, _ = await _run([("step_1", "completed", "step_1"), ("step_2", "failed", "step_2")])

    assert states["activity_statuses"]["step_2"] == "failed"


@pytest.mark.asyncio
async def test_strips_the_iteration_suffix_so_a_loop_body_appears_once() -> None:
    """A loop body runs once per iteration and must collapse to a single key.

    Without stripping, every iteration would appear as its own node id and none of
    them would match a node in the graph, so a loop body could never be skipped.
    """
    states, _ = await _run(
        [
            ("body#iter-1", "completed", "body_iter_1"),
            ("body#iter-2", "completed", "body_iter_2"),
            ("body#iter-3", "failed", "body_iter_3"),
        ]
    )

    assert states["activity_statuses"] == {"body": "failed"}
    assert states["temporal_activity_statuses"] == {
        "body_iter_1": "completed",
        "body_iter_2": "completed",
        "body_iter_3": "failed",
    }


@pytest.mark.asyncio
async def test_the_last_row_for_a_repeated_node_wins() -> None:
    """Ordering is by iteration then creation, so the newest attempt is the truth."""
    states, _ = await _run([("body#iter-1", "failed", "body_iter_1"), ("body#iter-2", "completed", "body_iter_2")])

    assert states["activity_statuses"] == {"body": "completed"}


@pytest.mark.asyncio
async def test_a_missing_temporal_id_is_ignored_even_if_a_display_name_exists() -> None:
    """A display label without canonical occurrence identity maps to no node."""
    states, _ = await _run([(None, "completed", None), ("step_1", "completed", "step_1")])

    assert states["activity_statuses"] == {"step_1": "completed"}


@pytest.mark.asyncio
async def test_temporal_ids_are_the_only_source_status_identity() -> None:
    """The query must not carry the payload columns into the workflow.

    ``input_data`` and ``output_data`` are unbounded JSONB. Selecting them
    deserializes every activity's payloads in the source execution, on the
    workflow's critical path and before any node has dispatched — for a mapping
    that only ever uses the status. The cost is invisible in the return value, so
    it is asserted against the statement itself.
    """
    _, queries = await _run([])
    sql = str(cast("Any", queries[0]))

    assert "temporal_activity_id" in sql
    assert "activity_name" not in sql
    assert "status" in sql
    for payload_column in ("output_data", "input_data"):
        assert payload_column not in sql, f"{payload_column} must not be selected"


@pytest.mark.asyncio
async def test_reads_rows_as_a_column_tuple() -> None:
    """A projected select yields tuples, not row objects.

    Reading ``row.activity_name`` off a projected result raises at runtime while
    type checking rejects it, so both the shape and the unpacking are pinned here
    to keep the projection from being "simplified" back into an entity select.
    """
    states, queries = await _run([("step_1", "completed", "step_1")])

    assert len(queries[0].selected_columns) == 2
    assert states["activity_statuses"] == {"step_1": "completed"}


@pytest.mark.asyncio
async def test_the_status_is_returned_as_its_value() -> None:
    """Statuses come back as the string the rest of the engine compares against."""
    states, _ = await _run([("step_1", ActivityStatus.SKIPPED.value, "step_1")])

    assert states["activity_statuses"] == {"step_1": "skipped"}
