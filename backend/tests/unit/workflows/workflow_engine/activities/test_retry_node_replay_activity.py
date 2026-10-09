"""Stored-output resolution for retry-from-failure .

These outputs are injected into a run in place of the nodes it skipped, so a
wrong one is a silently wrong result rather than a failure.
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.workflow_engine.activities.retry_node_replay_activity import (
    RESTORABLE_SOURCE_STATUSES,
    replay_retry_node_activity,
)


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
        error_details: str | None = None,
    ) -> None:
        self.activity_name = activity_name
        self.status = status
        self.output_data = output
        self.input_data = input_data
        self.started_at = started_at
        self.completed_at = completed_at
        self.error_details = error_details


def _mock_session(rows: list[Any]) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = rows[0] if rows else None
    session.exec.return_value = result
    return session


async def _run(rows: list[Any], node_id: str | None) -> dict[str, Any] | None:
    # The mock session does not execute SQL, so the activity's predicates are
    # applied here to keep these tests meaningful: the restorable-status filter
    # and the exact-name match the query performs. The integration test for this
    # activity covers the real query.
    wanted = node_id.strip() if node_id else ""
    session = _mock_session(
        [row for row in rows if row.status in RESTORABLE_SOURCE_STATUSES and row.activity_name == wanted]
    )

    async def mock_get_db():  # noqa: ANN202
        yield session

    with patch(
        "syntara.workflows.workflow_engine.activities.retry_node_replay_activity.get_db",
        mock_get_db,
    ):
        return await replay_retry_node_activity("src-1", node_id) if node_id is not None else None


@pytest.mark.asyncio
async def test_returns_completed_output_for_a_node() -> None:
    """A completed node's stored output is what gets injected in its place."""
    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"})]

    assert await _run(rows, "step_1") == {
        "status": "completed",
        "error_details": None,
        "input_data": {},
        "output_data": {"result": "ok"},
        "started_at": None,
        "completed_at": None,
    }


@pytest.mark.asyncio
async def test_only_requested_nodes_are_returned() -> None:
    """Unrelated rows in the execution must not be pulled in.

    The name match happens in the query, so the worker only ever holds the
    requested node's row and payload.
    """
    rows = [
        _Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"}),
        _Row("step_2", ActivityStatus.COMPLETED, {"result": "other"}),
    ]

    assert await _run(rows, "step_1") == {
        "status": "completed",
        "error_details": None,
        "input_data": {},
        "output_data": {"result": "ok"},
        "started_at": None,
        "completed_at": None,
    }


@pytest.mark.asyncio
async def test_a_node_with_no_restorable_record_is_absent_not_empty() -> None:
    """Absent distinguishes "nothing recorded" from "ran and produced nothing".

    A node with no restorable record cannot be replayed, because there would be
    nothing to inject. Returning an empty dict for it would let the caller skip it
    and leave downstream expressions unresolved.

    A FAILED node *is* restorable, so it is used here only as a name that has no row
    at all — the row list is what decides, not the status.
    """
    assert await _run([_Row("step_1", ActivityStatus.FAILED, None)], "never_ran") is None


@pytest.mark.asyncio
async def test_completed_node_with_no_output_returns_empty_dict() -> None:
    """A node that completed but produced nothing is an empty output, not absent."""
    rows = [_Row("step_1", ActivityStatus.COMPLETED, None)]

    assert await _run(rows, "step_1") == {
        "status": "completed",
        "error_details": None,
        "input_data": {},
        "output_data": {},
        "started_at": None,
        "completed_at": None,
    }


@pytest.mark.asyncio
async def test_iteration_suffixed_request_is_not_resolved_to_a_base_node() -> None:
    """A suffixed id matches nothing, because the query matches names exactly.

    Stripping the suffix used to be this activity's job, but only loop replay
    needs it: classification excludes loop nodes and loop bodies, so no suffixed
    id reaches here. Resolving one now would need per-iteration state this
    single-record transport cannot carry.
    """
    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"})]

    assert await _run(rows, "step_1#iter-2") is None


@pytest.mark.asyncio
async def test_an_iteration_row_is_matched_only_by_its_own_exact_name() -> None:
    """Exact matching means an iteration row is reachable only by its own name.

    Nothing sends such an id today, since classification excludes loop nodes and
    bodies. It is worth pinning that the match is literal rather than by suffix,
    so the loop work knows what this transport does and does not already do.
    """
    rows = [
        _Row("step_1", ActivityStatus.COMPLETED, {"result": "iter-0"}),
        _Row("step_1#iter-1", ActivityStatus.COMPLETED, {"result": "iter-1"}),
    ]

    by_iteration = await _run(rows, "step_1#iter-1")
    by_base = await _run(rows, "step_1")

    assert by_iteration is not None
    assert by_iteration["output_data"] == {"result": "iter-1"}
    assert by_base is not None
    assert by_base["output_data"] == {"result": "iter-0"}


@pytest.mark.asyncio
async def test_the_lookup_filters_by_name_in_the_query() -> None:
    """The name predicate belongs in the query, not in a Python loop over rows.

    This activity runs once per restored node. Reading the run's completed rows
    and filtering in Python made each call cost the whole execution, and pulled
    every node's payload into the worker to answer one question about one node.
    Asserting on the statement is what pins that: a mock that returns rows
    cannot tell a name filter from a full scan.
    """
    captured: list[Any] = []
    session = _mock_session([])

    async def capture(stmt: Any) -> MagicMock:  # noqa: ANN401 — the statement type is SQLAlchemy-internal
        captured.append(stmt)
        result = MagicMock()
        result.first.return_value = None
        return result

    session.exec.side_effect = capture

    async def mock_get_db():  # noqa: ANN202
        yield session

    with patch(
        "syntara.workflows.workflow_engine.activities.retry_node_replay_activity.get_db",
        mock_get_db,
    ):
        assert await replay_retry_node_activity("src-1", "step_target") is None

    assert len(captured) == 1
    statement = captured[0]
    sql = str(statement)
    assert "activity_execution.activity_name = " in sql
    assert "LIMIT" in sql.upper()
    assert statement.compile().params["activity_name_1"] == "step_target"


@pytest.mark.asyncio
async def test_empty_request_short_circuits() -> None:
    """Nothing requested means no query and no result."""
    assert await _run([], None) is None


@pytest.mark.asyncio
async def test_blank_ids_are_ignored() -> None:
    """Whitespace-only ids are not node ids."""
    assert await _run([], "   ") is None


@pytest.mark.asyncio
async def test_ids_are_whitespace_trimmed() -> None:
    """A padded id still resolves to its node."""
    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"})]

    assert await _run(rows, "  step_1  ") == {
        "status": "completed",
        "error_details": None,
        "input_data": {},
        "output_data": {"result": "ok"},
        "started_at": None,
        "completed_at": None,
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
        await _run(rows, "step_1")


@pytest.mark.asyncio
async def test_size_within_the_limit_is_returned() -> None:
    """A payload under the limit passes through untouched."""
    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"blob": "x" * 1000})]

    result = await _run(rows, "step_1")

    assert result is not None
    assert result["output_data"]["blob"] == "x" * 1000


@pytest.mark.asyncio
async def test_returns_stored_input_alongside_output() -> None:
    """Both halves of the stored record come back.

    A restored node has to be indistinguishable from one that executed, and the
    sync service resolves input through ``get_activity_input``, which reads
    ``node_inputs``. Returning output alone leaves drill-down with a blank input.
    """
    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"}, input_data={"query": "select 1"})]

    result = await _run(rows, "step_1")

    assert result == {
        "status": "completed",
        "error_details": None,
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

    result = await _run(rows, "step_1")

    assert result is not None
    assert result["started_at"] == started.isoformat()
    assert result["completed_at"] == completed.isoformat()


@pytest.mark.asyncio
async def test_node_with_no_stored_input_returns_empty_not_missing() -> None:
    """A node with no recorded input yields ``{}``, so the key is always present.

    The caller writes ``node_inputs[node.id]`` unconditionally; a missing key
    would have to be special-cased for no benefit.
    """
    rows = [_Row("step_1", ActivityStatus.COMPLETED, {"result": "ok"})]

    result = await _run(rows, "step_1")

    assert result is not None
    assert result["input_data"] == {}


@pytest.mark.asyncio
async def test_a_skipped_node_is_restorable() -> None:
    """A source SKIPPED node must come back, not be treated as absent.

    Absent means "no restorable record", and the caller then *executes* the node.
    Filtering to COMPLETED only would turn every source skip into a re-execution,
    which is both wrong work and a divergence from what the run view reported.
    """
    rows = [_Row("skipped_one", ActivityStatus.SKIPPED, {"reason": "not on this branch"})]

    result = await _run(rows, "skipped_one")

    assert result is not None
    assert result["status"] == "skipped"
    assert result["output_data"] == {"reason": "not on this branch"}


@pytest.mark.asyncio
async def test_a_failed_node_is_restorable_with_its_error() -> None:
    """A source failure keeps its recorded reason.

    The caller restores the node as FAILED; without the error details it would
    report a failure with no explanation, or — if the status were also dropped —
    report the failure as a clean skip.
    """
    rows = [_Row("failed_one", ActivityStatus.FAILED, {"partial": True}, error_details="exit code 1")]

    result = await _run(rows, "failed_one")

    assert result is not None
    assert result["status"] == "failed"
    assert result["error_details"] == "exit code 1"
    assert result["output_data"] == {"partial": True}


@pytest.mark.asyncio
async def test_an_unfinished_node_is_not_restorable() -> None:
    """PENDING, RUNNING and WAITING have nothing to restore.

    The source run reached a terminal state, so an in-flight row is work that never
    finished. Returning it would have the caller inject nothing and skip a node that
    should run.
    """
    for status in (ActivityStatus.PENDING, ActivityStatus.RUNNING, ActivityStatus.WAITING):
        rows = [_Row("unfinished", status, None)]

        assert await _run(rows, "unfinished") is None, status


@pytest.mark.asyncio
async def test_a_cancelled_node_is_not_restorable() -> None:
    """A cancelled row is an interrupted node, not a node with recorded state.

    Cancellation only rewrites unfinished rows — a node that had completed keeps its
    real status and output — so a CANCELLED row carries a synthetic
    "Workflow was cancelled" error and no output. Restoring it would report an
    interrupted node as a failure, which sets the run's unhandled-failure flag for a
    node that merely stopped. Absence makes the caller run it for real, which is what
    a retry of a cancelled run should do.
    """
    rows = [_Row("cancelled_one", ActivityStatus.CANCELLED, None, error_details="Workflow was cancelled")]

    assert await _run(rows, "cancelled_one") is None


@pytest.mark.asyncio
async def test_a_completed_node_in_a_cancelled_run_is_still_restorable() -> None:
    """Cancelling a run does not invalidate the work that had already finished.

    This is what makes retrying a cancelled run work: the completed nodes keep their
    real status and output, so they restore, and only the interrupted ones have no
    restorable record and run for real.
    """
    rows = [
        _Row("finished", ActivityStatus.COMPLETED, {"result": "ok"}),
        _Row("interrupted", ActivityStatus.CANCELLED, None, error_details="Workflow was cancelled"),
    ]

    result = await _run(rows, "finished")

    assert result is not None
    assert result["status"] == "completed"
    assert result["output_data"] == {"result": "ok"}
    assert await _run([rows[1]], "interrupted") is None
