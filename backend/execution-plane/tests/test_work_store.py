"""Tests for database ownership and lifecycle in WorkStore."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Self
from unittest.mock import AsyncMock

import pytest
from execution_plane.models.work_item import WorkItem, WorkItemStatus
from execution_plane.work_store import WorkStore
from sqlalchemy.pool import NullPool


class _Session:
    def __init__(self, item: WorkItem | None = None) -> None:
        self.item = item
        self.added: Any = None
        self.commits = 0
        self.rollbacks = 0
        self.execute = AsyncMock()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def add(self, item: WorkItem) -> None:
        self.added = item

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def get(self, _model: object, _item_id: uuid.UUID) -> WorkItem | None:
        return self.item


class _SessionFactory:
    def __init__(self, session: _Session) -> None:
        self.session = session

    def __call__(self) -> _Session:
        return self.session


class _ScalarResult:
    def __init__(self, value: uuid.UUID | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> uuid.UUID | None:
        return self.value


class _ClaimResult:
    def __init__(self, item: WorkItem | None) -> None:
        self.item = item

    def scalars(self) -> Self:
        return self

    def first(self) -> WorkItem | None:
        return self.item


def _store() -> WorkStore:
    return WorkStore("postgresql+asyncpg://localhost/syntara")


@pytest.mark.asyncio
async def test_dispatch_owns_session_and_commits_notification() -> None:
    """Dispatch uses an internally managed session and commits the notification."""
    store = _store()
    session = _Session()
    session.execute.return_value = None
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]

    item = await store.dispatch("handle", uuid.uuid4(), {"input_config": {}})

    assert item.status == WorkItemStatus.PENDING
    assert session.added is item
    assert session.commits == 1
    session.execute.assert_awaited_once()
    await store.close()


@pytest.mark.asyncio
async def test_set_result_reloads_item_by_id() -> None:
    """Result persistence does not require a session-bound WorkItem."""
    store = _store()
    item = WorkItem(
        id=uuid.uuid4(),
        work_correlation_id=uuid.uuid4(),
        activity_handle="handle",
        created_at=datetime.now(UTC),
    )
    session = _Session(item)
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]

    await store.set_result(item.id, {"output": "ok"}, WorkItemStatus.COMPLETED)

    assert item.status == WorkItemStatus.COMPLETED
    assert item.result == {"output": "ok"}
    assert session.commits == 1
    await store.close()


@pytest.mark.asyncio
async def test_is_target_drained_checks_claimed_and_dispatched_work() -> None:
    """A target is drained only when no active WorkItems reference it."""
    store = _store()
    session = _Session()
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]
    target_id = uuid.uuid4()

    session.execute.return_value = _ScalarResult(None)
    assert await store.is_target_drained(target_id) is True
    active_item = WorkItem(
        id=uuid.uuid4(),
        work_correlation_id=uuid.uuid4(),
        activity_handle="handle",
        execution_target_id=target_id,
        status=WorkItemStatus.CLAIMED,
        created_at=datetime.now(UTC),
    )
    session.execute.return_value = _ScalarResult(active_item.id)
    assert await store.is_target_drained(target_id) is False
    await store.close()


@pytest.mark.asyncio
async def test_claim_one_assigns_an_eligible_target_in_the_claim_transaction() -> None:
    """A claimed item must remain visible to target draining until execution completes."""
    store = _store()
    item = WorkItem(
        id=uuid.uuid4(),
        work_correlation_id=uuid.uuid4(),
        activity_handle="handle",
        status=WorkItemStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    target_id = uuid.uuid4()
    session = _Session()
    session.execute.side_effect = [_ClaimResult(item), _ScalarResult(target_id)]
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]

    claimed = await store.claim_one()

    assert claimed is item
    assert claimed.execution_target_id == target_id
    assert claimed.status is WorkItemStatus.CLAIMED
    assert claimed.claimed_at is not None
    assert session.commits == 1
    target_statement = session.execute.await_args_list[1].args[0]
    assert target_statement._for_update_arg is not None
    assert target_statement._for_update_arg.skip_locked is True
    await store.close()


@pytest.mark.asyncio
async def test_accepts_engine_options() -> None:
    """Store callers can select a pool appropriate for their lifecycle."""
    store = WorkStore("postgresql+asyncpg://localhost/syntara", poolclass=NullPool)

    assert store._engine is not None
    assert isinstance(store._engine.pool, NullPool)
    await store.close()
