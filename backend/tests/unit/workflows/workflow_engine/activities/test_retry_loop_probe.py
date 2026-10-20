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
) -> tuple[bool, list[Select[Any]]]:
    session = AsyncMock()
    session.exec.side_effect = [_result(found=value) for value in found]

    async def mock_get_db():  # noqa: ANN202
        yield session

    with patch(
        "syntara.workflows.workflow_engine.activities.retry_node_replay_activity.get_db",
        mock_get_db,
    ):
        answer = await probe_retry_loop_iteration("src-1", body_ids, child_loops or [], path)

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
async def test_missing_exact_path_is_not_iteration_evidence() -> None:
    answer, queries = await _run(["body_a"], [2], found=[False])

    assert answer is False
    sql = _render(queries[0])
    assert "loop_1_iter_2" not in sql
    assert "activity_name" not in sql
    assert "iteration" not in sql


@pytest.mark.asyncio
async def test_nested_iteration_without_an_exact_path_record_is_not_reached() -> None:
    answer, _ = await _run(["body_a"], [2, 3], found=[False, False])

    assert answer is False


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
async def test_nested_loop_with_no_direct_body_has_no_iteration_evidence() -> None:
    answer, queries = await _run([], [1, 0], found=[])

    assert answer is False
    assert queries == []
