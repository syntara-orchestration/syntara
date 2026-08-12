"""Integration tests for run_resource_discovery batch selection against a real DB.

Covers query semantics the unit tests cannot reach: the batch_size cap,
stalest-first selection, refreshable-type filtering (AAP excluded), and
skipping disabled or not-yet-due integrations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import select

from syntara.integrations.models.integration import Integration, IntegrationRefreshStatus, IntegrationType
from syntara.integrations.services import resource_discovery

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from tests.integration.helpers.integration import IntegrationFactory

pytestmark = pytest.mark.integration


def _mock_settings(*, batch_size: int, interval_seconds: int) -> MagicMock:
    values = {
        "integrations.discovery_batch_size": batch_size,
        "integrations.discovery_interval_seconds": interval_seconds,
    }
    settings = MagicMock()

    async def _get(key: str) -> int:
        return values[key]

    settings.get = _get
    return settings


def _mock_service() -> MagicMock:
    service = MagicMock()
    service.refresh_resources = AsyncMock(return_value=MagicMock(synced_count=0, updated_count=0, missing_count=0))
    return service


async def _clear_integrations(session: AsyncSession) -> None:
    result = await session.exec(select(Integration))
    for integration in result.all():
        await session.delete(integration)
    await session.commit()


def _refreshed_ids(service: MagicMock) -> set[UUID]:
    return {call.args[0] for call in service.refresh_resources.await_args_list}


class TestRunResourceDiscoverySelection:
    """Real-DB coverage for the batch fetch query in run_resource_discovery."""

    async def test_batch_size_caps_stalest_first(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        integration_factory: IntegrationFactory,
    ) -> None:
        """batch_size caps the run to the stalest integrations (never-refreshed first)."""
        await _clear_integrations(test_db_session)
        now = datetime.now(UTC)

        never = await integration_factory.create(name="rd-never")
        oldest = await integration_factory.create(name="rd-oldest")
        middle = await integration_factory.create(name="rd-middle")
        newest = await integration_factory.create(name="rd-newest")
        never.last_refreshed_at = None
        oldest.last_refreshed_at = now - timedelta(days=30)
        middle.last_refreshed_at = now - timedelta(days=10)
        newest.last_refreshed_at = now - timedelta(days=1)
        test_db_session.add_all([never, oldest, middle, newest])
        await test_db_session.commit()

        service = _mock_service()
        settings = _mock_settings(batch_size=2, interval_seconds=3600)
        with (
            patch.object(resource_discovery, "AsyncSessionLocal", test_db_session_factory),
            patch.object(resource_discovery, "get_runtime_settings", return_value=settings),
            patch.object(resource_discovery, "get_settings", return_value=MagicMock()),
            patch.object(resource_discovery, "make_service_user", return_value=MagicMock()),
            patch.object(resource_discovery, "create_secret_service", return_value=MagicMock()),
            patch.object(resource_discovery, "IntegrationService", return_value=service),
        ):
            report = await resource_discovery.run_resource_discovery()

        # The 2 stalest integrations are selected (deterministic oldest-first order).
        assert report.processed == 2
        assert _refreshed_ids(service) == {never.id, oldest.id}

    async def test_skips_disabled_not_due_and_aap(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        integration_factory: IntegrationFactory,
    ) -> None:
        """Disabled, not-yet-due, and AAP integrations are excluded from discovery."""
        await _clear_integrations(test_db_session)
        now = datetime.now(UTC)

        disabled = await integration_factory.create(name="rd-disabled", enabled=False)
        fresh = await integration_factory.create(name="rd-fresh")
        aap = await integration_factory.create(
            name="rd-aap", integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM
        )
        due = await integration_factory.create(name="rd-due")
        disabled.last_refreshed_at = now - timedelta(days=10)
        fresh.last_refreshed_at = now - timedelta(seconds=30)
        aap.last_refreshed_at = now - timedelta(days=10)
        due.last_refreshed_at = now - timedelta(days=10)
        test_db_session.add_all([disabled, fresh, aap, due])
        await test_db_session.commit()

        service = _mock_service()
        settings = _mock_settings(batch_size=50, interval_seconds=3600)
        with (
            patch.object(resource_discovery, "AsyncSessionLocal", test_db_session_factory),
            patch.object(resource_discovery, "get_runtime_settings", return_value=settings),
            patch.object(resource_discovery, "get_settings", return_value=MagicMock()),
            patch.object(resource_discovery, "make_service_user", return_value=MagicMock()),
            patch.object(resource_discovery, "create_secret_service", return_value=MagicMock()),
            patch.object(resource_discovery, "IntegrationService", return_value=service),
        ):
            report = await resource_discovery.run_resource_discovery()

        assert report.processed == 1
        assert _refreshed_ids(service) == {due.id}

    async def test_skips_refreshing_integrations(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        integration_factory: IntegrationFactory,
    ) -> None:
        """An integration mid-refresh (status REFRESHING) is skipped so a periodic tick can't overlap a manual one."""
        await _clear_integrations(test_db_session)
        now = datetime.now(UTC)

        # Both are stale enough to be due; only the REFRESHING one is skipped.
        refreshing = await integration_factory.create(name="rd-refreshing")
        idle = await integration_factory.create(name="rd-idle")
        refreshing.last_refreshed_at = now - timedelta(days=10)
        refreshing.refresh_status = IntegrationRefreshStatus.REFRESHING
        idle.last_refreshed_at = now - timedelta(days=10)
        test_db_session.add_all([refreshing, idle])
        await test_db_session.commit()

        service = _mock_service()
        settings = _mock_settings(batch_size=50, interval_seconds=3600)
        with (
            patch.object(resource_discovery, "AsyncSessionLocal", test_db_session_factory),
            patch.object(resource_discovery, "get_runtime_settings", return_value=settings),
            patch.object(resource_discovery, "get_settings", return_value=MagicMock()),
            patch.object(resource_discovery, "make_service_user", return_value=MagicMock()),
            patch.object(resource_discovery, "create_secret_service", return_value=MagicMock()),
            patch.object(resource_discovery, "IntegrationService", return_value=service),
        ):
            report = await resource_discovery.run_resource_discovery()

        assert report.processed == 1
        assert _refreshed_ids(service) == {idle.id}
