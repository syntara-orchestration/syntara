"""Integration health check service.

Validates integrations that are due for health checks based on the
health_check_interval_seconds setting.
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
import syntara.integrations.adapters.mcp_server  # noqa: F401 — register MCP adapter
from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.models.principal import make_service_user
from syntara.core.services.secret_service import create_secret_service
from syntara.integrations.models import Integration
from syntara.integrations.services.integration_service import IntegrationService
from syntara.settings.cache.settings_cache import get_runtime_settings

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class IntegrationCheckResult:
    """Outcome of validating a single integration."""

    integration_id: str
    status: str
    error: str | None = None


@dataclass
class HealthCheckReport:
    """Summary of one health-check run."""

    checked: int = 0
    available: int = 0
    error: int = 0
    results: list[IntegrationCheckResult] = field(default_factory=list)


async def run_health_checks() -> HealthCheckReport:
    """Run health checks on all integrations due for validation."""
    logger.info("Starting integration health check")

    svc_user = make_service_user(get_settings().service_identity)
    report = HealthCheckReport()

    settings = get_runtime_settings()
    interval_seconds: int = await settings.get("integrations.health_check_interval_seconds")
    batch_size: int = await settings.get("integrations.health_check_batch_size")
    threshold = datetime.now(UTC) - timedelta(seconds=interval_seconds)

    # Fetch the batch in its own short-lived session so the connection is
    # released before the per-check loop, which is network-bound and slow.
    async with AsyncSessionLocal() as session:
        query = (
            select(Integration.id)
            .where(
                col(Integration.enabled).is_(True),
                or_(
                    col(Integration.last_validated_at).is_(None),
                    col(Integration.last_validated_at) < threshold,
                ),
            )
            .order_by(col(Integration.last_validated_at).asc().nulls_first())
            .limit(batch_size)
        )
        result = await session.exec(query)
        integration_ids: list[UUID] = list(result.all())

    logger.info(
        "Batch integration health check",
        stale_count=len(integration_ids),
        threshold=threshold.isoformat(),
    )

    for int_id in integration_ids:
        try:
            async with AsyncSessionLocal() as check_session:
                secret_service = create_secret_service(check_session)
                service = IntegrationService(check_session, svc_user, secret_service)
                # validate_integration() commits internally
                validate_result = await service.validate_integration(int_id)

                report.checked += 1
                if validate_result.success:
                    report.available += 1
                    report.results.append(IntegrationCheckResult(str(int_id), "available"))
                else:
                    report.error += 1
                    report.results.append(IntegrationCheckResult(str(int_id), "error", validate_result.error))

        except Exception as exc:  # noqa: BLE001 — isolate per-integration failures; continue checking the rest
            logger.warning(
                "integration_health_check_failed",
                integration_id=str(int_id),
                error_type=type(exc).__name__,
            )
            report.checked += 1
            report.error += 1
            report.results.append(
                IntegrationCheckResult(str(int_id), "error", f"Unexpected error: {type(exc).__name__}")
            )

    logger.info(
        "Integration health check completed",
        checked=report.checked,
        available=report.available,
        errors=report.error,
    )

    return report
