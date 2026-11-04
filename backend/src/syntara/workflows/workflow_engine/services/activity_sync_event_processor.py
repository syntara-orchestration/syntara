"""Translate Temporal activity events into pending database updates."""

import json
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

    _SUBWORKFLOW_SETUP_PREFIX = "__internal__setup_sub_workflow_"

    def _process_activity_scheduled(self, event: HistoryEvent, metadata: ExecutionMonitorMetadata) -> None:
        """Process ACTIVITY_TASK_SCHEDULED event."""
        attrs = event.activity_task_scheduled_event_attributes
        if attrs.activity_id.startswith(self._SUBWORKFLOW_SETUP_PREFIX):
            self._process_subworkflow_setup_scheduled(event, attrs.activity_id, metadata)
            return
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

    def _process_subworkflow_setup_scheduled(
        self, event: HistoryEvent, activity_id: str, metadata: ExecutionMonitorMetadata
    ) -> None:
        """Register the sub-workflow setup activity against its canvas node.

        The sub-workflow node runs through an ``__internal__setup_sub_workflow_*``
        activity whose id encodes the canvas node and (for ``for_each``) the
        iteration: ``__internal__setup_sub_workflow_{node.id}`` or
        ``..._{node.id}_iter_{n}``. The node's aggregate ActivityExecution row is
        already created upfront, so this only registers a pending update keyed to
        the canvas node: the activity's STARTED event drives RUNNING and its
        COMPLETED event populates runtime_metadata (non-iterated nodes only).
        Terminal status stays owned by the finalizer (see
        ``_process_subworkflow_setup_completed``).
        """
        invocation_node_id = activity_id[len(self._SUBWORKFLOW_SETUP_PREFIX) :]
        iteration_number = innermost_iteration_index(invocation_node_id)
        canvas_node_id = (
            strip_loop_iteration_suffixes(invocation_node_id) if iteration_number is not None else invocation_node_id
        )
        metadata.pending_activity_updates[event.event_id] = {
            "activity_id": canvas_node_id,
            "activity_name": canvas_node_id,
            "_is_loop_iteration": False,
            "_is_loop_control": False,
            "_subworkflow_setup": True,
            "_subworkflow_iteration": iteration_number,
            "status": ActivityStatus.PENDING,
            "started_at": None,
            "completed_at": None,
            "error_details": None,
            "retry_count": 0,
            "iteration": None,
            "scheduled_at": ensure_timezone_aware(event.event_time),
            "configured_timeout_seconds": None,
        }
        metadata.pending_sync_event_ids.add(event.event_id)

    def _process_activity_started(self, event: HistoryEvent, metadata: ExecutionMonitorMetadata) -> None:
        """Process ACTIVITY_TASK_STARTED event."""
        attrs = event.activity_task_started_event_attributes
        scheduled_id = attrs.scheduled_event_id
        if scheduled_id in metadata.pending_activity_updates:
            attempt = attrs.attempt or 1
            update = metadata.pending_activity_updates[scheduled_id]
            update["status"] = self._activity_status_for_attempt(update, metadata, attempt)
            update["started_at"] = ensure_timezone_aware(event.event_time)
            update["retry_count"] = attempt - 1
            metadata.pending_sync_event_ids.add(scheduled_id)

            if attempt > 1:
                update["_retry_info"] = self._build_retry_info(attrs.last_failure, attempt)

    @staticmethod
    def _activity_status_for_attempt(
        update: dict[str, Any], metadata: ExecutionMonitorMetadata, attempt: int
    ) -> ActivityStatus:
        if attempt > 1:
            return ActivityStatus.RETRYING
        activity_def = metadata.activity_definitions_map.get(update["activity_id"], {})
        return (
            ActivityStatus.WAITING
            if activity_def.get("type") in (NodeType.APPROVAL, NodeType.WAIT)
            else ActivityStatus.RUNNING
        )

    @staticmethod
    def _build_retry_info(last_failure: Any, attempt: int) -> dict[str, Any]:  # noqa: ANN401
        retry_reason = last_failure.message if last_failure else None
        if retry_reason and len(retry_reason) > RETRY_REASON_MAX_LENGTH:
            retry_reason = retry_reason[: RETRY_REASON_MAX_LENGTH - 3] + "..."
        failure_type: str | None = None
        if last_failure:
            cause = last_failure.cause
            if cause and cause.application_failure_info and cause.application_failure_info.type:
                failure_type = cause.application_failure_info.type
            elif last_failure.application_failure_info and last_failure.application_failure_info.type:
                failure_type = last_failure.application_failure_info.type
        return {"retry_count": attempt - 1, "retry_reason": retry_reason, "error_type": failure_type}

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
            if update.get("_subworkflow_setup"):
                self._process_subworkflow_setup_completed(attrs, update, scheduled_id, metadata)
                return
            update["status"] = ActivityStatus.COMPLETED
            update["completed_at"] = ensure_timezone_aware(event.event_time)
            metadata.pending_sync_event_ids.add(scheduled_id)
            metadata.terminal_activity_ids.add(update["activity_id"])

    def _process_subworkflow_setup_completed(
        self,
        attrs: Any,  # noqa: ANN401 - ActivityTaskCompletedEventAttributes
        update: dict[str, Any],
        scheduled_id: int,
        metadata: ExecutionMonitorMetadata,
    ) -> None:
        """Handle completion of the sub-workflow setup activity.

        Setup completion is NOT node completion: the child workflow has only just
        been dispatched. The node is kept RUNNING and deliberately not added to
        ``terminal_activity_ids`` — the finalizer owns the node's terminal status
        until a reliable logical-node completion signal exists (C3).

        For a non-iterated node the child's identifying metadata from the setup
        result is surfaced as ``runtime_metadata``. For a ``for_each`` node
        (N setups -> one aggregate row) ``runtime_metadata`` is intentionally left
        unset in C2: writing each iteration would silently overwrite the previous
        one, and the aggregate representation is a deferred decision (C3).
        """
        update["status"] = ActivityStatus.RUNNING
        update["completed_at"] = None
        if update.get("_subworkflow_iteration") is None:
            child_metadata = self._extract_child_runtime_metadata(attrs)
            if child_metadata is not None:
                update["runtime_metadata"] = child_metadata
        metadata.pending_sync_event_ids.add(scheduled_id)

    @staticmethod
    def _extract_child_runtime_metadata(attrs: Any) -> dict[str, Any] | None:  # noqa: ANN401
        """Pull the child's identifying metadata from the setup activity result.

        The setup activity returns a JSON dict carrying the child execution and
        workflow identifiers. Only those UI-relevant identifiers are surfaced as
        ``runtime_metadata``; the full result (which also carries the child
        workflow definition) is never stored. Returns ``None`` when the payload is
        absent, unparseable, or carries none of the expected identifiers.
        """
        if not attrs.result or not attrs.result.payloads:
            return None
        try:
            result_data = json.loads(attrs.result.payloads[0].data)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to parse sub-workflow setup result for runtime_metadata", exc_info=True)
            return None
        if not isinstance(result_data, dict):
            return None
        child_metadata = {
            "child_execution_id": result_data.get("execution_id"),
            "child_workflow_id": result_data.get("child_workflow_id"),
            "child_workflow_name": result_data.get("child_workflow_name"),
            "child_workflow_version": result_data.get("child_workflow_version"),
        }
        if all(value is None for value in child_metadata.values()):
            return None
        return child_metadata

    def _process_activity_failed(self, event: HistoryEvent, metadata: ExecutionMonitorMetadata) -> None:
        """Process ACTIVITY_TASK_FAILED event."""
        attrs = event.activity_task_failed_event_attributes
        scheduled_id = attrs.scheduled_event_id
        if scheduled_id in metadata.pending_activity_updates:
            update = metadata.pending_activity_updates[scheduled_id]
            if update.get("_subworkflow_setup"):
                # Terminal status for the sub-workflow node is owned by the
                # finalizer in C2; a setup failure must not terminalize the node.
                return
            is_cancelled = bool(
                attrs.failure
                and attrs.failure.application_failure_info
                and attrs.failure.application_failure_info.type == "InvocationCancelledError"
            )
            update["status"] = ActivityStatus.CANCELLED if is_cancelled else ActivityStatus.FAILED
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
            if update.get("_subworkflow_setup"):
                # Terminal status for the sub-workflow node is owned by the
                # finalizer in C2; a setup timeout must not terminalize the node.
                return
            update["status"] = ActivityStatus.FAILED
            timed_out_at = ensure_timezone_aware(event.event_time)
            update["completed_at"] = timed_out_at
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
            if update.get("_subworkflow_setup"):
                # Terminal status for the sub-workflow node is owned by the
                # finalizer in C2; a setup cancel must not terminalize the node.
                return
            update["status"] = ActivityStatus.CANCELLED
            update["completed_at"] = ensure_timezone_aware(event.event_time)
            update["error_details"] = "Activity was canceled"
            metadata.pending_sync_event_ids.add(scheduled_id)
            metadata.terminal_activity_ids.add(update["activity_id"])
