"""Scheduling, coordination, and failure isolation for cluster reconciliation."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from syntara.core.config.base import get_settings
from syntara.execution_plane import integration_sync
from syntara.execution_plane.client import ExecutionPlaneUnavailableError


@pytest.fixture
def reconciliation(monkeypatch: pytest.MonkeyPatch) -> tuple[AsyncMock, UUID, UUID]:
    first, second = uuid4(), uuid4()

    @asynccontextmanager
    async def acquired(_factory: object) -> AsyncIterator[bool]:
        yield True

    async def batches(_factory: object, _integration_id: UUID | None) -> AsyncIterator[list[UUID]]:
        yield [first, second]

    monkeypatch.setattr(integration_sync, "_reconciliation_lock", acquired)
    monkeypatch.setattr(integration_sync, "_integration_batches", batches)
    apply = AsyncMock(return_value=True)
    monkeypatch.setattr(integration_sync, "apply_integration_cluster", apply)
    return apply, first, second


def test_default_frequency_is_five_minutes() -> None:
    assert get_settings().ep_cluster_reconciliation_interval_seconds == 300


def test_worker_uses_shared_reconciliation_coordination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        integration_sync, "get_settings", lambda: SimpleNamespace(ep_cluster_reconciliation_interval_seconds=300)
    )
    periodic = integration_sync.get_cluster_reconciliation_worker()
    assert periodic._interval_seconds == 300
    assert periodic._callback is integration_sync.reconcile_integration_clusters
    assert periodic._coordinate is False  # Core also coordinates manual and immediate runs.


@pytest.mark.asyncio
async def test_one_failed_integration_does_not_block_another(reconciliation: tuple[AsyncMock, UUID, UUID]) -> None:
    apply, first, second = reconciliation
    apply.side_effect = [ExecutionPlaneUnavailableError(), True]
    result = await integration_sync.reconcile_integration_clusters(MagicMock())
    assert result == {"synced": 1, "failed": 1, "skipped": 0}
    assert [call.args[1] for call in apply.await_args_list] == [first, second]


@pytest.mark.asyncio
async def test_busy_run_is_deferred_without_an_ep_attempt(
    reconciliation: tuple[AsyncMock, UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply, _, _ = reconciliation

    @asynccontextmanager
    async def busy(_factory: object) -> AsyncIterator[bool]:
        yield False

    monkeypatch.setattr(integration_sync, "_reconciliation_lock", busy)
    result = await integration_sync.reconcile_integration_clusters(MagicMock())
    assert result == {"synced": 0, "failed": 0, "skipped": 1}
    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_timeout_does_not_block_next_integration(
    reconciliation: tuple[AsyncMock, UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply, first, _ = reconciliation
    monkeypatch.setattr(integration_sync, "get_settings", lambda: SimpleNamespace(ep_request_timeout_seconds=0.01))

    async def apply_with_timeout(_factory: object, integration_id: UUID) -> bool:
        if integration_id == first:
            await asyncio.Event().wait()
        return True

    apply.side_effect = apply_with_timeout
    result = await integration_sync.reconcile_integration_clusters(MagicMock())
    assert result == {"synced": 1, "failed": 1, "skipped": 0}
