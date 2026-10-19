"""Probe source execution records using complete loop iteration paths."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from syntara.workflows.workflow_engine.activities.retry_node_replay_activity import (
    probe_retry_loop_iteration,
)


def _result(*, found: bool) -> MagicMock:
    result = MagicMock()
    result.first.return_value = object() if found else None
    return result


async def _run(
    body_ids: list[str],
    path: list[int],
    *,
    found: list[bool],
    child_loops: list[str] | None = None,
    loop_id: str = "loop_1",
) -> tuple[bool | None, list[Select[Any]]]:
    session = AsyncMock()
    session.exec.side_effect = [_result(found=value) for value in found]

    async def mock_get_db():  # noqa: ANN202
        yield session

    with patch(
        "syntara.workflows.workflow_engine.activities.retry_node_replay_activity.get_db",
        mock_get_db,
    ):
        answer = await probe_retry_loop_iteration("src-1", loop_id, body_ids, child_loops or [], path)

    statements = [call.args[0] for call in session.exec.await_args_list]
    return answer, statements


def _render(query: Select[Any]) -> str:
    kwargs: dict[str, Any] = {"literal_binds": True}
    compiled = query.compile(dialect=postgresql.dialect(), compile_kwargs=kwargs)  # type: ignore[no-untyped-call]
    return str(compiled)


@pytest.mark.asyncio
async def test_exact_full_path_record_means_iteration_was_reached() -> None:
    answer, queries = await _run(["body_a"], [2, 3], found=[True])

    assert answer is True
    assert "body_a_iter_2_iter_3" in _render(queries[0])
    assert "src-1" in _render(queries[0])


@pytest.mark.asyncio
async def test_loop_control_completion_is_not_body_iteration_evidence() -> None:
    answer, queries = await _run(["body_a"], [2], found=[False, False])

    assert answer is False
    assert "loop_1_iter_2" not in _render(queries[0])


@pytest.mark.asyncio
async def test_nested_scope_record_means_missing_iteration_was_not_reached() -> None:
    answer, queries = await _run(["body_a"], [2, 3], found=[False, True])

    assert answer is False
    assert len(queries) == 2
    assert "body/_a/_iter/_2/_iter/_" in _render(queries[1])
    assert "loop/_1/_iter/_2/_iter/_" in _render(queries[1])


@pytest.mark.asyncio
async def test_legacy_nested_history_is_unknown_and_must_not_skip_work() -> None:
    answer, _ = await _run(["body_a"], [2, 3], found=[False, False])

    assert answer is None


@pytest.mark.asyncio
async def test_top_level_legacy_rows_keep_the_compatibility_lookup() -> None:
    answer, queries = await _run(["body_a"], [3], found=[False, True])

    assert answer is True
    legacy_sql = _render(queries[1])
    assert "body_a" in legacy_sql
    assert "body_a#iter-3" in legacy_sql
    assert "iteration" in legacy_sql


@pytest.mark.asyncio
async def test_nested_loop_controller_counts_under_the_exact_parent_path() -> None:
    answer, queries = await _run([], [2], child_loops=["inner"], found=[True])

    assert answer is True
    assert "inner/_iter/_2/_iter/_" in _render(queries[0])


@pytest.mark.asyncio
async def test_empty_body_never_queries_the_database() -> None:
    answer, queries = await _run([], [0], found=[])

    assert answer is False
    assert queries == []


@pytest.mark.asyncio
async def test_nested_loop_with_no_direct_activity_body_is_unknown_for_legacy_rows() -> None:
    answer, queries = await _run([], [1, 0], found=[])

    assert answer is None
    assert queries == []
