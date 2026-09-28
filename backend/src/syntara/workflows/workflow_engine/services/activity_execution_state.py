"""Execution-level state transitions driven by Temporal workflow events."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.orm import selectinload
from sqlmodel import select
from temporalio.api.enums.v1 import EventType
from temporalio.api.history.v1 import HistoryEvent

from syntara.core.exceptions import SafeValueError
from syntara.telemetry.events.workflow_emitters import _map_execution_status_to_telemetry
from syntara.telemetry.events.workflow_error import TimedOutComponent
from syntara.workflows.audit.execution_completed import WorkflowCompletedEvent
from syntara.workflows.audit.execution_error import WorkflowExecutionErrorEvent
from syntara.workflows.models.activity_execution import TERMINAL_ACTIVITY_STATUSES, ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.utils.datetime import ensure_timezone_aware
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, NodeType
from syntara.workflows.workflow_engine.services.activity_sync_types import ExecutionMonitorMetadata

logger = structlog.stdlib.get_logger(__name__)
_COMPOSITE_ITER_SEP = "#iter-"


class ActivityExecutionStateMixin:
    """Workflow execution status transitions and terminal activity handling."""

    session_factory: Any
    _publish_activity_patches: Any
    _publish_snapshot: Any
    _dispatch_audit_event: Any

    def _extract_execution_status_from_event(self, event: HistoryEvent) -> tuple[ExecutionStatus, datetime, str | None]:  # noqa: C901, PLR0912
        """Extract execution status, completion time, and error from workflow completion event.

        Args:
            event: Temporal workflow completion event

        Returns:
            Tuple of (status, completed_at, error_details)

        Raises:
            ValueError: If event is not a workflow completion event

        """
        event_type = event.event_type
        completed_at = ensure_timezone_aware(event.event_time)
        error_details = None

        if event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED:
            # Check workflow result for internal failure status (e.g., node failures
            # that don't raise exceptions but return status: "failed" in the result)
            status = ExecutionStatus.COMPLETED
            completed_attrs = event.workflow_execution_completed_event_attributes
            if completed_attrs and completed_attrs.result and completed_attrs.result.payloads:
                try:
                    payload = completed_attrs.result.payloads[0]
                    result_data = json.loads(payload.data)
                    if isinstance(result_data, dict):
                        inner_status = result_data.get("status")
                        if inner_status == "cancelled":
                            status = ExecutionStatus.CANCELLED
                        elif inner_status == "failed":
                            status = ExecutionStatus.FAILED
                            error_details = self._extract_failed_activity_errors(result_data)
                        elif inner_status == "completed_with_errors":
                            status = ExecutionStatus.COMPLETED_WITH_ERRORS
                            error_details = self._extract_failed_activity_errors(result_data)
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to parse workflow result for failure detection", exc_info=True)
        elif event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED:
            status = ExecutionStatus.FAILED
            failed_attrs = event.workflow_execution_failed_event_attributes
            if failed_attrs and failed_attrs.failure:
                error_details = failed_attrs.failure.message
        elif event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CANCELED:
            status = ExecutionStatus.CANCELLED
        elif event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TIMED_OUT:
            status = ExecutionStatus.FAILED
            error_details = "Workflow execution timed out"
        elif event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TERMINATED:
            status = ExecutionStatus.CANCELLED
            error_details = "Workflow was forcibly terminated"
        else:
            msg = f"Event type {event_type} is not a workflow completion event"
            raise SafeValueError(msg)

        return status, completed_at, error_details

    @staticmethod
    def _extract_failed_activity_errors(result_data: dict[str, Any]) -> str:
        """Extract error messages from failed workflow activities.

        Uses failed_activities dict from the workflow result, which is always
        present when nodes fail (populated by _build_result in dynamic_workflow.py).

        Args:
            result_data: Workflow result dict containing failed_activities

        Returns:
            Human-readable error string with failed node details

        """
        failed_activities = result_data.get("failed_activities", {})
        if isinstance(failed_activities, dict) and failed_activities:
            errors = [f"{node_id}: {error}" for node_id, error in failed_activities.items()]
            return "; ".join(errors)
        return "One or more workflow activities failed"

    @staticmethod
    def _extract_failed_activities_from_event(event: HistoryEvent) -> dict[str, str]:
        """Extract ``failed_activities`` from a workflow completion event result.

        The workflow's ``_build_result`` always includes ``failed_activities``
        (a dict mapping node-ID → error-message) in the completion payload.
        This provides a reliable fallback when the ``get_failed_nodes`` Temporal
        query fails (e.g. due to a timeout or the workflow being closed before
        the query can execute).
        """
        if event.event_type != EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED:
            return {}
        completed_attrs = event.workflow_execution_completed_event_attributes
        if not completed_attrs or not completed_attrs.result or not completed_attrs.result.payloads:
            return {}
        try:
            result_data = json.loads(completed_attrs.result.payloads[0].data)
            if isinstance(result_data, dict):
                fa = result_data.get("failed_activities", {})
                if isinstance(fa, dict):
                    return fa
        except Exception:  # noqa: BLE001
            logger.debug("Could not parse failed_activities from workflow result", exc_info=True)
        return {}

    @staticmethod
    def _finalize_non_terminal_activities(
        execution: Execution,
        execution_id: UUID,
        failed_node_map: dict[str, str] | None = None,
    ) -> None:
        """Mark any non-terminal activities as skipped when a workflow completes.

        Safety net: when a workflow finishes, any activity still pending or running
        was effectively skipped (e.g. cancelled by an "any N" converge strategy).
        Activities already synced to a terminal status (FAILED, COMPLETED, SKIPPED,
        CANCELLED) by prior ``_sync_failed_nodes`` / ``_sync_skipped_nodes`` calls
        are left untouched.

        When ``failed_node_map`` is provided, activities whose base node ID
        appears in the map are marked FAILED (with the error message) instead
        of SKIPPED.  This handles nodes like loops that exceed max_iterations:
        the failure is recorded in the workflow state but may not have a
        corresponding Temporal activity event, so the prior DB sync could
        miss them.
        """
        now = datetime.now(UTC)
        finalized_count = 0
        for activity in execution.activities or []:
            if activity.status not in TERMINAL_ACTIVITY_STATUSES:
                base_name = activity.activity_name.split(_COMPOSITE_ITER_SEP)[0]
                error_msg = failed_node_map.get(base_name) if failed_node_map else None
                if error_msg is not None:
                    activity.status = ActivityStatus.FAILED
                    activity.error_details = error_msg
                else:
                    activity.status = ActivityStatus.SKIPPED
                activity.completed_at = now
                activity.updated_at = now
                finalized_count += 1
        if finalized_count:
            logger.info(
                "Finalized non-terminal activities",
                execution_id=execution_id,
                count=finalized_count,
            )

    async def _update_execution_status_from_event(
        self,
        metadata: ExecutionMonitorMetadata,
        event: HistoryEvent,
        failed_node_map: dict[str, str] | None = None,
    ) -> None:
        """Update execution status to terminal state when workflow completes.

        Args:
            metadata: Monitoring metadata containing execution and related data
            event: Temporal workflow completion event
            failed_node_map: Map of node ID to error message from ``_sync_failed_nodes``.
                Used as a fallback by ``_finalize_non_terminal_activities`` to mark
                nodes as FAILED rather than SKIPPED when the prior DB sync didn't
                persist in time for the fresh session to see it.

        """
        async with self.session_factory() as session:
            try:
                # Load execution with activities (selectinload respects relationship order_by)
                query = select(Execution).where(Execution.id == metadata.execution_id)
                query = query.options(selectinload(Execution.activities))  # type: ignore[arg-type]
                result = await session.exec(query)
                execution = result.one_or_none()

                if not execution:
                    logger.warning(
                        "Execution not found when processing workflow completion", execution_id=metadata.execution_id
                    )
                    return

                terminal_states = {
                    ExecutionStatus.COMPLETED,
                    ExecutionStatus.COMPLETED_WITH_ERRORS,
                    ExecutionStatus.FAILED,
                    ExecutionStatus.CANCELLED,
                }

                # Only update if not already in terminal state (idempotency)
                if execution.status in terminal_states:
                    logger.debug(
                        "Execution already in terminal state",
                        execution_id=metadata.execution_id,
                        status=execution.status.value,
                    )
                    return

                # Extract status, timestamp, and error details from event
                status, completed_at, error_details = self._extract_execution_status_from_event(event)

                # Ensure completed_at > created_at (database constraint)
                if completed_at <= execution.created_at:
                    completed_at = execution.created_at + timedelta(microseconds=1)
                    logger.warning(
                        "Workflow completed before execution created, adjusting",
                        temporal_workflow_id=execution.temporal_workflow_id,
                        completed_at=completed_at.isoformat(),
                        created_at=execution.created_at.isoformat(),
                        adjusted_completed_at=completed_at.isoformat(),
                    )

                # Update execution to terminal state
                execution.status = status
                execution.completed_at = completed_at
                execution.last_processed_event_id = event.event_id
                if error_details:
                    execution.error_details = error_details
                execution.updated_at = datetime.now(UTC)

                # If workflow was cancelled, mark running activities as cancelled and pending as skipped
                updated_activities: list[tuple[ActivityExecution, dict[str, Any]]] = []
                if status == ExecutionStatus.CANCELLED:
                    updated_activities = self._update_non_terminal_activities_on_cancel(execution, completed_at)

                # Safety net: mid-workflow sync (via _sync_skipped_nodes on converge/condition
                # completion) handles the fast path. This catches anything still non-terminal
                # if those earlier syncs missed it (e.g. query failure, race).
                self._finalize_non_terminal_activities(execution, metadata.execution_id, failed_node_map)

                await session.commit()

                logger.info(
                    "Updated execution to status at time",
                    execution_id=metadata.execution_id,
                    status=status.value,
                    completed_at=completed_at.isoformat(),
                )

                if updated_activities:
                    await self._publish_activity_patches(metadata, updated_activities)

                await self._publish_snapshot(execution, "final_snapshot")

                # Dispatch workflow-completed domain event through audit framework
                # (activity counts are now accurate after commit)
                activities = execution.activities or []
                node_count = sum(1 for a in activities if a.status in TERMINAL_ACTIVITY_STATUSES)
                error_count = sum(1 for a in activities if a.status == ActivityStatus.FAILED)
                duration_ms = int((completed_at - execution.created_at).total_seconds() * 1000)
                telemetry_status = _map_execution_status_to_telemetry(status)
                error_type: str | None = "ActivityExecutionError" if error_details else None
                trigger_type = next((a for a in ActivityName if a == execution.trigger_type), None)

                self._dispatch_audit_event(
                    WorkflowCompletedEvent(
                        execution_id=execution.id,
                        workflow_id=execution.workflow_id,
                        status=telemetry_status,
                        duration_ms=duration_ms,
                        node_count=node_count,
                        error_count=error_count,
                        error_type=error_type,
                        trigger_type=trigger_type,
                        interface=execution.interface,
                        request_id=metadata.request_id,
                        workflow_name=metadata.workflow_name,
                    )
                )

                # Emit workflow error telemetry for engine-level workflow timeouts
                if event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TIMED_OUT:
                    elapsed_time_ms = int((completed_at - execution.created_at).total_seconds() * 1000)
                    self._dispatch_audit_event(
                        WorkflowExecutionErrorEvent(
                            execution_id=metadata.execution_id,
                            workflow_id=metadata.workflow_id,
                            timed_out_component=TimedOutComponent.WORKFLOW,
                            configured_timeout_seconds=metadata.workflow_run_timeout_seconds or 0.0,
                            elapsed_time_ms=elapsed_time_ms,
                            error_type="WorkflowTimedOut",
                            request_id=metadata.request_id,
                            workflow_name=metadata.workflow_name,
                        )
                    )

            except Exception:
                await session.rollback()
                logger.exception(
                    "Error updating execution status from workflow completion event", execution_id=metadata.execution_id
                )
                raise

    def _update_non_terminal_activities_on_cancel(
        self,
        execution: Execution,
        cancelled_at: datetime,
    ) -> list[tuple[ActivityExecution, dict[str, Any]]]:
        """Mark unfinished activities when workflow is cancelled.

        In-flight activities (RUNNING, RETRYING, WAITING) are marked
        CANCELLED; PENDING activities are marked SKIPPED since they
        never started executing.

        Modifies activity objects already loaded in execution.activities.
        Returns list of (activity, old_values) tuples for JSON patch generation.
        """
        non_terminal_statuses = {
            ActivityStatus.PENDING,
            ActivityStatus.RUNNING,
            ActivityStatus.RETRYING,
            ActivityStatus.WAITING,
        }
        updated_activities: list[tuple[ActivityExecution, dict[str, Any]]] = []
        cancelled_count = 0
        skipped_count = 0

        for activity in execution.activities:
            if activity.status in non_terminal_statuses:
                old_values = {
                    "status": activity.status,
                    "started_at": activity.started_at,
                    "completed_at": activity.completed_at,
                    "error_details": activity.error_details,
                    "retry_count": activity.retry_count,
                    "output_data": activity.output_data,
                    "iteration": activity.iteration,
                }
                if activity.status == ActivityStatus.PENDING:
                    activity.status = ActivityStatus.SKIPPED
                    skipped_count += 1
                else:
                    activity.status = ActivityStatus.CANCELLED
                    activity.error_details = "Workflow was cancelled"
                    cancelled_count += 1
                activity.completed_at = cancelled_at
                activity.updated_at = datetime.now(UTC)
                updated_activities.append((activity, old_values))

        if updated_activities:
            logger.info(
                "Updated activities due to workflow cancellation",
                cancelled_count=cancelled_count,
                skipped_count=skipped_count,
                execution_id=execution.id,
            )

        return updated_activities

    async def _maybe_update_execution_paused_status(
        self,
        execution: Execution,
        activities: Sequence[ActivityExecution],
    ) -> ExecutionStatus | None:
        """Toggle execution between PAUSED and RUNNING based on activity states.

        Uses the already-loaded execution and activities from the caller's session
        to avoid an extra DB roundtrip.

        Pre-created PENDING placeholders are excluded — only activities that Temporal
        has actually started (non-PENDING) are considered.

        RUNNING -> PAUSED: when all non-PENDING non-terminal activities are WAITING
                           (no RUNNING or RETRYING).
        PAUSED -> RUNNING: when any activity is active, or no WAITING activities remain.
        """
        if execution.status not in (ExecutionStatus.RUNNING, ExecutionStatus.PAUSED):
            return None

        non_terminal = [a for a in activities if a.status not in TERMINAL_ACTIVITY_STATUSES]
        if not non_terminal:
            return None

        scheduled = [a for a in non_terminal if a.status != ActivityStatus.PENDING]
        if not scheduled:
            return None

        active_statuses = {ActivityStatus.RUNNING, ActivityStatus.RETRYING}
        has_active = any(a.status in active_statuses for a in scheduled)
        has_waiting = any(a.status == ActivityStatus.WAITING for a in scheduled)

        new_status: ExecutionStatus | None = None

        if execution.status == ExecutionStatus.RUNNING and has_waiting and not has_active:
            new_status = ExecutionStatus.PAUSED
        elif execution.status == ExecutionStatus.PAUSED and (has_active or not has_waiting):
            new_status = ExecutionStatus.RUNNING

        if new_status is None:
            return None

        execution.status = new_status
        execution.updated_at = datetime.now(UTC)

        logger.info(
            "Execution status transitioned",
            execution_id=execution.id,
            new_status=new_status.value,
        )
        return new_status

    def _update_approval_pending_flag(
        self,
        execution: Execution,
        activities: Sequence[ActivityExecution],
    ) -> bool | None:
        """Update execution.approval_pending based on current activity states.

        Returns the new flag value if changed, None if unchanged.
        """
        has_pending_approval = any(
            a.node_type == NodeType.APPROVAL and a.status == ActivityStatus.WAITING for a in activities
        )

        if execution.approval_pending != has_pending_approval:
            execution.approval_pending = has_pending_approval
            execution.updated_at = datetime.now(UTC)
            logger.info(
                "Execution approval_pending flag updated",
                execution_id=execution.id,
                approval_pending=has_pending_approval,
            )
            return has_pending_approval

        return None
