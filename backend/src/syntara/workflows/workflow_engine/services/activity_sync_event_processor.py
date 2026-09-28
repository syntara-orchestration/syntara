"""Translate Temporal activity events into pending database updates."""

from typing import Any

import structlog
from temporalio.api.history.v1 import HistoryEvent

from syntara.telemetry.events.workflow_error import RETRY_REASON_MAX_LENGTH
from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.utils.datetime import ensure_timezone_aware
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, NodeType
from syntara.workflows.workflow_engine.services.activity_sync_types import ExecutionMonitorMetadata
from syntara.workflows.workflow_engine.utils.loop_iteration_ids import (
    innermost_iteration_index,
    strip_loop_iteration_suffixes,
)
from syntara.workflows.workflow_engine.utils.timeout_messages import build_timeout_error_message

logger = structlog.stdlib.get_logger(__name__)


class ActivitySyncEventProcessorMixin:
    """Handlers for Temporal activity task history events."""

    def _process_activity_scheduled(self, event: HistoryEvent, metadata: ExecutionMonitorMetadata) -> None:
        """Process ACTIVITY_TASK_SCHEDULED event."""
        attrs = event.activity_task_scheduled_event_attributes
        if attrs.activity_id.startswith("__internal__"):
            return
        iteration_number = innermost_iteration_index(attrs.activity_id)
        if iteration_number is not None:
            base_activity_id = strip_loop_iteration_suffixes(attrs.activity_id)
            has_iter_suffix = True
        else:
            base_activity_id = attrs.activity_id
            has_iter_suffix = False
        is_loop_iteration = has_iter_suffix or base_activity_id in metadata.terminal_activity_ids
        # Loop *control* nodes use `{loop_id}_iter_{n}` (or
        # `{loop_id}_iter_{outer}_iter_{inner}` when nested). Body nodes inside
        # a loop (e.g. approval) reuse that suffix for uniqueness; they must
        # not be classified as control or their status is held at RUNNING
        # between iterations. Unknown type keeps the historical control
        # heuristic so tests without a definitions map still pass.
        activity_type = metadata.activity_definitions_map.get(base_activity_id, {}).get("type")
        is_loop_control = has_iter_suffix and activity_type in (None, NodeType.LOOP)
        configured_timeout_seconds: float | None = None
        if attrs.start_to_close_timeout and attrs.start_to_close_timeout.seconds > 0:
            configured_timeout_seconds = attrs.start_to_close_timeout.seconds + (
                attrs.start_to_close_timeout.nanos / 1e9
            )

        metadata.pending_activity_updates[event.event_id] = {
            "activity_id": base_activity_id,
            "activity_name": base_activity_id,
            "_is_loop_iteration": is_loop_iteration,
            "_is_loop_control": is_loop_control,
            "status": ActivityStatus.PENDING,
            "started_at": None,
            "completed_at": None,
            "error_details": None,
            "retry_count": 0,
            "iteration": iteration_number,
            "scheduled_at": ensure_timezone_aware(event.event_time),
            "configured_timeout_seconds": configured_timeout_seconds,
        }
        metadata.pending_sync_event_ids.add(event.event_id)

    def _process_activity_started(self, event: HistoryEvent, metadata: ExecutionMonitorMetadata) -> None:
        """Process ACTIVITY_TASK_STARTED event."""
        attrs = event.activity_task_started_event_attributes
        scheduled_id = attrs.scheduled_event_id
        if scheduled_id in metadata.pending_activity_updates:
            attempt = attrs.attempt or 1
            update = metadata.pending_activity_updates[scheduled_id]
            if attempt > 1:
                update["status"] = ActivityStatus.RETRYING
            else:
                activity_id = update["activity_id"]
                activity_def = metadata.activity_definitions_map.get(activity_id, {})
                activity_type = activity_def.get("type")
                update["status"] = (
                    ActivityStatus.WAITING
                    if activity_type in (NodeType.APPROVAL, NodeType.WAIT)
                    else ActivityStatus.RUNNING
                )
            update["started_at"] = ensure_timezone_aware(event.event_time)
            update["retry_count"] = attempt - 1
            metadata.pending_sync_event_ids.add(scheduled_id)

            if attempt > 1:
                last_failure = attrs.last_failure
                retry_reason = last_failure.message if last_failure else None
                if retry_reason and len(retry_reason) > RETRY_REASON_MAX_LENGTH:
                    retry_reason = retry_reason[: RETRY_REASON_MAX_LENGTH - 3] + "..."
                # Extract failure type name from the Temporal failure chain
                failure_type: str | None = None
                if last_failure:
                    cause = last_failure.cause
                    if cause and cause.application_failure_info and cause.application_failure_info.type:
                        failure_type = cause.application_failure_info.type
                    elif last_failure.application_failure_info and last_failure.application_failure_info.type:
                        failure_type = last_failure.application_failure_info.type
                update["_retry_info"] = {
                    "retry_count": attempt - 1,
                    "retry_reason": retry_reason,
                    "error_type": failure_type,
                }

    @staticmethod
    def _is_agentic_activity(activity_def: dict[str, Any]) -> bool:
        """Check whether an activity definition uses the agentic executor."""
        return activity_def.get("type") == "agentic"

    _TRIGGER_ACTIVITY_TYPES: frozenset[ActivityName] = frozenset(
        {
            ActivityName.MANUAL_TRIGGER,
            ActivityName.SCHEDULED_TRIGGER,
            ActivityName.WEBHOOK_TRIGGER,
            ActivityName.EDA_TRIGGER,
        }
    )

    @staticmethod
    def _extract_trigger_activity_type(activity_definitions_map: dict[str, dict[str, Any]]) -> ActivityName | None:
        """Extract the trigger type from activity definitions.

        Searches through the activity definitions to find a trigger node
        (e.g., manual_trigger, scheduled_trigger, webhook_trigger, eda_trigger).

        Args:
            activity_definitions_map: Map of activity ID to activity definition

        Returns:
            The trigger ActivityName if found, None otherwise

        """
        return next(
            (
                ActivityName(defn["type"])
                for defn in activity_definitions_map.values()
                if defn.get("type") in ActivitySyncEventProcessorMixin._TRIGGER_ACTIVITY_TYPES
            ),
            None,
        )

    def _process_activity_completed(self, event: HistoryEvent, metadata: ExecutionMonitorMetadata) -> None:
        """Process ACTIVITY_TASK_COMPLETED event.

        With async completion, ACTIVITY_TASK_COMPLETED means the activity is
        genuinely complete for all node types (including approval and agentic).
        """
        attrs = event.activity_task_completed_event_attributes
        scheduled_id = attrs.scheduled_event_id
        if scheduled_id in metadata.pending_activity_updates:
            update = metadata.pending_activity_updates[scheduled_id]
            update["status"] = ActivityStatus.COMPLETED
            update["completed_at"] = ensure_timezone_aware(event.event_time)
            metadata.pending_sync_event_ids.add(scheduled_id)
            metadata.terminal_activity_ids.add(update["activity_id"])

    def _process_activity_failed(self, event: HistoryEvent, metadata: ExecutionMonitorMetadata) -> None:
        """Process ACTIVITY_TASK_FAILED event."""
        # TODO(https://redhat.atlassian.net/browse/AAP-86855): InvocationCancelledError raises a
        # non-retryable ApplicationError, which Temporal records as
        # ACTIVITY_TASK_FAILED. This unconditionally sets ActivityStatus.FAILED.
        # Once the activity row is terminal, _sync_nodes_to_terminal_status
        # skips it, so the Execute Invocation step shows "Failed" even though
        # the execution-level status is CANCELLED.  Inspect
        # attrs.failure.application_failure_info.type for
        # "InvocationCancelledError" and set ActivityStatus.CANCELLED instead.
        attrs = event.activity_task_failed_event_attributes
        scheduled_id = attrs.scheduled_event_id
        if scheduled_id in metadata.pending_activity_updates:
            update = metadata.pending_activity_updates[scheduled_id]
            update["status"] = ActivityStatus.FAILED
            update["completed_at"] = ensure_timezone_aware(event.event_time)
            if attrs.failure:
                update["error_details"] = attrs.failure.message
            metadata.pending_sync_event_ids.add(scheduled_id)
            metadata.terminal_activity_ids.add(update["activity_id"])

    def _process_activity_timed_out(self, event: HistoryEvent, metadata: ExecutionMonitorMetadata) -> None:
        """Process ACTIVITY_TASK_TIMED_OUT event."""
        attrs = event.activity_task_timed_out_event_attributes
        scheduled_id = attrs.scheduled_event_id
        if scheduled_id in metadata.pending_activity_updates:
            update = metadata.pending_activity_updates[scheduled_id]
            update["status"] = ActivityStatus.FAILED
            timed_out_at = ensure_timezone_aware(event.event_time)
            update["completed_at"] = timed_out_at
            if attrs.failure:
                logger.warning(
                    "Activity timed out (raw Temporal message)",
                    activity_id=update["activity_id"],
                    raw_message=attrs.failure.message,
                )
            activity_def = metadata.activity_definitions_map.get(update["activity_id"], {})
            update["error_details"] = build_timeout_error_message(
                step_name=activity_def.get("name") or update["activity_id"],
                is_agentic=activity_def.get("type") == "agentic",
                timeout_seconds=update.get("configured_timeout_seconds"),
            )

            start_time = update.get("started_at") or update.get("scheduled_at")
            update["_timeout_info"] = {
                "elapsed_time_ms": int((timed_out_at - start_time).total_seconds() * 1000) if start_time else 0,
                "configured_timeout_seconds": update.get("configured_timeout_seconds", 0.0) or 0.0,
                "retry_count": update.get("retry_count", 0),
            }
            metadata.pending_sync_event_ids.add(scheduled_id)
            metadata.terminal_activity_ids.add(update["activity_id"])

    def _process_activity_canceled(self, event: HistoryEvent, metadata: ExecutionMonitorMetadata) -> None:
        """Process ACTIVITY_TASK_CANCELED event."""
        attrs = event.activity_task_canceled_event_attributes
        scheduled_id = attrs.scheduled_event_id
        if scheduled_id in metadata.pending_activity_updates:
            update = metadata.pending_activity_updates[scheduled_id]
            update["status"] = ActivityStatus.CANCELLED
            update["completed_at"] = ensure_timezone_aware(event.event_time)
            update["error_details"] = "Activity was canceled"
            metadata.pending_sync_event_ids.add(scheduled_id)
            metadata.terminal_activity_ids.add(update["activity_id"])
