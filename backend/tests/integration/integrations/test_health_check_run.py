"""Integration tests for run_health_checks batch selection against a real DB.

Covers query semantics the unit tests can't reach: the batch_size cap,
oldest-first ordering, and skipping disabled or not-yet-stale integrations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import select

from syntara.integrations.models.integration import Integration
from syntara.integrations.services import health_check

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from tests.integration.helpers.integration import IntegrationFactory

pytestmark = pytest.mark.integration


def _mock_settings(*, batch_size: int, interval_seconds: int) -> MagicMock:
    values = {
        "integrations.health_check_batch_size": batch_size,
        "integrations.health_check_interval_seconds": interval_seconds,
    }
    settings = MagicMock()

    async def _get(key: str) -> int:
        return values[key]

    settings.get = _get
    return settings


def _mock_service() -> MagicMock:
    service = MagicMock()
    service.validate_integration = AsyncMock(return_value=MagicMock(success=True, error=None))
    return service


async def _clear_integrations(session: AsyncSession) -> None:
    result = await session.exec(select(Integration))
    for integration in result.all():
        await session.delete(integration)
    await session.commit()


class TestRunHealthChecksSelection:
    """Real-DB coverage for the batch fetch query in run_health_checks."""

    async def test_batch_size_caps_and_orders_oldest_first(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        integration_factory: IntegrationFactory,
    ) -> None:
        """batch_size caps the run; never-validated first, then oldest last_validated_at."""
        await _clear_integrations(test_db_session)
        now = datetime.now(UTC)

        never = await integration_factory.create(name="hc-never")
        oldest = await integration_factory.create(name="hc-oldest")
        middle = await integration_factory.create(name="hc-middle")
        newest_stale = await integration_factory.create(name="hc-newest-stale")
        never.last_validated_at = None
        oldest.last_validated_at = now - timedelta(days=30)
        middle.last_validated_at = now - timedelta(days=10)
        newest_stale.last_validated_at = now - timedelta(days=1)
        test_db_session.add_all([never, oldest, middle, newest_stale])
        await test_db_session.commit()

        service = _mock_service()
        settings = _mock_settings(batch_size=2, interval_seconds=3600)
        with (
            patch.object(health_check, "AsyncSessionLocal", test_db_session_factory),
            patch.object(health_check, "get_runtime_settings", return_value=settings),
            patch.object(health_check, "get_settings", return_value=MagicMock()),
            patch.object(health_check, "make_service_user", return_value=MagicMock()),
            patch.object(health_check, "create_secret_service", return_value=MagicMock()),
            patch.object(health_check, "IntegrationService", return_value=service),
        ):
            report = await health_check.run_health_checks()

        assert report.checked == 2
        assert report.available == 2
        assert report.error == 0
        checked_ids = [call.args[0] for call in service.validate_integration.await_args_list]
        assert checked_ids == [never.id, oldest.id]

    async def test_skips_disabled_and_not_yet_stale(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        integration_factory: IntegrationFactory,
    ) -> None:
        """Disabled integrations and those validated within the interval are not checked."""
        await _clear_integrations(test_db_session)
        now = datetime.now(UTC)

        disabled = await integration_factory.create(name="hc-disabled", enabled=False)
        fresh = await integration_factory.create(name="hc-fresh")
        stale = await integration_factory.create(name="hc-stale")
        disabled.last_validated_at = now - timedelta(days=10)
        fresh.last_validated_at = now - timedelta(seconds=30)
        stale.last_validated_at = now - timedelta(days=10)
        test_db_session.add_all([disabled, fresh, stale])
        await test_db_session.commit()

        service = _mock_service()
        settings = _mock_settings(batch_size=50, interval_seconds=3600)
        with (
            patch.object(health_check, "AsyncSessionLocal", test_db_session_factory),
            patch.object(health_check, "get_runtime_settings", return_value=settings),
            patch.object(health_check, "get_settings", return_value=MagicMock()),
            patch.object(health_check, "make_service_user", return_value=MagicMock()),
            patch.object(health_check, "create_secret_service", return_value=MagicMock()),
            patch.object(health_check, "IntegrationService", return_value=service),
        ):
            report = await health_check.run_health_checks()

        assert report.checked == 1
        checked_ids = [call.args[0] for call in service.validate_integration.await_args_list]
        assert checked_ids == [stale.id]

    async def test_checked_counts_failed_validations(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        integration_factory: IntegrationFactory,
    ) -> None:
        """A validation that raises is still counted in ``checked`` (checked == available + error).

        Mirrors the discovery report, where ``processed`` counts both success and
        failure paths. Prevents ``checked`` from silently undercounting failures.
        """
        await _clear_integrations(test_db_session)
        now = datetime.now(UTC)

        # older is processed first (ASC last_validated_at); it raises. newer succeeds.
        older = await integration_factory.create(name="hc-raises")
        newer = await integration_factory.create(name="hc-ok")
        older.last_validated_at = now - timedelta(days=30)
        newer.last_validated_at = now - timedelta(days=10)
        test_db_session.add_all([older, newer])
        await test_db_session.commit()

        service = _mock_service()
        service.validate_integration = AsyncMock(
            side_effect=[RuntimeError("upstream unreachable"), MagicMock(success=True, error=None)]
        )
        settings = _mock_settings(batch_size=50, interval_seconds=3600)
        with (
            patch.object(health_check, "AsyncSessionLocal", test_db_session_factory),
            patch.object(health_check, "get_runtime_settings", return_value=settings),
            patch.object(health_check, "get_settings", return_value=MagicMock()),
            patch.object(health_check, "make_service_user", return_value=MagicMock()),
            patch.object(health_check, "create_secret_service", return_value=MagicMock()),
            patch.object(health_check, "IntegrationService", return_value=service),
        ):
            report = await health_check.run_health_checks()

        # The failed validation is counted in checked, not dropped.
        assert report.checked == 2
        assert report.available == 1
        assert report.error == 1
        assert report.checked == report.available + report.error
