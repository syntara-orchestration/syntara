"""Shared metric emission helpers for workflow and activity completions.

Both the on-read path (``ExecutionService``) and the background poller
(``completion_poller``) call into these functions so that emission logic
is defined in exactly one place.

Owns the process-local deduplication set that prevents the same terminal
execution from being counted twice regardless of which path fires first.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import TYPE_CHECKING

import structlog
from sqlmodel import select

from syntara.metrics.types import ComponentLabel, MetricType
from syntara.workflows.models.activity_execution import (
    TERMINAL_ACTIVITY_STATUSES,
    ActivityExecution,
    ActivityStatus,
)
from syntara.workflows.models.execution import TERMINAL_EXECUTION_STATUSES, ExecutionStatus

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.metrics.recorder import MetricsRecorder
    from syntara.workflows.models.execution import Execution

logger = structlog.stdlib.get_logger(__name__)

DEFAULT_MAX_DEDUP_SIZE = 50_000


class _BoundedDedup:
    """FIFO-bounded deduplication tracker using insertion-ordered eviction.

    When the capacity is exceeded, the oldest entries are evicted first.
    This replaces the previous plain ``set[UUID]`` which could grow without
    bound and used non-deterministic iteration order for trimming.

    Thread-safe: All operations are protected by an internal lock to prevent
    race conditions during concurrent access from multiple threads.
    """

    __slots__ = ("_data", "_lock", "_max_size")

    def __init__(self, max_size: int = DEFAULT_MAX_DEDUP_SIZE) -> None:
        self._data: OrderedDict[UUID, None] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def __contains__(self, item: UUID) -> bool:
        with self._lock:
            return item in self._data

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def add(self, item: UUID) -> None:
        with self._lock:
            self._data[item] = None
            while len(self._data) > self._max_size:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def difference_update(self, items: set[UUID] | list[UUID]) -> None:
        with self._lock:
            for item in items:
                self._data.pop(item, None)


emitted_completions: _BoundedDedup = _BoundedDedup()
emitted_invocations: _BoundedDedup = _BoundedDedup()

# Running counters for aggregate rate gauges.
_workflow_completion_counts: list[int] = [0, 0]  # [completed, total]
_activity_success_counts: list[int] = [0, 0]  # [succeeded, total]

# Thread locks to protect counters from race conditions during concurrent access
_workflow_completion_lock = threading.Lock()
_activity_success_lock = threading.Lock()


def reset_emission_trackers() -> None:
    """Clear the process-local dedup set and running counters (testing helper)."""
    emitted_completions.clear()
    emitted_invocations.clear()
    with _workflow_completion_lock:
        _workflow_completion_counts[:] = [0, 0]
    with _activity_success_lock:
        _activity_success_counts[:] = [0, 0]


async def emit_completion_metrics(
    session: AsyncSession,
    execution: Execution,
    recorder: MetricsRecorder,
) -> bool:
    """Emit workflow + activity metrics for a terminal execution.

    Returns *True* if metrics were emitted, *False* if skipped (already
    emitted or not terminal).
    """
    if execution.id in emitted_completions:
        return False
    if execution.status not in TERMINAL_EXECUTION_STATUSES or not execution.completed_at:
        return False

    workflow_type = execution.workflow.name if execution.workflow else "unknown"

    _emit_workflow(execution, workflow_type, recorder)
    await _emit_activities(session, execution, workflow_type, recorder)

    emitted_completions.add(execution.id)
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _emit_workflow(
    execution: Execution,
    workflow_type: str,
    recorder: MetricsRecorder,
) -> None:
    """Record WORKFLOW_DURATION, WORKFLOW_STATUS and update the active gauge."""
    if not execution.completed_at:
        return
    labels = {
        "workflow_id": str(execution.workflow_id),
        "execution_id": str(execution.id),
        "status": execution.status.value,
        "workflow_type": workflow_type,
    }
    duration_ms = (execution.completed_at - execution.created_at).total_seconds() * 1000
    recorder.record(MetricType.WORKFLOW_DURATION, duration_ms, unit="ms", labels=labels)
    recorder.record(MetricType.WORKFLOW_STATUS, value=1, labels=labels)

    with _workflow_completion_lock:
        _workflow_completion_counts[1] += 1
        if execution.status in (ExecutionStatus.COMPLETED, ExecutionStatus.COMPLETED_WITH_ERRORS):
            _workflow_completion_counts[0] += 1
        completion_rate = _workflow_completion_counts[0] / _workflow_completion_counts[1]
    recorder.record(
        MetricType.WORKFLOW_COMPLETION_RATE,
        completion_rate,
        component=ComponentLabel.EXECUTION_SERVICE,
    )


async def _emit_activities(
    session: AsyncSession,
    execution: Execution,
    workflow_type: str,
    recorder: MetricsRecorder,
) -> None:
    """Query terminal activities and record ACTIVITY_DURATION + success rate."""
    result = await session.exec(
        select(ActivityExecution)
        .where(ActivityExecution.execution_id == execution.id)
        .where(ActivityExecution.status.in_(TERMINAL_ACTIVITY_STATUSES))  # type: ignore[attr-defined]
        .where(ActivityExecution.started_at.is_not(None))  # type: ignore[union-attr]
        .where(ActivityExecution.completed_at.is_not(None))  # type: ignore[union-attr]
        .order_by(ActivityExecution.created_at)  # type: ignore[arg-type]
    )
    activities = result.all()
    total = 0
    succeeded = 0
    for activity in activities:
        if not activity.started_at or not activity.completed_at:
            continue  # defensive; SQL WHERE should prevent this
        total += 1
        if activity.status == ActivityStatus.COMPLETED:
            succeeded += 1
        duration_ms = (activity.completed_at - activity.started_at).total_seconds() * 1000
        recorder.record(
            MetricType.ACTIVITY_DURATION,
            duration_ms,
            unit="ms",
            labels={
                "execution_id": str(execution.id),
                "activity_name": activity.activity_name,
                "status": activity.status.value if activity.status else "unknown",
                "workflow_type": workflow_type,
            },
        )

    if total > 0:
        with _activity_success_lock:
            _activity_success_counts[0] += succeeded
            _activity_success_counts[1] += total
            aggregate_rate = _activity_success_counts[0] / _activity_success_counts[1]
        recorder.record(
            MetricType.ACTIVITY_EXECUTION_SUCCESS_RATE,
            aggregate_rate,
            component=ComponentLabel.TEMPORAL_WORKER,
        )
