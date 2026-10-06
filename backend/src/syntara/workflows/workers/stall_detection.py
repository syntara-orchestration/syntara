"""Periodic detection of running activities that exceed their expected duration.

Runs a database-only scanner that:

1. Identifies running activities where ``started_at + expected_duration < now()``.
2. Atomically claims them by setting ``stall_alert_at`` (permanent deduplication marker).
3. Emits audit events, Segment telemetry, and Prometheus metrics for each newly claimed stall.

Stall detection does NOT cancel, retry, or pause stalled activities. It provides
observability and alerting only. Intervention logic belongs to AAP-92826.

SDP Requirements (R16/AC-10, R23/AC-13):
- 10-second scan interval default
- Three Prometheus metrics: stalled workflows (gauge), stalled steps (gauge), stalled workflows total (counter)
- Segment event with anonymized properties
- Execution-level counter deduplication via first_stall_detected_at

Timestamp Semantics:
- stall_alert_at and first_stall_detected_at are permanent markers (never cleared)
- updated_at is NOT set for internal stall bookkeeping to avoid misleading
  "last modified" semantics - stall detection is observability, not user action
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from functools import lru_cache
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, select, text, update
from sqlmodel import col

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.metrics.recorder import MetricsRecorder

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.workers.periodic import PeriodicWorker
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.types import MetricType
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.workflow_stall import WorkflowStallEvent
from syntara.workflows.audit.node_stalled import NodeStalledEvent
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution

logger = structlog.stdlib.get_logger(__name__)


async def detect_stalled_activities(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> None:
    """Scan for and claim running activities that have exceeded their expected duration.

    Uses an atomic UPDATE...RETURNING to claim stalled activities, ensuring
    each stall is detected exactly once even under concurrent workers.

    Only rows successfully claimed by the update may produce audit events or
    telemetry increments.

    SDP Implementation (R23/AC-13):
    - Emits Segment event with anonymized properties (execution_mode, stalled_step_type)
    - Updates Prometheus gauges (only from coordinated scanner)
    - Increments stalled workflows counter only once per execution
    - Independent failure handling for audit, Segment, and Prometheus

    Args:
        session_factory: Async session factory for database access.

    """
    if session_factory is None:
        return

    now = datetime.now(UTC)

    # Atomic UPDATE...RETURNING that claims stalled activities in a single database round-trip.
    # All eligibility conditions are in the WHERE clause to ensure only qualifying rows are updated.
    async with session_factory() as session:
        stmt = (
            update(ActivityExecution)
            .where(
                ActivityExecution.status == ActivityStatus.RUNNING,  # type: ignore[arg-type]
                ActivityExecution.expected_duration.isnot(None),  # type: ignore[union-attr]
                ActivityExecution.started_at.isnot(None),  # type: ignore[union-attr]
                ActivityExecution.stall_alert_at.is_(None),  # type: ignore[union-attr]
                # PostgreSQL: started_at + make_interval(secs => expected_duration) < now
                text("started_at + make_interval(secs => expected_duration) < :now"),
            )
            .values(stall_alert_at=now)
            .returning(ActivityExecution)
            .execution_options(synchronize_session=False)
        )

        result = await session.execute(stmt, {"now": now})
        claimed_rows = list(result.scalars().all())
        await session.commit()

    if not claimed_rows:
        logger.debug("stall_detection_noop", cycle_time=now.isoformat())
        # Still update gauges even when no new stalls (gauges show current state)
        await _update_prometheus_gauges_safe(session_factory)
        return

    # Group claimed activities by execution_id for batch processing
    activities_by_execution: dict[UUID, list[ActivityExecution]] = defaultdict(list)
    for activity in claimed_rows:
        activities_by_execution[activity.execution_id].append(activity)

    execution_ids = list(activities_by_execution.keys())

    # Atomically mark executions entering stalled state for the first time (batched)
    # Returns execution IDs that were marked for the first time (for counter deduplication)
    first_stall_execution_ids: set[UUID] = set()
    async with session_factory() as session:
        stmt = (
            update(Execution)
            .where(
                col(Execution.id).in_(execution_ids),
                Execution.first_stall_detected_at.is_(None),  # type: ignore[union-attr]
            )
            .values(first_stall_detected_at=now)
            .returning(col(Execution.id))
        )
        result = await session.execute(stmt)
        first_stall_execution_ids = set(result.scalars().all())
        await session.commit()

    # Load execution mode for Segment events (single batched query)
    execution_modes: dict[UUID, str] = {}
    async with session_factory() as session:
        mode_stmt = select(col(Execution.id), col(Execution.mode)).where(col(Execution.id).in_(execution_ids))
        mode_result = await session.execute(mode_stmt)
        execution_modes = {row[0]: row[1].value for row in mode_result.all()}

    # Emit audit events, Segment events, and track metrics for each claimed stall
    # All three reporting paths are independent - failure in one doesn't prevent others
    audit_failure_count = 0
    segment_failure_count = 0

    recorder = get_metrics_recorder()
    telemetry_registry = get_telemetry_registry()

    for activity in claimed_rows:
        # Emit audit event
        try:
            event = NodeStalledEvent(
                activity_execution_id=activity.id,
                execution_id=activity.execution_id,
                activity_name=activity.activity_name,
                node_type=activity.node_type,
                expected_duration=activity.expected_duration,
                started_at=activity.started_at,
                stall_alert_at=activity.stall_alert_at,
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

        # Emit Segment event (SDP R23/AC-13) - independent of audit
        try:
            if telemetry_registry.is_initialized():
                mode = execution_modes.get(activity.execution_id, "standard")
                telemetry_registry.send_event(
                    WorkflowStallEvent(
                        execution_mode=mode,
                        stalled_step_type=activity.node_type.value,
                        entitlement_id=telemetry_registry.entitlement_id,
                    )
                )
        except Exception:  # noqa: BLE001
            logger.warning(
                "stall_detection_segment_failed",
                activity_execution_id=str(activity.id),
                execution_id=str(activity.execution_id),
                exc_info=True,
            )
            segment_failure_count += 1

    # Update Prometheus metrics (SDP R23/AC-13)
    # This scanner is coordinated, so only this process updates gauges
    prometheus_failed = False
    try:
        # Increment counter for executions entering stalled state
        for _ in first_stall_execution_ids:
            recorder.record(MetricType.STALLED_WORKFLOWS_TOTAL, 1.0)

        # Update gauges to reflect current state
        await _update_prometheus_gauges(session_factory, recorder)
    except Exception:  # noqa: BLE001
        logger.warning(
            "stall_detection_prometheus_failed",
            exc_info=True,
        )
        prometheus_failed = True

    logger.info(
        "stall_detection_completed",
        claimed=len(claimed_rows),
        first_stall_executions=len(first_stall_execution_ids),
        audit_failures=audit_failure_count,
        segment_failures=segment_failure_count,
        prometheus_failed=prometheus_failed,
        cycle_time=now.isoformat(),
    )


async def _update_prometheus_gauges_safe(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Safely update Prometheus gauges with error isolation.

    Wraps _update_prometheus_gauges to prevent Prometheus/DB errors from
    disrupting the periodic worker cycle.

    Args:
        session_factory: Database session factory.

    """
    try:
        await _update_prometheus_gauges(session_factory)
    except Exception:  # noqa: BLE001
        logger.warning(
            "stall_detection_gauge_refresh_failed",
            exc_info=True,
        )


async def _update_prometheus_gauges(
    session_factory: async_sessionmaker[AsyncSession],
    recorder: MetricsRecorder | None = None,
) -> None:
    """Update Prometheus gauges to reflect current stalled state.

    Gauges show point-in-time state:
    - stalled_workflows_current: count distinct executions with at least one stalled activity
    - stalled_steps_current: count activities with status=RUNNING and stall_alert_at IS NOT NULL

    Only called from the coordinated scanner to avoid conflicting updates across replicas.

    Args:
        session_factory: Database session factory.
        recorder: Metrics recorder (optional, will get default if None).

    """
    if recorder is None:
        recorder = get_metrics_recorder()

    async with session_factory() as session:
        # Count distinct stalled executions
        stalled_executions_stmt = select(func.count(func.distinct(ActivityExecution.execution_id))).where(
            ActivityExecution.status == ActivityStatus.RUNNING,  # type: ignore[arg-type]
            col(ActivityExecution.stall_alert_at).is_not(None),
        )
        result = await session.execute(stalled_executions_stmt)
        stalled_workflows_count = result.scalar() or 0

        # Count stalled activities
        stalled_activities_stmt = select(func.count(col(ActivityExecution.id))).where(
            ActivityExecution.status == ActivityStatus.RUNNING,  # type: ignore[arg-type]
            col(ActivityExecution.stall_alert_at).is_not(None),
        )
        result = await session.execute(stalled_activities_stmt)
        stalled_steps_count = result.scalar() or 0

    # Set gauge values directly via Prometheus (gauges are absolute values, not increments)
    recorder._prometheus.stalled_workflows_current.set(float(stalled_workflows_count))  # noqa: SLF001
    recorder._prometheus.stalled_steps_current.set(float(stalled_steps_count))  # noqa: SLF001


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
