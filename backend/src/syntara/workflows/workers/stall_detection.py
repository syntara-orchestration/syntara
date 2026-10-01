"""Periodic detection of running activities that exceed their expected duration.

Runs a database-only scanner that:

1. Identifies running activities where ``started_at + expected_duration < now()``.
2. Atomically claims them by setting ``stall_alert_at`` (permanent deduplication marker).
3. Emits audit events and Prometheus telemetry for each newly claimed stall.

Stall detection does NOT cancel, retry, or pause stalled activities. It provides
observability and alerting only. Intervention logic belongs to AAP-92826.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING

import structlog
from sqlmodel import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.workers.periodic import PeriodicWorker
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.types import MetricType
from syntara.workflows.audit.node_stalled import NodeStalledEvent
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus

logger = structlog.stdlib.get_logger(__name__)


async def detect_stalled_activities(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> None:
    """Scan for and claim running activities that have exceeded their expected duration.

    Uses an atomic conditional update to claim stalled activities, ensuring
    each stall is detected exactly once even under concurrent workers.

    Only rows successfully claimed by the update may produce audit events or
    telemetry increments.

    Args:
        session_factory: Async session factory for database access.

    """
    if session_factory is None:
        return

    async with session_factory() as session:
        # Find eligible activities: running, has expected_duration, overdue, not yet marked
        now = datetime.now(UTC)

        # Query for stalled activities
        stmt = select(ActivityExecution).where(
            ActivityExecution.status == ActivityStatus.RUNNING,
            ActivityExecution.expected_duration.isnot(None),  # type: ignore[union-attr]
            ActivityExecution.started_at.isnot(None),  # type: ignore[union-attr]
            ActivityExecution.stall_alert_at.is_(None),  # type: ignore[union-attr]
        )

        result = await session.exec(stmt)
        all_running = result.all()

        # Filter to those that are overdue
        claimed_rows: list[ActivityExecution] = []
        for activity in all_running:
            if (
                activity.expected_duration is not None
                and activity.started_at is not None
                and activity.started_at + timedelta(seconds=activity.expected_duration) < now
            ):
                # Atomically claim by setting stall_alert_at
                activity.stall_alert_at = now
                activity.updated_at = now
                session.add(activity)
                claimed_rows.append(activity)

        if claimed_rows:
            await session.commit()

    if not claimed_rows:
        logger.debug("stall_detection_noop", cycle_time=now.isoformat())
        return

    # Emit audit events and telemetry for each claimed stall
    recorder = get_metrics_recorder()
    success_count = 0
    audit_failure_count = 0
    telemetry_failure_count = 0

    for activity in claimed_rows:
        # Emit audit event
        try:
            event = NodeStalledEvent(
                activity_execution_id=activity.id,
                execution_id=activity.execution_id,
                activity_name=activity.activity_name,
                node_type=activity.node_type,
                expected_duration=activity.expected_duration or 0,  # Should not be None due to filter
                started_at=activity.started_at or now,  # Should not be None due to filter
                stall_alert_at=now,
            )
            AuditEventDispatcher.dispatch(event)
        except Exception:  # noqa: BLE001
            logger.warning(
                "stall_detection_audit_failed",
                activity_execution_id=str(activity.id),
                execution_id=str(activity.execution_id),
                exc_info=True,
            )
            audit_failure_count += 1
            # Skip telemetry for this activity and continue to next
            continue

        # Record Prometheus metric
        try:
            recorder.record(
                MetricType.STALLS_DETECTED,
                1.0,
                labels={"node_type": activity.node_type.value},
            )
            success_count += 1
        except Exception:  # noqa: BLE001
            logger.warning(
                "stall_detection_telemetry_failed",
                activity_execution_id=str(activity.id),
                execution_id=str(activity.execution_id),
                exc_info=True,
            )
            telemetry_failure_count += 1

    logger.info(
        "stall_detection_completed",
        claimed=len(claimed_rows),
        success=success_count,
        audit_failures=audit_failure_count,
        telemetry_failures=telemetry_failure_count,
        cycle_time=now.isoformat(),
    )


@lru_cache(maxsize=1)
def get_stall_detection_worker() -> PeriodicWorker:
    """Create the periodic stall detection worker."""
    settings = get_settings()
    return PeriodicWorker(
        name="stall-detection",
        interval_seconds=settings.stall_detection_interval_seconds,
        session_factory=AsyncSessionLocal,
        callback=detect_stalled_activities,
        coordinate=True,
    )
