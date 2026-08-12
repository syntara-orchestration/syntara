"""High-level workflow telemetry emitters.

Provides simple functions for emitting workflow telemetry events.
These functions handle all the mapping and calculation logic internally,
keeping the calling code clean.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.workflows.audit.node_execution import NodeExecutedEvent
from syntara.workflows.models.activity_execution import TERMINAL_ACTIVITY_STATUSES, ActivityStatus
from syntara.workflows.models.execution import ExecutionStatus
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ActivityTerminalStatus,
    WorkflowTerminalStatus,
)

if TYPE_CHECKING:
    from uuid import UUID

    from syntara.workflows.models.activity_execution import ActivityExecution

logger = structlog.stdlib.get_logger(__name__)


_STATUS_TO_TELEMETRY: dict[ActivityStatus, ActivityTerminalStatus] = {
    ActivityStatus.COMPLETED: ActivityTerminalStatus.COMPLETED,
    ActivityStatus.FAILED: ActivityTerminalStatus.FAILED,
    ActivityStatus.SKIPPED: ActivityTerminalStatus.SKIPPED,
    ActivityStatus.CANCELLED: ActivityTerminalStatus.CANCELLED,
}


def emit_activities(
    execution_id: UUID,
    activity_definitions_map: dict[str, dict[str, Any]],
    updated_activities: list[tuple[ActivityExecution, dict[str, Any]]],
    *,
    request_id: UUID | None = None,
) -> None:
    """Emit activity telemetry for updated activities.

    Called when activities are updated in the database to emit telemetry
    for activities that reached terminal states. Each terminal transition
    dispatches a :class:`NodeExecutedEvent` through the audit framework.

    Args:
        execution_id: Database execution ID.
        activity_definitions_map: Map of activity ID to activity definition from workflow.
        updated_activities: List of (activity, old_values) tuples for activities that were updated.
        request_id: Optional X-Request-Id from the originating HTTP request.

    """
    for activity, old_values in updated_activities:
        try:
            if activity.status not in TERMINAL_ACTIVITY_STATUSES:
                continue
            if old_values.get("status") in TERMINAL_ACTIVITY_STATUSES:
                continue

            telemetry_status = _STATUS_TO_TELEMETRY.get(activity.status)
            if not telemetry_status:
                continue

            activity_def = activity_definitions_map.get(activity.activity_name, {})
            node_type = activity.node_type
            duration_ms: int | None = None
            if activity.started_at and activity.completed_at:
                duration_ms = int((activity.completed_at - activity.started_at).total_seconds() * 1000)
            error_type: str | None = "ActivityExecutionError" if activity.status == ActivityStatus.FAILED else None
            AuditEventDispatcher.dispatch(
                NodeExecutedEvent(
                    execution_id=execution_id,
                    node_type=node_type,
                    node_def=activity_def,
                    status=telemetry_status,
                    duration_ms=duration_ms,
                    error_type=error_type,
                    request_id=request_id,
                )
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to emit node telemetry (fire-and-forget)",
                activity_name=activity.activity_name,
                execution_id=execution_id,
                exc_info=True,
            )


def _map_execution_status_to_telemetry(status: ExecutionStatus) -> WorkflowTerminalStatus:
    """Map ExecutionStatus to WorkflowTerminalStatus for telemetry.

    Args:
        status: The execution status.

    Returns:
        The corresponding telemetry status.

    """
    if status == ExecutionStatus.COMPLETED:
        return WorkflowTerminalStatus.COMPLETED
    if status == ExecutionStatus.COMPLETED_WITH_ERRORS:
        return WorkflowTerminalStatus.COMPLETED_WITH_ERRORS
    if status == ExecutionStatus.FAILED:
        return WorkflowTerminalStatus.FAILED
    return WorkflowTerminalStatus.CANCELLED
