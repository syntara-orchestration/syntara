"""Probing whether the source run reached a loop iteration.

The probe is what routes a loop replay: it answers "did this iteration happen"
from what the source run recorded, instead of re-deriving the loop's decision.
That is the whole reason it can be trusted under ``continue_on_failure``, where a
failed body node does not mean the loop exited.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from syntara.workflows.workflow_engine.activities.retry_node_replay_activity import (
    probe_retry_loop_iteration,
)


async def _run(body_ids: list[str], index: int, *, found: bool) -> tuple[bool, Select[Any] | None]:
    """Run the probe, returning its answer and the statement it used, if any."""
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = object() if found else None
    session.exec.return_value = result

    async def mock_get_db():  # noqa: ANN202
        yield session

    with patch(
        "syntara.workflows.workflow_engine.activities.retry_node_replay_activity.get_db",
        mock_get_db,
    ):
        answer = await probe_retry_loop_iteration("src-1", body_ids, index)

    # No query is issued for an empty body, so the statement is genuinely absent.
    issued = session.exec.await_args
    return answer, issued.args[0] if issued else None


@pytest.mark.asyncio
async def test_answers_true_when_the_iteration_was_reached() -> None:
    answer, _ = await _run(["body_a"], 2, found=True)

    assert answer is True


@pytest.mark.asyncio
async def test_answers_false_when_the_source_never_got_there() -> None:
    answer, _ = await _run(["body_a"], 9, found=False)

    assert answer is False


@pytest.mark.asyncio
async def test_an_empty_body_never_reached_an_iteration() -> None:
    """No body nodes means nothing can have run, and no query is worth making."""
    answer, query = await _run([], 0, found=True)

    assert answer is False
    assert query is None, "an empty body must not reach the database at all"


def _render(query: Select[Any]) -> str:
    """Compile to literal SQL so the asserted values appear verbatim.

    ``.in_()`` and the OR branches otherwise compile to bind parameters, so a
    substring check against the default rendering would pass whether or not the
    node ids were actually in the statement.
    """
    # Select.compile carries no annotation in the pinned SQLAlchemy, so strict
    # mypy cannot see this call as typed even though it is.
    kwargs: dict[str, Any] = {"literal_binds": True}
    compiled = query.compile(dialect=postgresql.dialect(), compile_kwargs=kwargs)  # type: ignore[no-untyped-call]
    return str(compiled)


@pytest.mark.asyncio
async def test_the_statement_checks_both_row_conventions() -> None:
    """Iteration 0 is the node's own row; later iterations are ``node#iter-n``.

    The sync service writes the first run under the plain activity name and only
    mints a composite key once the previous row is terminal, so a probe that
    assumed one convention would miss half the iterations.
    """
    _, query = await _run(["body_a"], 3, found=True)
    assert query is not None
    sql = _render(query)

    assert "body_a" in sql
    assert "body_a#iter-3" in sql
    assert "iteration" in sql


@pytest.mark.asyncio
async def test_the_statement_is_scoped_to_the_source_execution() -> None:
    """A row from another execution must not answer this one."""
    _, query = await _run(["body_a"], 1, found=True)
    assert query is not None
    sql = _render(query)

    assert "src-1" in sql


@pytest.mark.asyncio
async def test_every_body_node_is_considered() -> None:
    """Any node in the body counts — a loop may have several, and one is enough."""
    _, query = await _run(["body_a", "body_b"], 1, found=True)
    assert query is not None
    sql = _render(query)

    assert "body_a#iter-1" in sql
    assert "body_b#iter-1" in sql
