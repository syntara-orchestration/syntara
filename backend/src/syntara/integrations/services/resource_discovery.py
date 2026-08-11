"""Integration resource discovery service.

Periodically re-discovers and syncs each integration's resources
(MCP tools, LLM models) that are due based on the
``integrations.discovery_interval_seconds`` setting.

Mirrors the health-check service (``health_check.py``) but calls
``IntegrationService.refresh_resources()`` instead of
``validate_integration()`` — discovery is the "what does it offer?"
companion to the health check's "is it alive?".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from uuid import UUID
from sqlmodel import col, or_, select

import syntara.integrations.adapters.aap
import syntara.integrations.adapters.llm_provider
import syntara.integrations.adapters.mcp_server  # noqa: F401 — register adapters in the worker process
from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.models.principal import make_service_user
from syntara.core.services.secret_service import create_secret_service
from syntara.integrations.models import Integration
from syntara.integrations.models.integration import IntegrationRefreshStatus, IntegrationType
from syntara.integrations.services.integration_service import IntegrationService
from syntara.settings.cache.settings_cache import get_runtime_settings

logger = structlog.stdlib.get_logger(__name__)

# Only these types have discoverable resources; AAP gateway is a no-op.
_REFRESHABLE_TYPES = (IntegrationType.MCP_SERVER, IntegrationType.LLM_PROVIDER)


@dataclass
class ResourceDiscoveryResult:
    """Outcome of discovering/syncing a single integration."""

    integration_id: str
    status: str
    synced: int = 0
    updated: int = 0
    disabled: int = 0
    error: str | None = None


@dataclass
class ResourceDiscoveryReport:
    """Summary of one resource-discovery run."""

    processed: int = 0
    refreshed: int = 0
    error: int = 0
    results: list[ResourceDiscoveryResult] = field(default_factory=list)


async def run_resource_discovery() -> ResourceDiscoveryReport:
    """Discover and sync resources for all integrations due for discovery."""
    logger.info("Starting integration resource discovery")

    svc_user = make_service_user(get_settings().service_identity)
    report = ResourceDiscoveryReport()

    settings = get_runtime_settings()
    interval_seconds: int = await settings.get("integrations.discovery_interval_seconds")
    batch_size: int = await settings.get("integrations.discovery_batch_size")
    threshold = datetime.now(UTC) - timedelta(seconds=interval_seconds)

    # Fetch the due batch in a short-lived session; the per-integration loop is slow and network-bound.
    async with AsyncSessionLocal() as session:
        query = (
            select(Integration.id)
            .where(
                col(Integration.enabled).is_(True),
                col(Integration.integration_type).in_(_REFRESHABLE_TYPES),
                # Skip rows a manual UI refresh is already processing (AC: manual + periodic must not overlap).
                # IS DISTINCT FROM keeps never-refreshed rows (refresh_status NULL) in the batch.
                col(Integration.refresh_status).is_distinct_from(IntegrationRefreshStatus.REFRESHING),
                or_(
                    col(Integration.last_refreshed_at).is_(None),
                    col(Integration.last_refreshed_at) < threshold,
                ),
            )
            .order_by(col(Integration.last_refreshed_at).asc().nulls_first())
            .limit(batch_size)
        )
        result = await session.exec(query)
        integration_ids: list[UUID] = list(result.all())

    logger.info(
        "Batch integration resource discovery",
        due_count=len(integration_ids),
        threshold=threshold.isoformat(),
    )

    for int_id in integration_ids:
        try:
            async with AsyncSessionLocal() as discover_session:
                secret_service = create_secret_service(discover_session)
                service = IntegrationService(discover_session, svc_user, secret_service)
                refresh_result = await service.refresh_resources(int_id, skip_if_recent=True)

                report.processed += 1
                report.refreshed += 1
                # RefreshResult.tools_* also carry model counts for LLM integrations.
                report.results.append(
                    ResourceDiscoveryResult(
                        integration_id=str(int_id),
                        status="refreshed",
                        synced=refresh_result.synced_count,
                        updated=refresh_result.updated_count,
                        disabled=refresh_result.missing_count,
                    )
                )

        except Exception as exc:  # noqa: BLE001 — isolate per-integration failures; continue the rest
            logger.warning(
                "integration_resource_discovery_failed",
                integration_id=str(int_id),
                error_type=type(exc).__name__,
            )
            report.processed += 1
            report.error += 1
            report.results.append(
                ResourceDiscoveryResult(str(int_id), "error", error=f"Unexpected error: {type(exc).__name__}")
            )

    logger.info(
        "Integration resource discovery completed",
        processed=report.processed,
        refreshed=report.refreshed,
        errors=report.error,
    )

    return report
