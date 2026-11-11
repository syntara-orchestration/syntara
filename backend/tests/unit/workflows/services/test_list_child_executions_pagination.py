"""Unit coverage for the DB-level child-execution pagination fix.

``list_child_executions`` now pushes the ``parent_execution_id`` / ``parent_node_id``
JSONB match into the shared paginator as ``extra_predicates`` instead of materializing
every matching child id and paging via an ``IN (...)`` restriction. These tests verify
the consumer wiring (no id materialization, predicates passed, id_restriction unused)
and the paginator helper. Multi-page/count/ordering behaviour is covered by the
DB-backed integration suite.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from sqlmodel import select

from syntara.core.services.base import BaseService
from syntara.workflows.models.execution import Execution
from syntara.workflows.services.execution_service import ExecutionService


def _service_with_existing_parent() -> tuple[ExecutionService, AsyncMock]:
    """An ExecutionService whose parent-existence lookup succeeds and whose paginator is mocked."""
    service = ExecutionService(Mock(), Mock())
    parent_lookup = Mock()
    parent_lookup.one_or_none.return_value = Mock()  # parent exists
    session = Mock()
    session.exec = AsyncMock(return_value=parent_lookup)
    service.session = session
    service.list_resources = AsyncMock(return_value=Mock())  # type: ignore[method-assign]
    return service, session.exec


async def test_passes_single_predicate_without_node_and_no_id_materialization() -> None:
    """Without node_id: one JSONB predicate, no id_restriction, and no id-only query."""
    service, session_exec = _service_with_existing_parent()
    parent_id = uuid4()

    await service.list_child_executions(parent_id)

    await_args = cast("AsyncMock", service.list_resources).await_args
    assert await_args is not None
    kwargs = await_args.kwargs
    assert "extra_predicates" in kwargs
    assert len(kwargs["extra_predicates"]) == 1
    assert kwargs.get("id_restriction") is None  # no IN(...) restriction
    # Only the parent-existence query ran — the child ids were NOT materialized.
    assert session_exec.await_count == 1


async def test_passes_two_predicates_with_node() -> None:
    """With node_id: a second predicate scopes to the node."""
    service, _ = _service_with_existing_parent()

    await service.list_child_executions(uuid4(), node_id="sub_wf_node")

    await_args = cast("AsyncMock", service.list_resources).await_args
    assert await_args is not None
    kwargs = await_args.kwargs
    assert len(kwargs["extra_predicates"]) == 2
    assert kwargs.get("id_restriction") is None


def test_apply_extra_predicates_ands_onto_query() -> None:
    """The helper ANDs predicates onto a query and is a no-op for None/empty."""
    base = select(Execution)
    assert BaseService._apply_extra_predicates(base, None) is base
    assert BaseService._apply_extra_predicates(base, []) is base

    pred = Execution.execution_metadata["parent_execution_id"].astext == "pe-1"  # type: ignore[index]
    filtered = BaseService._apply_extra_predicates(base, [pred])
    base_sql = str(base)
    filtered_sql = str(filtered)
    assert "WHERE" not in base_sql  # baseline select has no predicate
    assert "WHERE" in filtered_sql  # the predicate was ANDed on
    assert "execution_metadata" in filtered_sql  # filtering on the JSONB column
