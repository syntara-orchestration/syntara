"""Source-state reads for retry-from-failure.

The mapping this returns decides which nodes a retry may skip, so a row read that
is one node too broad seeds a node the retry is about to re-execute with the
previous run's state.
"""

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.workflow_engine.activities.retry_node_replay_activity import (
    fetch_retry_source_state_activity,
)


async def _run(rows: list[tuple[str, str]]) -> tuple[dict[str, str], Any]:
    """Run the activity over ``rows``, returning the mapping and the query used."""
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    session.exec.return_value = result

    async def mock_get_db():  # noqa: ANN202
        yield session

    with patch(
        "syntara.workflows.workflow_engine.activities.retry_node_replay_activity.get_db",
        mock_get_db,
    ):
        states = await fetch_retry_source_state_activity("src-1")

    return states, session.exec.await_args.args[0]


@pytest.mark.asyncio
async def test_returns_the_status_for_a_node() -> None:
    states, _ = await _run([("step_1", "completed")])

    assert states == {"step_1": "completed"}


@pytest.mark.asyncio
async def test_a_failed_node_keeps_its_failed_status() -> None:
    """The whole point of the read: a retry needs to see *which* nodes failed."""
    states, _ = await _run([("step_1", "completed"), ("step_2", "failed")])

    assert states["step_2"] == "failed"


@pytest.mark.asyncio
async def test_strips_the_iteration_suffix_so_a_loop_body_appears_once() -> None:
    """A loop body runs once per iteration and must collapse to a single key.

    Without stripping, every iteration would appear as its own node id and none of
    them would match a node in the graph, so a loop body could never be skipped.
    """
    states, _ = await _run(
        [
            ("body#iter-1", "completed"),
            ("body#iter-2", "completed"),
            ("body#iter-3", "failed"),
        ]
    )

    assert states == {"body": "failed"}


@pytest.mark.asyncio
async def test_the_last_row_for_a_repeated_node_wins() -> None:
    """Ordering is by iteration then creation, so the newest attempt is the truth."""
    states, _ = await _run([("body#iter-1", "failed"), ("body#iter-2", "completed")])

    assert states == {"body": "completed"}


@pytest.mark.asyncio
async def test_a_null_activity_name_is_ignored() -> None:
    """Sync bookkeeping rows carry no activity name and map to no node."""
    states, _ = await _run([(None, "completed"), ("step_1", "completed")])  # type: ignore[list-item]

    assert states == {"step_1": "completed"}


@pytest.mark.asyncio
async def test_selects_only_the_columns_it_reads() -> None:
    """The query must not carry the payload columns into the workflow.

    ``input_data`` and ``output_data`` are unbounded JSONB. Selecting them
    deserializes every activity's payloads in the source execution, on the
    workflow's critical path and before any node has dispatched — for a mapping
    that only ever uses the status. The cost is invisible in the return value, so
    it is asserted against the statement itself.
    """
    _, query = await _run([])
    sql = str(cast("Any", query))

    assert "activity_name" in sql
    assert "status" in sql
    for payload_column in ("output_data", "input_data"):
        assert payload_column not in sql, f"{payload_column} must not be selected"


@pytest.mark.asyncio
async def test_reads_rows_as_a_column_tuple() -> None:
    """A projected select yields tuples, not row objects.

    Reading ``row.activity_name`` off a two-column result raises at runtime while
    type checking rejects it, so both the shape and the unpacking are pinned here
    to keep the projection from being "simplified" back into an entity select.
    """
    states, query = await _run([("step_1", "completed")])

    assert len(query.selected_columns) == 2
    assert states == {"step_1": "completed"}


@pytest.mark.asyncio
async def test_the_status_is_returned_as_its_value() -> None:
    """Statuses come back as the string the rest of the engine compares against."""
    states, _ = await _run([("step_1", ActivityStatus.SKIPPED.value)])

    assert states == {"step_1": "skipped"}
