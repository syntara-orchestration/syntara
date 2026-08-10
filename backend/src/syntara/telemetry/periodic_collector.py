"""Background task for periodic system analytics collection.

Snapshots current database state every hour and sends
a stateless system_analytics event to Segment via the
existing TelemetryClientRegistry.

Uses the shared PeriodicWorker for lifecycle management and
cross-instance coordination via PostgreSQL advisory locks.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.workers import PeriodicWorker
from syntara.telemetry.api_usage_accumulator import get_accumulator
from syntara.telemetry.events.integration_health import IntegrationHealthEvent
from syntara.telemetry.events.system_analytics import (
    ConfigInfo,
    FeatureUsageEntry,
    SystemAnalyticsEvent,
    UniqueCallerCounts,
)
from syntara.telemetry.queries import (
    get_enabled_feature_flags,
    query_credential_counts,
    query_credential_health,
    query_execution_counts,
    query_identity_provider_health,
    query_integration_health,
    query_model_usage,
    query_tool_counts,
    query_workflow_counts,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.settings.cache.settings_cache import SettingsCache
    from syntara.telemetry.client import TelemetryClientRegistry

logger = structlog.stdlib.get_logger(__name__)


async def _collect_and_send(
    session_factory: async_sessionmaker[AsyncSession],
    registry: TelemetryClientRegistry,
) -> None:
    """Snapshot current DB state and send to Segment.

    Args:
        session_factory: Async session maker for database access.
        registry: Telemetry client registry for sending events.

    """
    async with session_factory() as session:
        workflow_counts = await query_workflow_counts(session)
        execution_counts = await query_execution_counts(session)
        credential_counts = await query_credential_counts(session)
        model_usage_list = await query_model_usage(session)
        tool_counts = await query_tool_counts(session)
        integration_health = await query_integration_health(session)
        identity_provider_health = await query_identity_provider_health(session)
        credential_health = await query_credential_health(session)

    feature_flags = get_enabled_feature_flags()

    usage_snapshot = get_accumulator().drain()
    unique_callers = UniqueCallerCounts(
        total=len(usage_snapshot.caller_ids),
        by_principal_type=usage_snapshot.callers_by_type,
        by_interface=usage_snapshot.callers_by_interface,
    )
    feature_usage = [
        FeatureUsageEntry(
            endpoint_group=endpoint,
            http_method=method,
            interface=iface,
            request_count=count,
        )
        for (endpoint, method, iface), count in usage_snapshot.feature_usage.items()
    ]

    event = SystemAnalyticsEvent(
        entitlement_id=registry.entitlement_id,
        workflows=workflow_counts,
        credentials=credential_counts,
        executions=execution_counts,
        config=ConfigInfo(feature_flags_enabled=feature_flags),
        tools=tool_counts,
        model_usage=model_usage_list,
        unique_callers=unique_callers,
        feature_usage=feature_usage,
    )
    registry.send_event(event)
    logger.debug("periodic_analytics_event_sent")

    integration_event = IntegrationHealthEvent(
        entitlement_id=registry.entitlement_id,
        integrations=integration_health,
        identity_providers=identity_provider_health,
        credentials=credential_health,
    )
    registry.send_event(integration_event)
    logger.debug("integration_health_event_sent")


class PeriodicCollector:
    """Background task that periodically snapshots DB state and sends to Segment.

    Events are stateless — each is a self-contained snapshot of the
    current database state. No delta tracking or "since last report" logic.
    Sends events via registry.send_event() for consistency with all
    other telemetry events.

    Uses the shared PeriodicWorker for:
    - Asyncio lifecycle management (start/stop)
    - Error resilience (exceptions don't kill the loop)
    - Cross-instance coordination via PostgreSQL advisory locks
    """

    def __init__(
        self,
        registry: TelemetryClientRegistry,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        settings_cache: SettingsCache | None = None,
    ) -> None:
        """Initialize the periodic collector.

        Args:
            registry: Telemetry client registry for sending events.
            session_factory: Async session maker for database access.
            settings_cache: Optional settings cache; when provided, the
                collector restarts automatically when Segment settings
                change at runtime.

        """
        self._registry = registry
        self._session_factory = session_factory

        async def callback(sf: async_sessionmaker[AsyncSession]) -> None:
            await _collect_and_send(sf, registry)

        async def cleanup() -> None:
            registry.flush()
            await asyncio.sleep(0)

        self._worker = PeriodicWorker(
            name="telemetry-collector",
            interval_seconds=get_settings().collection_interval_seconds,
            session_factory=session_factory,
            callback=callback,
            cleanup_callback=cleanup,
            coordinate=True,
        )

        if settings_cache is not None:
            self._watch_settings(settings_cache)

    def start(self) -> None:
        """Start the background collection task."""
        self._worker.start()

    def _watch_settings(self, cache: SettingsCache) -> None:
        """Register for telemetry setting changes to restart the collector."""

        async def _on_segment_change(_key: str, _value: Any) -> None:  # noqa: ANN401
            await self.restart()

        async def _on_interval_change(_key: str, value: Any) -> None:  # noqa: ANN401
            interval = int(value) if value else get_settings().collection_interval_seconds
            self._worker._interval_seconds = interval  # noqa: SLF001
            logger.info("periodic_collector_interval_updated", interval_seconds=interval)
            await self.restart()

        cache.on_change("telemetry.segment_write_key", _on_segment_change)
        cache.on_change("telemetry.segment_endpoint", _on_segment_change)
        cache.on_change("telemetry.collection_interval_seconds", _on_interval_change)

    async def restart(self) -> None:
        """Restart the background task and run an immediate collection cycle."""
        await self._worker.stop()
        self._worker.start()
        try:
            await _collect_and_send(self._session_factory, self._registry)
        except Exception:  # noqa: BLE001
            logger.warning("periodic_collector_immediate_cycle_error", exc_info=True)

    async def stop(self) -> None:
        """Stop the background task and flush pending events."""
        await self._worker.stop()
