"""Translate Temporal activity events into pending database updates."""

import json
from typing import Any

import structlog
from temporalio.api.history.v1 import HistoryEvent

from syntara.telemetry.events.workflow_error import RETRY_REASON_MAX_LENGTH
from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.utils.datetime import ensure_timezone_aware
from syntara.workflows.workflow_engine.codecs.credential_codec import CredentialPayloadCodec
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, NodeType
from syntara.workflows.workflow_engine.services.activity_sync_types import ExecutionMonitorMetadata
from syntara.workflows.workflow_engine.utils.credential_scrubber import scrub_credentials
from syntara.workflows.workflow_engine.utils.loop_iteration_ids import (
    innermost_iteration_index,
    loop_iteration_indices,
    strip_loop_iteration_suffixes,
)
from syntara.workflows.workflow_engine.utils.timeout_messages import build_timeout_error_message

logger = structlog.stdlib.get_logger(__name__)


class ActivitySyncEventProcessorMixin:
    """Handlers for Temporal activity task history events."""

    # Provided by the composed ActivitySyncService; declared here for type-checkers
    # (mirrors the stub on the monitor mixin) so self.temporal_client resolves.
    temporal_client: Any

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
        COMPLETED event populates runtime_metadata. For a ``for_each`` node the
        ``_subworkflow_iteration`` index is carried through so the sync layer can
        materialise one run-details row per iteration, each linking to that
        iteration's child execution. Terminal status stays owned by
        the finalizer (see ``_process_subworkflow_setup_completed``).
        """
        invocation_node_id = activity_id[len(self._SUBWORKFLOW_SETUP_PREFIX) :]
        # Full loop-index chain (outermost first) uniquely identifies a nested
        # iteration; the innermost index alone collides across outer indices.
        iteration_chain = loop_iteration_indices(invocation_node_id)
        iteration_number = iteration_chain[-1] if iteration_chain else None
        canvas_node_id = strip_loop_iteration_suffixes(invocation_node_id) if iteration_chain else invocation_node_id
        metadata.pending_activity_updates[event.event_id] = {
            "activity_id": canvas_node_id,
            "activity_name": canvas_node_id,
            "_is_loop_iteration": False,
            "_is_loop_control": False,
            "_subworkflow_setup": True,
            "_subworkflow_iteration": iteration_number,
            "_subworkflow_iteration_chain": iteration_chain,
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

        The node's ``input_data``/``output_data`` summaries are reconstructed from
        the setup result payload and persisted via the shared writer (C3: ASS owns
        this, replacing the activity-side direct writer). The child's identifying
        metadata is surfaced as ``runtime_metadata`` on every row -- the single
        row for a non-looped node, and one row per iteration for a ``for_each``
        node -- with each iteration's setup result routed to its own row.
        """
        update["status"] = ActivityStatus.RUNNING
        update["completed_at"] = None
        setup_result = self._decode_setup_result(attrs, self.temporal_client.data_converter.payload_codec)
        if setup_result is not None:
            update["_subworkflow_io"] = self._build_subworkflow_io(setup_result)
            # Surface the child link on every row: each setup result carries its
            # own child execution id, routed to the matching row (the single row
            # for a non-looped node, or the per-iteration row for a for_each).
            child_metadata = self._child_runtime_metadata(setup_result)
            if child_metadata is not None:
                update["runtime_metadata"] = child_metadata
        metadata.pending_sync_event_ids.add(scheduled_id)

    @staticmethod
    def _decode_setup_result(
        attrs: Any,  # noqa: ANN401
        codec: CredentialPayloadCodec | None = None,
    ) -> dict[str, Any] | None:
        """Decode the sub-workflow setup activity's JSON result payload.

        When a credential payload codec is provided, the payload is decrypted
        first: credential-bearing setup results are stored ``binary/encrypted``
        in history, so a raw ``json.loads`` would throw and silently drop the
        child link and I/O summary. Non-encrypted payloads pass through
        unchanged. Returns the parsed dict, or ``None`` when the payload is
        absent or unparseable (defensive: the summaries are best-effort UI data).
        """
        if not attrs.result or not attrs.result.payloads:
            return None
        payload = attrs.result.payloads[0]
        try:
            if isinstance(codec, CredentialPayloadCodec):
                payload = codec.decode_payload(payload)
            result_data = json.loads(payload.data)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to decode/parse sub-workflow setup result", exc_info=True)
            return None
        return result_data if isinstance(result_data, dict) else None

    @staticmethod
    def _child_runtime_metadata(setup_result: dict[str, Any]) -> dict[str, Any] | None:
        """UI-relevant child identifiers for ``runtime_metadata``.

        Only the identifiers are surfaced; the child workflow definition carried in
        the setup result is never stored. Returns ``None`` when none are present.
        """
        child_metadata = {
            "child_execution_id": setup_result.get("execution_id"),
            "child_workflow_id": setup_result.get("child_workflow_id"),
            "child_workflow_name": setup_result.get("child_workflow_name"),
            "child_workflow_version": setup_result.get("child_workflow_version"),
        }
        if all(value is None for value in child_metadata.values()):
            return None
        return child_metadata

    @staticmethod
    def _build_subworkflow_io(setup_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Reconstruct the node's ``input_data``/``output_data`` summaries.

        Byte-for-byte the shapes the setup activity used to persist directly: the
        reference-mode invocation summary and the four-field child summary (same
        field names, ``.get()`` null behaviour, and ``or {}`` default). The large
        workflow definition in the result is deliberately not included.
        """
        input_data = {
            "execution_mode": "reference",
            "workflow_id": setup_result.get("child_workflow_id"),
            "workflow_name": setup_result.get("child_workflow_name"),
            "trigger_node_id": setup_result.get("trigger_node_id"),
            "input_parameters": scrub_credentials(setup_result.get("input_data") or {}),
        }
        output_data = {
            "workflow_id": setup_result.get("child_workflow_id"),
            "workflow_name": setup_result.get("child_workflow_name"),
            "child_workflow_version": setup_result.get("child_workflow_version"),
            "child_execution_id": setup_result.get("execution_id"),
        }
        return {"input": input_data, "output": output_data}

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
