"""Background service for syncing activity executions from Temporal to database.

This service monitors running workflow executions and syncs activity data
to the database in real-time by streaming Temporal history events.
"""

import asyncio
import json
import random
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import structlog
from jsonpatch import JsonPatch  # type: ignore[import-untyped]
from sqlalchemy import or_
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.api.enums.v1 import EventType, PendingActivityState
from temporalio.api.history.v1 import HistoryEvent
from temporalio.client import Client, WorkflowHandle, WorkflowHistoryEventFilterType
from temporalio.exceptions import TemporalError

from syntara.audit.context_managers import actor_context
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.constants import FieldLimits
from syntara.core.exceptions import SafeValueError
from syntara.telemetry.events.workflow_emitters import (
    _map_execution_status_to_telemetry,
    emit_activities,
)
from syntara.telemetry.events.workflow_error import RETRY_REASON_MAX_LENGTH, TimedOutComponent
from syntara.workflows.audit.execution_completed import WorkflowCompletedEvent
from syntara.workflows.audit.execution_error import WorkflowExecutionErrorEvent
from syntara.workflows.audit.execution_started import WorkflowStartEvent
from syntara.workflows.models.activity_execution import TERMINAL_ACTIVITY_STATUSES, ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import ActivityData, Execution, ExecutionStatus
from syntara.workflows.models.visualization import JsonPatchOperation
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.activity_update_publisher import ActivityUpdatePublisher
from syntara.workflows.utils.datetime import ensure_timezone_aware
from syntara.workflows.workflow_engine.activities.common import (
    HEARTBEAT_PARTIAL_OUTPUT_KEY,
    HEARTBEAT_STOP_MONITOR,
)
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, NodeType
from syntara.workflows.workflow_engine.utils.credential_scrubber import scrub_credentials
from syntara.workflows.workflow_engine.utils.timeout_messages import build_timeout_error_message

PRE_RESOLVED_ACTIVITY_ID_PREFIX = "pre-resolved-"


logger = structlog.stdlib.get_logger(__name__)

# Retry parameters for querying activity output after Temporal marks an activity as
# completed but before the workflow loop stores the result in the resolver namespace.
# Uses exponential backoff: 100ms, 200ms, 400ms, 800ms, 1600ms (total ~3.1s).
_OUTPUT_QUERY_MAX_RETRIES = 5
_OUTPUT_QUERY_BASE_DELAY_MS = 100

# Temporal defers ACTIVITY_TASK_STARTED events until the activity completes,
# so the sync service never sees RUNNING status for in-flight activities.
# After SCHEDULED, we probe describe() to detect the real state, retrying
# with exponential backoff if the activity hasn't been picked up yet.
_DESCRIBE_PROBE_INITIAL_DELAY_S = 1.0
_DESCRIBE_PROBE_MAX_DELAY_S = 30.0
_DESCRIBE_PROBE_BACKOFF_FACTOR = 2.0
_DESCRIBE_PROBE_MAX_TOTAL_S = 600.0  # 10 minutes
_DESCRIBE_PROBE_MAX_TASKS = 25

_ITER_SUFFIX_RE = re.compile(r"_iter_\d+$")
_ITER_CAPTURE_RE = re.compile(r"_iter_(\d+)$")

# Wire-format separator for per-iteration composite keys (e.g. "body-1#iter-2").
# Mirrored in frontend: packages/syntara-ui/src/routes/workflows/execution/utils/activityState.ts
_COMPOSITE_ITER_SEP = "#iter-"

_PENDING_ACTIVITY_STATE_STARTED = PendingActivityState.PENDING_ACTIVITY_STATE_STARTED

# Retry parameters for the _monitor_execution loop when transient errors
# (e.g. DB pool exhaustion, brief network blips) kill the monitoring task.
_MONITOR_RETRY_BASE_DELAY_S = 1.0
_MONITOR_RETRY_MAX_DELAY_S = 30.0
_MONITOR_RETRY_BACKOFF_FACTOR = 2.0
_MONITOR_RETRY_JITTER_FACTOR = 0.5


@dataclass
class SyntheticActivityStarted:
    """Synthetic STARTED event produced by describe() probing.

    Temporal defers ACTIVITY_TASK_STARTED until the activity completes,
    so in-flight activities stay PENDING in the DB. When describe() detects
    an activity is actually running, this event is pushed into the shared
    queue so the single consumer can update the status to RUNNING.
    """

    activity_id: str
    scheduled_event_id: int


@dataclass
class SyntheticPartialOutput:
    """Partial output extracted from heartbeat details during describe() probing.

    Pushed into the queue after a SyntheticActivityStarted event, when the
    activity's heartbeat contains HEARTBEAT_STOP_MONITOR with partial output
    data (e.g. job_id, job_url). Written to the DB as early output_data
    before the activity completes.
    """

    activity_id: str
    scheduled_event_id: int
    partial_output: dict[str, Any]


_QueueItem = HistoryEvent | SyntheticActivityStarted | SyntheticPartialOutput | None


@dataclass
class ExecutionMonitorMetadata:
    """Metadata required for monitoring a workflow execution.

    This contains all the necessary data structures for monitoring
    and syncing activity executions from Temporal to the database.

    Attributes:
        execution_id: Database execution ID being monitored
        last_processed_event_id: Last event ID that was processed and synced
        activity_definitions_map: Map of activity ID to activity definition from workflow
        activity_index_map: Map of activity names to their indices in the activities list
        pending_activity_updates: Map of event IDs to activity update data awaiting database sync
        pending_sync_event_ids: Set of event IDs that need to be synced to database
        request_id: Optional X-Request-Id (UUID) from the originating HTTP request, for telemetry correlation
        workflow_name: Name of the workflow (for audit events)

    """

    execution_id: UUID
    last_processed_event_id: int
    activity_definitions_map: dict[str, dict[str, Any]]
    activity_index_map: dict[str, int]
    pending_activity_updates: dict[int, dict[str, Any]]
    pending_sync_event_ids: set[int] = field(default_factory=set)
    terminal_activity_ids: set[str] = field(default_factory=set)
    iteration_counters: dict[str, int] = field(default_factory=dict)
    next_activity_index: int = 0
    workflow_id: UUID | None = None
    request_id: UUID | None = None
    workflow_run_timeout_seconds: float | None = None
    workflow_name: str | None = None


class ActivitySyncService:
    """Service for syncing activity executions from Temporal to database in real-time."""

    def __init__(
        self,
        temporal_client: Client,
        session_factory: async_sessionmaker[AsyncSession],
        activity_publisher: ActivityUpdatePublisher | None = None,
    ) -> None:
        """Initialize activity sync service.

        Args:
            temporal_client: Temporal client for workflow operations
            session_factory: AsyncSession factory (async_sessionmaker)
            activity_publisher: Publisher for streaming activity updates to Redis (optional)

        """
        self.temporal_client = temporal_client
        self.session_factory = session_factory
        self.activity_publisher = activity_publisher or ActivityUpdatePublisher()
        self._sync_tasks: dict[str, asyncio.Task[None]] = {}
        self._shutdown = False

    def is_monitoring_execution(self, execution_id: UUID) -> bool:
        """Check if an execution is currently being monitored.

        Args:
            execution_id: Database execution ID

        Returns:
            True if monitoring is active for this execution, False otherwise

        """
        task_key = str(execution_id)
        return task_key in self._sync_tasks

    def start_monitoring_execution(
        self,
        execution_id: UUID,
        temporal_workflow_id: str,
        *,
        request_id: UUID | None = None,
    ) -> None:
        """Start background monitoring for a specific execution.

        Monitoring continues until the workflow completes or the service shuts down.

        Args:
            execution_id: Database execution ID
            temporal_workflow_id: Temporal workflow ID
            request_id: Optional X-Request-Id from the originating HTTP request

        """
        task_key = str(execution_id)

        if task_key in self._sync_tasks:
            logger.warning("Already monitoring execution", execution_id=execution_id)
            return

        logger.info("Starting activity sync monitoring for execution", execution_id=execution_id)

        # Create background task to monitor this execution
        task = asyncio.create_task(
            self._monitor_execution(execution_id, temporal_workflow_id, request_id=request_id),
            name=f"activity_sync_{execution_id}",
        )
        self._sync_tasks[task_key] = task

        # Add cleanup callback when task completes
        task.add_done_callback(lambda t: self._cleanup_task(execution_id, t))

    def _cleanup_task(self, execution_id: UUID, task: asyncio.Task[None]) -> None:
        """Clean up completed monitoring task.

        Args:
            execution_id: Database execution ID
            task: Completed task

        """
        task_key = str(execution_id)
        self._sync_tasks.pop(task_key, None)

        if task.cancelled():
            logger.debug("Monitoring task for execution was cancelled", execution_id=execution_id)
        elif task.exception():
            logger.error("Monitoring task for execution failed", execution_id=execution_id, error=str(task.exception()))
        else:
            logger.info("Monitoring task for execution completed successfully", execution_id=execution_id)

    async def _publish_snapshot(
        self,
        execution_or_id: UUID | Execution,
        snapshot_type: Literal["initial_snapshot", "final_snapshot"],
    ) -> None:
        """Publish an execution snapshot (best-effort).

        Accepts either a UUID (loads from DB with activities) or an already-loaded
        Execution instance (skips the query).

        Args:
            execution_or_id: Execution UUID or loaded Execution object.
            snapshot_type: Either ``"initial_snapshot"`` or ``"final_snapshot"``.

        """
        execution_id = execution_or_id if isinstance(execution_or_id, UUID) else execution_or_id.id
        try:
            if isinstance(execution_or_id, UUID):
                async with self.session_factory() as session:
                    query = select(Execution).where(Execution.id == execution_or_id)
                    query = query.options(selectinload(Execution.activities))  # type: ignore[arg-type]
                    result = await session.exec(query)
                    resolved = result.one_or_none()
                    if not resolved:
                        logger.warning(
                            "Execution not found for snapshot", execution_id=execution_id, snapshot_type=snapshot_type
                        )
                        return
            else:
                resolved = execution_or_id
            await self.activity_publisher.publish_snapshot(resolved, snapshot_type)
            logger.debug("Published snapshot for execution", execution_id=execution_id, snapshot_type=snapshot_type)
        except Exception:
            logger.exception(
                "Failed to publish snapshot (non-fatal)", execution_id=execution_id, snapshot_type=snapshot_type
            )

    async def _publish_execution_patch(
        self,
        execution_id: UUID,
        ops: list[JsonPatchOperation],
    ) -> None:
        """Publish execution-level field changes as JSON Patch operations (best-effort).

        Args:
            execution_id: Execution UUID.
            ops: JSON Patch operations to broadcast.

        """
        try:
            await self.activity_publisher.publish_execution_patch(execution_id, ops)
        except Exception:
            logger.exception(
                "Failed to publish execution patch (non-fatal)",
                execution_id=execution_id,
            )

    async def _update_execution_to_running(self, metadata: ExecutionMonitorMetadata, event: HistoryEvent) -> None:
        """Update execution status to RUNNING when workflow starts.

        Only updates if execution is in PENDING state (idempotent for service restarts).

        Args:
            metadata: Monitoring metadata containing execution and related data
            event: Temporal workflow started event

        """
        started_attrs = event.workflow_execution_started_event_attributes
        if started_attrs and started_attrs.workflow_run_timeout and started_attrs.workflow_run_timeout.seconds > 0:
            metadata.workflow_run_timeout_seconds = started_attrs.workflow_run_timeout.seconds + (
                started_attrs.workflow_run_timeout.nanos / 1e9
            )

        async with self.session_factory() as session:
            try:
                result = await session.exec(select(Execution).where(Execution.id == metadata.execution_id))
                execution = result.one_or_none()

                if not execution:
                    logger.warning("Execution not found when updating to RUNNING", execution_id=metadata.execution_id)
                    return

                # Only update if currently PENDING (defensive check for race conditions)
                if execution.status == ExecutionStatus.PENDING:
                    execution.status = ExecutionStatus.RUNNING
                    execution.last_processed_event_id = event.event_id
                    execution.updated_at = datetime.now(UTC)
                    await session.commit()
                    logger.info("Updated execution to RUNNING status", execution_id=metadata.execution_id)

                    await self._publish_execution_patch(
                        metadata.execution_id,
                        [JsonPatchOperation(op="replace", path="/status", value=ExecutionStatus.RUNNING.value)],
                    )

                    # Dispatch workflow-start domain event through audit framework
                    trigger_activity_type = self._extract_trigger_activity_type(metadata.activity_definitions_map)
                    workflow_name = metadata.workflow_name
                    if not workflow_name:
                        workflow_name = "unknown"
                        logger.warning(
                            "Workflow name missing from execution metadata, using fallback",
                            execution_id=str(metadata.execution_id),
                        )
                    AuditEventDispatcher.dispatch(
                        WorkflowStartEvent(
                            execution_id=execution.id,
                            workflow_id=execution.workflow_id,
                            workflow_name=workflow_name,
                            trigger_type=trigger_activity_type,
                            interface=execution.interface,
                            request_id=metadata.request_id,
                        )
                    )
                else:
                    logger.debug(
                        "Skipping RUNNING update for execution - already in state",
                        execution_id=metadata.execution_id,
                        current_status=execution.status.value,
                    )
            except Exception:
                await session.rollback()
                logger.exception("Error updating execution to RUNNING", execution_id=metadata.execution_id)
                # Don't raise - this is non-critical, monitoring should continue

    async def shutdown(self) -> None:
        """Shutdown all monitoring tasks gracefully."""
        logger.info("Shutting down activity sync service...")
        self._shutdown = True

        # Cancel all running tasks
        for task in self._sync_tasks.values():
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete
        if self._sync_tasks:
            await asyncio.gather(*self._sync_tasks.values(), return_exceptions=True)

        self._sync_tasks.clear()
        logger.info("Activity sync service shutdown complete")

    _TEMPORAL_TERMINAL_STATUSES: frozenset[str] = frozenset(
        {
            "COMPLETED",
            "FAILED",
            "CANCELED",
            "CANCELLED",
            "TIMED_OUT",
            "TERMINATED",
        }
    )

    async def reconcile_stale_executions(self) -> None:
        """Reconcile executions stuck in RUNNING status after a worker restart.

        Queries the database for executions in RUNNING status, checks each
        one's Temporal workflow status, and updates the DB for any that have
        already completed in Temporal. Executions still running in Temporal
        are skipped to avoid duplicate monitoring across workers.
        """
        try:
            async with self.session_factory() as session:
                query = (
                    select(Execution)
                    .where(Execution.status == ExecutionStatus.RUNNING)
                    .options(selectinload(Execution.activities))  # type: ignore[arg-type]
                )
                result = await session.exec(query)
                stale_executions = result.all()

            if not stale_executions:
                logger.info("No stale executions found during startup reconciliation")
                return

            logger.info("Found executions to reconcile", count=len(stale_executions))

            reconciled = 0

            for execution in stale_executions:
                try:
                    outcome = await self._reconcile_single_execution(execution)
                    if outcome == "reconciled":
                        reconciled += 1
                except TemporalError:
                    logger.warning(
                        "Temporal error during reconciliation, skipping",
                        execution_id=execution.id,
                        exc_info=True,
                    )
                except Exception:
                    logger.exception("Error reconciling execution, skipping", execution_id=execution.id)

            logger.info(
                "Startup reconciliation complete",
                reconciled_to_terminal=reconciled,
                total_checked=len(stale_executions),
            )

        except Exception:
            logger.exception("Failed to query stale executions during reconciliation")

    async def _reconcile_single_execution(
        self,
        execution: Execution,
    ) -> Literal["reconciled", "skipped"]:
        """Reconcile a single stale execution against Temporal."""
        handle = self.temporal_client.get_workflow_handle(execution.temporal_workflow_id)
        description = await handle.describe()
        status_name = description.status.name.upper() if description.status else "UNKNOWN"

        if status_name not in self._TEMPORAL_TERMINAL_STATUSES:
            return "skipped"

        # Workflow completed in Temporal — fetch the close event and update DB
        history = await handle.fetch_history(
            event_filter_type=WorkflowHistoryEventFilterType.CLOSE_EVENT,
        )
        close_event = next(iter(history.events), None)
        if close_event:
            status, completed_at, error_details = self._extract_execution_status_from_event(close_event)
        else:
            logger.warning(
                "No close event found for completed workflow, forcing FAILED",
                execution_id=execution.id,
                temporal_workflow_id=execution.temporal_workflow_id,
            )
            status = ExecutionStatus.FAILED
            completed_at = datetime.now(UTC)
            error_details = "Workflow completed in Temporal but close event could not be retrieved"

        async with self.session_factory() as session:
            query = (
                select(Execution).where(Execution.id == execution.id).options(selectinload(Execution.activities))  # type: ignore[arg-type]
            )
            result = await session.exec(query)
            fresh_execution = result.one_or_none()
            if not fresh_execution or fresh_execution.status != ExecutionStatus.RUNNING:
                return "skipped"

            if completed_at <= fresh_execution.created_at:
                completed_at = fresh_execution.created_at + timedelta(microseconds=1)

            fresh_execution.status = status
            fresh_execution.completed_at = completed_at
            if error_details:
                fresh_execution.error_details = error_details
            fresh_execution.updated_at = datetime.now(UTC)
            await session.commit()

        await self._publish_snapshot(execution.id, "final_snapshot")
        logger.info("Reconciled stale execution", execution_id=execution.id, new_status=status.value)
        return "reconciled"

    async def _initialize_monitoring(
        self,
        execution_id: UUID,
        *,
        request_id: UUID | None = None,
    ) -> ExecutionMonitorMetadata:
        """Initialize monitoring by fetching execution data and workflow structure.

        Args:
            execution_id: Database execution ID
            request_id: Optional X-Request-Id from the originating HTTP request

        Returns:
            ExecutionMonitorMetadata containing execution and related data structures

        Raises:
            RuntimeError: If execution not found in database

        """
        async with self.session_factory() as session:
            result = await session.exec(select(Execution).where(Execution.id == execution_id))
            execution = result.one_or_none()

            if not execution:
                msg = f"Execution {execution_id} not found in database"
                logger.error(msg)
                raise RuntimeError(msg)

            # Extract needed fields from execution
            workflow_id = execution.workflow_id
            workflow_version_id = execution.workflow_version_id
            last_processed_event_id = execution.last_processed_event_id

            # Load workflow name for audit events
            workflow_result = await session.exec(select(Workflow).where(Workflow.id == workflow_id))
            workflow = workflow_result.one_or_none()
            if not workflow:
                msg = f"Workflow {workflow_id} not found in database"
                logger.error(msg)
                raise RuntimeError(msg)
            workflow_name = workflow.name

        activity_definitions_map = await self._fetch_activity_definitions_map(workflow_version_id)

        await self._create_all_activities_upfront(execution_id, activity_definitions_map)

        # Build activity index map after activities are created (for patch generation)
        activity_index_map = await self._build_activity_index_map(execution_id)

        # Rebuild loop-iteration state from existing DB records so that
        # monitor restarts mid-loop correctly recognise body children as
        # iterations and avoid duplicate #iter-N creation.
        iteration_counters: dict[str, int] = {}
        for key in activity_index_map:
            if _COMPOSITE_ITER_SEP in key:
                base_id, _, num_str = key.rpartition(_COMPOSITE_ITER_SEP)
                try:
                    num = int(num_str)
                except ValueError:
                    continue
                if num > iteration_counters.get(base_id, 0):
                    iteration_counters[base_id] = num

        terminal_activity_ids = await self._load_terminal_activity_ids(execution_id)

        return ExecutionMonitorMetadata(
            execution_id=execution_id,
            last_processed_event_id=last_processed_event_id,
            activity_definitions_map=activity_definitions_map,
            activity_index_map=activity_index_map,
            next_activity_index=len(activity_index_map),
            pending_activity_updates={},
            terminal_activity_ids=terminal_activity_ids,
            iteration_counters=iteration_counters,
            workflow_id=workflow_id,
            request_id=request_id,
            workflow_name=workflow_name,
        )

    async def _build_activity_index_map(self, execution_id: UUID) -> dict[str, int]:
        """Build mapping from activity_name to index in activities list.

        This mapping is used for JSON Patch generation to identify activity positions
        in the activities array without repeatedly querying the database.

        Args:
            execution_id: Database execution ID

        Returns:
            Dictionary mapping activity_name to its index in the ordered activities list

        """
        async with self.session_factory() as session:
            result = await session.exec(
                select(ActivityExecution)
                .where(ActivityExecution.execution_id == execution_id)
                .order_by(ActivityExecution.created_at, ActivityExecution.activity_name)  # type: ignore[arg-type]
            )
            activities = result.all()
            return {activity.activity_name: idx for idx, activity in enumerate(activities)}

    async def _load_terminal_activity_ids(self, execution_id: UUID) -> set[str]:
        """Load activity IDs that have reached terminal status from the database."""
        async with self.session_factory() as session:
            result = await session.exec(
                select(ActivityExecution.activity_name).where(
                    ActivityExecution.execution_id == execution_id,
                    ActivityExecution.status.in_(TERMINAL_ACTIVITY_STATUSES),  # type: ignore[attr-defined]
                    ~ActivityExecution.activity_name.contains(_COMPOSITE_ITER_SEP),  # type: ignore[attr-defined]
                )
            )
            return set(result.all())

    async def _handle_event_post_processing(
        self,
        event: HistoryEvent,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
    ) -> int | None:
        """Handle post-processing after an event is processed.

        Args:
            event: Temporal history event
            metadata: Monitoring metadata containing execution and related data
            handle: Workflow handle

        Returns:
            Event ID if sync was performed, None otherwise

        """
        # Sync skipped nodes after control node completions that cause branching
        if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED:
            attrs = event.activity_task_completed_event_attributes
            scheduled_id = attrs.scheduled_event_id

            if scheduled_id in metadata.pending_activity_updates:
                activity_id = metadata.pending_activity_updates[scheduled_id]["activity_id"]
                # Check if this is a control node that causes branch skipping
                activity_def = metadata.activity_definitions_map.get(activity_id, {})
                activity_type = activity_def.get("type")

                if (
                    activity_type in (NodeType.CONDITION, NodeType.APPROVAL, NodeType.CONVERGE, NodeType.SWITCH)
                    or activity_type in self._TRIGGER_ACTIVITY_TYPES
                ):
                    await self._sync_skipped_nodes(metadata, handle)

        if event.event_type in {
            EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED,
            EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED,
            EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED,
            EventType.EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT,
            EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED,
        }:
            # Update metadata with the event ID before syncing
            metadata.last_processed_event_id = event.event_id
            await self._sync_activities_to_db(metadata, handle)
            return event.event_id

        # Sync SCHEDULED events for loop iterations so per-iteration
        # records are created as PENDING before the STARTED event arrives
        if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            update = metadata.pending_activity_updates.get(event.event_id)
            if update and update.get("_is_loop_iteration"):
                metadata.last_processed_event_id = event.event_id
                await self._sync_activities_to_db(metadata, handle)
                return event.event_id

        return None

    async def _history_event_producer(
        self,
        handle: WorkflowHandle[Any, Any],
        queue: asyncio.Queue[_QueueItem],
        execution_id: UUID,
    ) -> None:
        """Stream Temporal history events into the shared queue.

        Pushes ``None`` as a sentinel when the history stream ends.
        """
        try:
            async for event in handle.fetch_history_events(page_size=100, wait_new_event=True):
                if self._shutdown:
                    break
                await queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("History event producer error", execution_id=execution_id)
        finally:
            await queue.put(None)

    @staticmethod
    def _extract_heartbeat_data(
        pa: Any,  # noqa: ANN401 — PendingActivityInfo from protobuf
    ) -> dict[str, Any] | None:
        """Decode the latest heartbeat payload from a pending activity.

        Returns the decoded dict if heartbeat_details contains a JSON payload,
        or None if no heartbeat has been sent yet.
        """
        hb = pa.heartbeat_details
        if not hb or not hb.payloads:
            return None
        try:
            result: dict[str, Any] = json.loads(hb.payloads[0].data)
            return result
        except (json.JSONDecodeError, IndexError, AttributeError, TypeError):
            logger.debug("Failed to decode heartbeat payload", activity_id=pa.activity_id)
            return None

    async def _probe_handle_disappeared(
        self,
        queue: asyncio.Queue[_QueueItem],
        activity_id: str,
        scheduled_event_id: int,
        *,
        started: bool,
    ) -> bool:
        """Handle the case where a pending activity disappears from describe().

        Pushes SyntheticActivityStarted if the activity hasn't been marked as
        started yet (it completed before we observed STARTED state).

        Returns True if the probe should exit, False otherwise.
        """
        if not started:
            await queue.put(
                SyntheticActivityStarted(
                    activity_id=activity_id,
                    scheduled_event_id=scheduled_event_id,
                )
            )
        return True

    async def _probe_check_heartbeat(
        self,
        queue: asyncio.Queue[_QueueItem],
        activity_id: str,
        scheduled_event_id: int,
        pa: Any,  # noqa: ANN401 — PendingActivityInfo from protobuf
    ) -> bool:
        """Check heartbeat data for STOP_MONITOR signal and push partial output.

        Examines the heartbeat payload of a running activity. If the heartbeat
        contains HEARTBEAT_STOP_MONITOR, pushes SyntheticPartialOutput (when
        partial_output data exists) and signals the probe to exit.

        Returns True if the probe should exit, False otherwise.
        """
        hb_data = self._extract_heartbeat_data(pa)
        if hb_data and hb_data.get(HEARTBEAT_STOP_MONITOR):
            partial_output = hb_data.get(HEARTBEAT_PARTIAL_OUTPUT_KEY)
            if partial_output:
                await queue.put(
                    SyntheticPartialOutput(
                        activity_id=activity_id,
                        scheduled_event_id=scheduled_event_id,
                        partial_output=partial_output,
                    )
                )
            return True
        return False

    async def _schedule_describe_probe(
        self,
        handle: WorkflowHandle[Any, Any],
        queue: asyncio.Queue[_QueueItem],
        activity_id: str,
        scheduled_event_id: int,
    ) -> None:
        """Probe describe() to detect STARTED state and heartbeat partial output.

        Two phases in one loop, each triggers a separate DB sync:
        Phase 1 — wait for state == STARTED → push SyntheticActivityStarted
                  so the DB transitions the activity to RUNNING immediately.
        Phase 2 — wait for heartbeat containing HEARTBEAT_STOP_MONITOR →
                  push SyntheticPartialOutput so the DB gets early output_data
                  (e.g. job_id, job_url) before the activity completes.

        The phases are independent: if the activity completes before the
        heartbeat arrives, only phase 1 fires. If the heartbeat is already
        present when STARTED is detected, both fire in the same iteration.
        """
        delay = _DESCRIBE_PROBE_INITIAL_DELAY_S
        elapsed = 0.0
        started = False

        # NOSONAR: polling is intentional; history events arrive too late
        while elapsed < _DESCRIBE_PROBE_MAX_TOTAL_S and not self._shutdown:
            await asyncio.sleep(delay)
            elapsed += delay

            try:
                desc = await handle.describe()
                pending_map = {pa.activity_id: pa for pa in desc.raw_description.pending_activities}
                pa = pending_map.get(activity_id)

                if pa is None and await self._probe_handle_disappeared(
                    queue, activity_id, scheduled_event_id, started=started
                ):
                    return

                # Phase 1: detect STARTED → immediate status update
                if not started and pa is not None and pa.state == _PENDING_ACTIVITY_STATE_STARTED:
                    started = True
                    await queue.put(
                        SyntheticActivityStarted(
                            activity_id=activity_id,
                            scheduled_event_id=scheduled_event_id,
                        )
                    )
                    delay = _DESCRIBE_PROBE_INITIAL_DELAY_S

                # Phase 2: wait for STOP_MONITOR in heartbeat → partial output
                if (
                    started
                    and pa is not None
                    and await self._probe_check_heartbeat(queue, activity_id, scheduled_event_id, pa)
                ):
                    return

                delay = min(delay * _DESCRIBE_PROBE_BACKOFF_FACTOR, _DESCRIBE_PROBE_MAX_DELAY_S)

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Describe probe failed",
                    activity_id=activity_id,
                )
                delay = min(delay * _DESCRIBE_PROBE_BACKOFF_FACTOR, _DESCRIBE_PROBE_MAX_DELAY_S)

    async def _process_synthetic_activity_started(
        self,
        event: SyntheticActivityStarted,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
    ) -> None:
        """Process a synthetic STARTED event from describe() probing.

        Sets the activity to RUNNING (or WAITING for approval nodes) and
        syncs to the database.
        """
        update = metadata.pending_activity_updates.get(event.scheduled_event_id)
        if not update or update["status"] != ActivityStatus.PENDING:
            return

        activity_def = metadata.activity_definitions_map.get(event.activity_id, {})
        activity_type = activity_def.get("type")
        new_status = (
            ActivityStatus.WAITING if activity_type in (NodeType.APPROVAL, NodeType.WAIT) else ActivityStatus.RUNNING
        )

        update["status"] = new_status
        update["started_at"] = datetime.now(UTC)

        logger.info(
            "Describe probe: activity started",
            activity_id=event.activity_id,
            execution_id=metadata.execution_id,
            status=new_status.value,
        )
        metadata.pending_sync_event_ids.add(event.scheduled_event_id)
        await self._sync_activities_to_db(metadata, handle)

    async def _process_synthetic_partial_output(
        self,
        event: SyntheticPartialOutput,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
    ) -> None:
        """Process partial output from heartbeat details.

        Writes early output_data (e.g. job_id, job_url) to the activity
        before the activity completes. Only updates if the activity is
        still in a non-terminal state.
        """
        update = metadata.pending_activity_updates.get(event.scheduled_event_id)
        if not update:
            return

        update["output_data"] = event.partial_output

        logger.info(
            "Describe probe: partial output received",
            activity_id=event.activity_id,
            execution_id=metadata.execution_id,
            partial_output_keys=list(event.partial_output.keys()),
        )
        metadata.pending_sync_event_ids.add(event.scheduled_event_id)
        await self._sync_activities_to_db(metadata, handle)

    async def _process_history_event(
        self,
        event: HistoryEvent,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
        queue: asyncio.Queue[_QueueItem],
        probe_tasks: list[asyncio.Task[None]],
    ) -> bool:
        """Process a single Temporal history event.

        Returns False if the monitor loop should stop (shutdown requested).
        """
        if event.event_id <= metadata.last_processed_event_id:
            return True

        # Handle workflow execution started event
        if event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED:
            await self._update_execution_to_running(metadata, event)
            metadata.last_processed_event_id = event.event_id
            return True

        # Handle workflow completion events
        if event.event_type in {
            EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED,
            EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED,
            EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CANCELED,
            EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TIMED_OUT,
            EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TERMINATED,
        }:
            # Sync failed and skipped nodes BEFORE finalizing the execution.
            # _update_execution_status_from_event calls _finalize_non_terminal_activities
            # which marks any remaining PENDING activities as SKIPPED. By syncing first,
            # converge nodes that were failed in the workflow (via _fail_converge_node)
            # are already FAILED in the DB, so _finalize_non_terminal_activities skips them.
            failed_node_map = await self._sync_failed_nodes(metadata, handle)
            if failed_node_map is None:
                failed_node_map = self._extract_failed_activities_from_event(event)
            await self._sync_skipped_nodes(metadata, handle)
            await self._update_execution_status_from_event(metadata, event, failed_node_map)
            metadata.last_processed_event_id = event.event_id
            return True

        # Process activity events
        self._process_activity_event(event, metadata)

        synced_event_id = await self._handle_event_post_processing(event, metadata, handle)
        if synced_event_id:
            metadata.last_processed_event_id = synced_event_id

        # Launch describe probe after SCHEDULED events.
        # Probe tasks complete quickly once the activity starts (single describe() call),
        # so hitting the cap is unlikely in practice. If the cap is reached, the only
        # impact is that the activity stays PENDING in the DB until the real STARTED
        # event arrives with the COMPLETED event — status is reported late, not lost.
        if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            attrs = event.activity_task_scheduled_event_attributes
            if attrs and not attrs.activity_id.startswith("__internal__"):
                probe_tasks[:] = [t for t in probe_tasks if not t.done()]
                if len(probe_tasks) < _DESCRIBE_PROBE_MAX_TASKS:
                    activity_id = _ITER_SUFFIX_RE.sub("", attrs.activity_id)
                    probe_tasks.append(
                        asyncio.create_task(
                            self._schedule_describe_probe(
                                handle,
                                queue,
                                activity_id,
                                event.event_id,
                            )
                        )
                    )

        return True

    async def _dispatch_queue_item(
        self,
        item: _QueueItem,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
        queue: asyncio.Queue[_QueueItem],
        probe_tasks: list[asyncio.Task[None]],
        execution_id: UUID,
    ) -> bool:
        """Dispatch a single queue item to the appropriate handler.

        Handles the isinstance chain for SyntheticActivityStarted,
        SyntheticPartialOutput, shutdown check, and history event processing.

        Args:
            item: Queue item to dispatch
            metadata: Monitoring metadata
            handle: Workflow handle
            queue: Shared event queue
            probe_tasks: List of active probe tasks
            execution_id: Database execution ID

        Returns:
            True to continue the loop, False to break out of it.

        """
        if isinstance(item, SyntheticActivityStarted):
            await self._process_synthetic_activity_started(item, metadata, handle)
            return True

        if isinstance(item, SyntheticPartialOutput):
            await self._process_synthetic_partial_output(item, metadata, handle)
            return True

        if self._shutdown:
            logger.info(
                "Shutdown requested, stopping monitoring for execution",
                execution_id=execution_id,
            )
            return False

        if not isinstance(item, HistoryEvent):
            return True
        return await self._process_history_event(
            item,
            metadata,
            handle,
            queue,
            probe_tasks,
        )

    @staticmethod
    async def _cancel_background_tasks(
        producer_task: asyncio.Task[None] | None,
        probe_tasks: list[asyncio.Task[None]],
    ) -> None:
        """Cancel producer and probe tasks, then gather them.

        Args:
            producer_task: History event producer task (may be None)
            probe_tasks: List of active describe-probe tasks

        """
        if producer_task is not None:
            producer_task.cancel()
        for t in probe_tasks:
            t.cancel()
        all_tasks = ([producer_task] if producer_task is not None else []) + probe_tasks
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)

    async def _monitor_execution(
        self,
        execution_id: UUID,
        temporal_workflow_id: str,
        *,
        request_id: UUID | None = None,
    ) -> None:
        """Monitor a single execution and sync activities to database.

        Uses a shared asyncio.Queue so that Temporal history events and
        describe-probe results are processed by a single consumer, avoiding
        race conditions between the two sources.

        Transient errors (DB pool exhaustion, brief network blips) trigger
        retries with exponential backoff. The event stream is re-established
        from the last successfully processed event on each retry. Retries
        stop once the execution reaches a terminal state or the service shuts
        down.

        Args:
            execution_id: Database execution ID
            temporal_workflow_id: Temporal workflow ID
            request_id: Optional X-Request-Id from the originating HTTP request

        """
        try:
            logger.info(
                "Starting activity monitor for execution (temporal)",
                execution_id=execution_id,
                temporal_workflow_id=temporal_workflow_id,
            )

            handle: WorkflowHandle[Any, Any] = self.temporal_client.get_workflow_handle(temporal_workflow_id)

            metadata = await self._initialize_monitoring(execution_id, request_id=request_id)

            delay = _MONITOR_RETRY_BASE_DELAY_S
            attempt = 0

            while not self._shutdown:
                completed = await self._run_monitor_loop(handle, metadata, execution_id)
                if completed:
                    break

                attempt += 1
                logger.warning(
                    "Retrying activity monitor after transient error",
                    execution_id=execution_id,
                    attempt=attempt,
                    delay_s=delay,
                )
                jitter = (1 - _MONITOR_RETRY_JITTER_FACTOR) + random.random() * _MONITOR_RETRY_JITTER_FACTOR  # noqa: S311
                jittered_delay = delay * jitter
                await asyncio.sleep(jittered_delay)
                delay = min(delay * _MONITOR_RETRY_BACKOFF_FACTOR, _MONITOR_RETRY_MAX_DELAY_S)

        except asyncio.CancelledError:
            logger.info("Activity monitoring cancelled for execution", execution_id=execution_id)
            raise
        except TemporalError as e:
            logger.warning(
                "Temporal error while monitoring execution, will not retry",
                execution_id=execution_id,
                error=str(e),
            )
        except Exception:
            logger.exception("Error monitoring execution", execution_id=execution_id)

    async def _run_monitor_loop(
        self,
        handle: WorkflowHandle[Any, Any],
        metadata: ExecutionMonitorMetadata,
        execution_id: UUID,
    ) -> bool:
        """Run a single attempt of the event-processing monitor loop.

        Returns True when monitoring completed normally (execution finished
        or service is shutting down). Returns False when a transient error
        occurred and the caller should retry.
        """
        queue: asyncio.Queue[_QueueItem] = asyncio.Queue()
        probe_tasks: list[asyncio.Task[None]] = []
        producer_task: asyncio.Task[None] | None = None

        try:
            producer_task = asyncio.create_task(self._history_event_producer(handle, queue, execution_id))

            with actor_context(
                execution_id=metadata.execution_id,
                workflow_id=metadata.workflow_id,
                request_id=metadata.request_id,
            ):
                while True:
                    item = await queue.get()

                    if item is None:
                        break

                    if not await self._dispatch_queue_item(item, metadata, handle, queue, probe_tasks, execution_id):
                        break

                if not self._shutdown:
                    await self._sync_activities_to_db(metadata, handle)

            logger.info("Activity monitoring completed for execution", execution_id=execution_id)
            return True

        except asyncio.CancelledError:
            raise
        except TemporalError:
            raise
        except (OperationalError, InterfaceError, SATimeoutError, OSError):
            logger.exception(
                "Transient error in monitor loop",
                execution_id=execution_id,
            )
            return False
        finally:
            await self._cancel_background_tasks(producer_task, probe_tasks)

    def _process_activity_scheduled(self, event: HistoryEvent, metadata: ExecutionMonitorMetadata) -> None:
        """Process ACTIVITY_TASK_SCHEDULED event."""
        attrs = event.activity_task_scheduled_event_attributes
        if attrs.activity_id.startswith("__internal__"):
            return
        match = _ITER_CAPTURE_RE.search(attrs.activity_id)
        if match:
            base_activity_id = attrs.activity_id[: match.start()]
            iteration_number: int | None = int(match.group(1))
            has_iter_suffix = True
        else:
            base_activity_id = attrs.activity_id
            iteration_number = None
            has_iter_suffix = False
        is_loop_iteration = has_iter_suffix or base_activity_id in metadata.terminal_activity_ids
        configured_timeout_seconds: float | None = None
        if attrs.start_to_close_timeout and attrs.start_to_close_timeout.seconds > 0:
            configured_timeout_seconds = attrs.start_to_close_timeout.seconds + (
                attrs.start_to_close_timeout.nanos / 1e9
            )

        metadata.pending_activity_updates[event.event_id] = {
            "activity_id": base_activity_id,
            "activity_name": base_activity_id,
            "_is_loop_iteration": is_loop_iteration,
            "_is_loop_control": has_iter_suffix,
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
                if defn.get("type") in ActivitySyncService._TRIGGER_ACTIVITY_TYPES
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

    def _extract_execution_status_from_event(self, event: HistoryEvent) -> tuple[ExecutionStatus, datetime, str | None]:  # noqa: C901
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
                        if inner_status == "failed":
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

                AuditEventDispatcher.dispatch(
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
                    AuditEventDispatcher.dispatch(
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
                # Don't raise - monitoring should continue

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

    def _process_activity_event(self, event: HistoryEvent, metadata: ExecutionMonitorMetadata) -> None:
        """Process a single activity event and update metadata's pending updates.

        Args:
            event: Temporal history event
            metadata: Monitoring metadata containing pending activity updates

        """
        event_type = event.event_type

        if event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            self._process_activity_scheduled(event, metadata)
        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED:
            self._process_activity_started(event, metadata)
        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED:
            self._process_activity_completed(event, metadata)
        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED:
            self._process_activity_failed(event, metadata)
        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT:
            self._process_activity_timed_out(event, metadata)
        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED:
            self._process_activity_canceled(event, metadata)

    async def _query_activity_io(
        self,
        handle: WorkflowHandle[Any, Any],
        activity_id: str,
        activity_data: dict[str, Any],
        initial_output_data: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Query workflow for activity input and output data.

        Queries ``get_activity_input`` and ``get_activity_output`` from the workflow.
        Handles the retry loop for the race condition where Temporal marks an
        activity as completed before the workflow loop stores the result.

        Args:
            handle: Temporal workflow handle for queries
            activity_id: Activity ID to query
            activity_data: Activity update data (used to check completion status)
            initial_output_data: Pre-existing output data (e.g. from heartbeat partial output)

        Returns:
            Tuple of (input_data, output_data)

        """
        input_data: dict[str, Any] = {}
        output_data = initial_output_data

        try:
            input_data = await handle.query("get_activity_input", activity_id) or {}
            queried_output = await handle.query("get_activity_output", activity_id)
            if queried_output is not None:
                output_data = queried_output

            # Race condition mitigation: If activity is completed but output is None,
            # retry the query. This handles the case where Temporal emits the
            # ACTIVITY_TASK_COMPLETED event before the workflow's async loop
            # stores the result in the resolver namespace.

            # (e.g., workflow signal after output is stored).
            if activity_data["status"] == ActivityStatus.COMPLETED and queried_output is None:
                max_retries = _OUTPUT_QUERY_MAX_RETRIES
                for retry in range(max_retries):
                    delay_ms = _OUTPUT_QUERY_BASE_DELAY_MS * (2**retry)
                    logger.debug(
                        "Activity completed but output is None, retrying query",
                        activity_id=activity_id,
                        retry=retry + 1,
                        max_retries=max_retries,
                        delay_ms=delay_ms,
                    )
                    await asyncio.sleep(delay_ms / 1000.0)
                    queried_output = await handle.query("get_activity_output", activity_id)
                    if queried_output is not None:
                        output_data = queried_output
                        logger.debug(
                            "Successfully retrieved output on retry",
                            activity_id=activity_id,
                            retry=retry + 1,
                        )
                        break
                else:
                    # All retries exhausted, log warning
                    logger.warning(
                        "Activity completed but output still None after retries",
                        activity_id=activity_id,
                        max_retries=max_retries,
                    )

        except (TemporalError, ValueError) as e:
            logger.debug("Could not query activity data", activity_id=activity_id, error=str(e))

        return input_data, output_data

    @staticmethod
    def _scrub_data(data: Any) -> dict[str, Any] | None:  # noqa: ANN401
        """Scrub credentials from data, wrapping non-dict values.

        Args:
            data: Raw data to scrub (dict, other non-None value, or None)

        Returns:
            Scrubbed dict, wrapped non-dict value, or None

        """
        if isinstance(data, dict):
            result: dict[str, Any] = scrub_credentials(data)
            return result
        if data is not None:
            return {"raw": data}
        return None

    @staticmethod
    def _update_activity_record(
        existing: ActivityExecution,
        activity_data: dict[str, Any],
        input_data: dict[str, Any] | None,
        output_data: dict[str, Any] | None,
        *,
        is_loop_control: bool = False,
    ) -> dict[str, Any]:
        """Update an ActivityExecution record with new data from Temporal events.

        Sets all fields on the activity and returns the old values for patch generation.

        Args:
            existing: Existing ActivityExecution record to update
            activity_data: Activity update data from Temporal events
            input_data: Scrubbed input data
            output_data: Scrubbed output data
            is_loop_control: Whether this is a loop control node

        Returns:
            Dictionary of old field values before the update

        """
        old_values = {
            "status": existing.status,
            "started_at": existing.started_at,
            "completed_at": existing.completed_at,
            "error_details": existing.error_details,
            "retry_count": existing.retry_count,
            "output_data": existing.output_data,
            "iteration": existing.iteration,
        }

        existing.status = activity_data["status"]
        existing.started_at = activity_data["started_at"] or (existing.started_at if is_loop_control else None)
        existing.completed_at = activity_data["completed_at"]
        existing.input_data = input_data or {}
        existing.output_data = output_data
        existing.error_details = activity_data["error_details"]
        existing.retry_count = activity_data["retry_count"]
        if activity_data.get("iteration") is not None and not is_loop_control:
            existing.iteration = activity_data["iteration"]
        existing.updated_at = datetime.now(UTC)

        return old_values

    @staticmethod
    def _collect_terminal_activities(
        metadata: ExecutionMonitorMetadata,
    ) -> tuple[list[int], list[tuple[str, dict[str, Any]]], dict[int, dict[str, Any]]]:
        """Collect terminal activity info and remove them from pending updates.

        Identifies activities that have reached a terminal status, collects
        timeout information for telemetry, and removes them from
        pending_activity_updates to avoid re-processing.

        Args:
            metadata: Monitoring metadata containing pending activity updates

        Returns:
            Tuple of (terminal_scheduled_ids, timed_out_activities, removed_entries)
            where timed_out_activities is a list of (activity_id, timeout_info) tuples
            and removed_entries maps event_id to the data dict for rollback restoration.

        """
        timed_out_activities: list[tuple[str, dict[str, Any]]] = []
        removed_entries: dict[int, dict[str, Any]] = {}
        terminal_scheduled_ids = [
            scheduled_id
            for scheduled_id, data in metadata.pending_activity_updates.items()
            if data.get("status") in TERMINAL_ACTIVITY_STATUSES
        ]
        for scheduled_id in terminal_scheduled_ids:
            data = metadata.pending_activity_updates[scheduled_id]
            metadata.terminal_activity_ids.add(data["activity_id"])
            timeout_info = data.get("_timeout_info")
            if timeout_info:
                timed_out_activities.append((data["activity_id"], timeout_info))
            removed_entries[scheduled_id] = data
            del metadata.pending_activity_updates[scheduled_id]

        # Clean up loop control entries whose status was overridden from terminal
        # to RUNNING by _process_single_activity_sync.  These intermediate
        # iterations have already been synced to the DB and would otherwise
        # accumulate for the lifetime of the execution monitor.
        # Only remove entries explicitly marked as overridden — naturally RUNNING
        # entries (started but not yet completed) must be kept so that subsequent
        # COMPLETED events are not silently dropped.
        stale_loop_ids = [
            sid
            for sid, data in metadata.pending_activity_updates.items()
            if data.get("_is_loop_control") and data.get("_status_overridden")
        ]
        for sid in stale_loop_ids:
            removed_entries[sid] = metadata.pending_activity_updates[sid]
            del metadata.pending_activity_updates[sid]

        return terminal_scheduled_ids, timed_out_activities, removed_entries

    def _emit_post_commit_telemetry(
        self,
        metadata: ExecutionMonitorMetadata,
        updated_activities: list[tuple[ActivityExecution, dict[str, Any]]],
        timed_out_activities: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """Emit all post-commit telemetry for activity updates.

        Emits telemetry for terminal activities, timeout events, and retry events.

        Args:
            metadata: Monitoring metadata
            updated_activities: List of (activity, old_values) tuples
            timed_out_activities: List of (activity_id, timeout_info) tuples

        """
        # Emit telemetry for activities that reached terminal states
        emit_activities(
            execution_id=metadata.execution_id,
            activity_definitions_map=metadata.activity_definitions_map,
            updated_activities=updated_activities,
            request_id=metadata.request_id,
        )

        # Emit workflow error telemetry for engine-level activity timeouts (post-commit)
        for activity_id, timeout_info in timed_out_activities:
            AuditEventDispatcher.dispatch(
                WorkflowExecutionErrorEvent(
                    execution_id=metadata.execution_id,
                    workflow_id=metadata.workflow_id,
                    timed_out_component=TimedOutComponent.ACTIVITY,
                    configured_timeout_seconds=timeout_info["configured_timeout_seconds"],
                    elapsed_time_ms=timeout_info["elapsed_time_ms"],
                    activity_id=activity_id,
                    retry_count=timeout_info["retry_count"],
                    error_type="ActivityTimedOut",
                    request_id=metadata.request_id,
                    workflow_name=metadata.workflow_name,
                )
            )

        # Emit workflow error telemetry for engine-level activity retries (post-commit)
        for data in metadata.pending_activity_updates.values():
            retry_info = data.pop("_retry_info", None)
            if retry_info:
                AuditEventDispatcher.dispatch(
                    WorkflowExecutionErrorEvent(
                        execution_id=metadata.execution_id,
                        workflow_id=metadata.workflow_id,
                        timed_out_component=TimedOutComponent.ACTIVITY,
                        configured_timeout_seconds=data.get("configured_timeout_seconds", 0.0) or 0.0,
                        elapsed_time_ms=0,
                        activity_id=data["activity_id"],
                        retry_count=retry_info["retry_count"],
                        error_type=retry_info["error_type"],
                        retry_reason=retry_info["retry_reason"],
                        request_id=metadata.request_id,
                        workflow_name=metadata.workflow_name,
                    )
                )

    async def _process_single_activity_sync(
        self,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
        activity_data: dict[str, Any],
        existing_activities: dict[str, ActivityExecution],
        session: AsyncSession,
    ) -> tuple[ActivityExecution, dict[str, Any], bool] | None:
        """Process a single activity update for database sync.

        Validates the activity, queries input/output data, and updates the record.
        For loop body children on subsequent iterations, creates a new per-iteration
        ActivityExecution record instead of overwriting the existing one.

        Args:
            metadata: Monitoring metadata
            handle: Temporal workflow handle for queries
            activity_data: Activity update data from Temporal events
            existing_activities: Map of activity_name to existing ActivityExecution records
            session: Database session for creating new records

        Returns:
            Tuple of (activity, old_values, is_new) if updated, None if skipped.
            is_new is True when a new per-iteration record was created.

        """
        activity_id = activity_data["activity_id"]

        # Skip internal activities (defense in depth)
        if activity_id.startswith("__internal__"):
            return None

        # Classify loop flags once — used by multiple guards below
        is_loop_control = bool(activity_data.get("_is_loop_control"))
        is_body_iteration = bool(activity_data.get("_is_loop_iteration")) and not is_loop_control
        is_new = False

        existing = existing_activities.get(activity_id)

        # For body children whose original record already reached terminal status,
        # create a separate per-iteration record instead of overwriting
        if is_body_iteration and existing and existing.status in TERMINAL_ACTIVITY_STATUSES:
            existing, is_new = self._get_or_create_iteration_record(activity_id, existing_activities, metadata, session)
            if existing is None:
                return None

        if not existing:
            logger.warning(
                "Activity not found in database for execution (should have been created upfront)",
                activity_id=activity_id,
                execution_id=metadata.execution_id,
            )
            return None

        # Don't regress terminal statuses — once skipped/completed/failed/cancelled,
        # later event processing (e.g. ACTIVITY_TASK_CANCELED after _sync_skipped_nodes)
        # must not overwrite. Check before querying to avoid wasted RPCs.
        # Exception: loop control nodes in COMPLETED status — the next iteration
        # re-schedules the same activity, so we must allow the update through.
        # Genuinely FAILED/CANCELLED loop control nodes must stay in that state.
        loop_control_iterating = is_loop_control and existing.status == ActivityStatus.COMPLETED
        if existing.status in TERMINAL_ACTIVITY_STATUSES and not loop_control_iterating and not is_new:
            return None

        # Query workflow for input/output data.
        # For running activities, partial output from heartbeat may
        # already be in the update dict — preserve it if the workflow
        # query returns None (output not stored until completion).
        input_data, output_data = await self._query_activity_io(
            handle, activity_id, activity_data, activity_data.get("output_data")
        )

        # Loop control nodes: keep the node "running" between iterations so the UI
        # doesn't flash completed→pending on every cycle.  The final iteration
        # populates iteration_results, so we only override intermediate ones.
        # Body nodes (is_loop_control=False) keep their real status per iteration.
        # Only override COMPLETED — real failures must propagate to the UI.
        if (
            is_loop_control
            and activity_data.get("status") == ActivityStatus.COMPLETED
            and isinstance(output_data, dict)
            and output_data.get("iteration_results") is None
        ):
            activity_data["status"] = ActivityStatus.RUNNING
            activity_data["completed_at"] = None
            activity_data["_status_overridden"] = True

        # For per-iteration records, set the iteration number in activity_data
        if is_new and existing.iteration is not None:
            activity_data["iteration"] = existing.iteration

        # Update existing activity and track old values for patch generation
        old_values = self._update_activity_record(
            existing,
            activity_data,
            self._scrub_data(input_data),
            self._scrub_data(output_data),
            is_loop_control=is_loop_control,
        )
        return existing, old_values, is_new

    @staticmethod
    def _get_or_create_iteration_record(
        activity_id: str,
        existing_activities: dict[str, ActivityExecution],
        metadata: ExecutionMonitorMetadata,
        session: AsyncSession,
    ) -> tuple[ActivityExecution | None, bool]:
        """Get or create a per-iteration ActivityExecution record for a loop body child.

        On subsequent loop iterations, body children are re-scheduled with the same
        activity_id. Instead of overwriting the previous iteration's record, this creates
        a new record with a composite key: ``{activity_id}#iter-{N}``.

        Args:
            activity_id: Base activity/node ID
            existing_activities: Map of activity_name to existing records (mutated on create)
            metadata: Monitoring metadata (activity_index_map is mutated on create)
            session: Database session for adding new records

        Returns:
            Tuple of (activity_record, is_new). is_new is True when a new record was created.

        """
        original = existing_activities.get(activity_id)
        if not original:
            logger.warning(
                "Original activity not found for loop body iteration",
                activity_id=activity_id,
                execution_id=metadata.execution_id,
            )
            return None, False

        # Use the per-base-id counter to find the latest iteration record.
        # Within a single iteration the activity transitions through multiple
        # states (PENDING → RUNNING → COMPLETED); only the first transition
        # should create a new record — subsequent transitions update it.
        latest_num = metadata.iteration_counters.get(activity_id, 0)
        if latest_num > 0:
            latest_key = f"{activity_id}{_COMPOSITE_ITER_SEP}{latest_num}"
            latest = existing_activities.get(latest_key)
            if latest is not None and latest.status not in TERMINAL_ACTIVITY_STATUSES:
                return latest, False

        iteration_num = latest_num + 1

        # Set iteration=0 on the original record if not already set
        if original.iteration is None:
            original.iteration = 0

        composite_key = f"{activity_id}{_COMPOSITE_ITER_SEP}{iteration_num}"

        new_activity = ActivityExecution(
            execution_id=metadata.execution_id,
            activity_name=composite_key,
            node_type=original.node_type,
            temporal_activity_id=composite_key,
            status=ActivityStatus.PENDING,
            started_at=None,
            completed_at=None,
            input_data={},
            output_data=None,
            error_details=None,
            retry_count=0,
            iteration=iteration_num,
        )
        session.add(new_activity)
        existing_activities[composite_key] = new_activity

        metadata.iteration_counters[activity_id] = iteration_num
        metadata.activity_index_map[composite_key] = metadata.next_activity_index
        metadata.next_activity_index += 1

        logger.debug(
            "Created per-iteration ActivityExecution record",
            activity_id=activity_id,
            composite_key=composite_key,
            iteration=iteration_num,
            execution_id=metadata.execution_id,
        )

        return new_activity, True

    async def _update_execution_flags(
        self,
        execution: Execution | None,
        updated_activities: list[tuple[ActivityExecution, dict[str, Any]]],
        existing_activities: list[ActivityExecution],
    ) -> tuple[ExecutionStatus | None, bool | None]:
        """Update execution status and approval_pending flag based on activity changes.

        Args:
            execution: Execution record to update
            updated_activities: List of updated activities with their old values
            existing_activities: All existing activities for the execution

        Returns:
            Tuple of (new_execution_status, approval_pending_changed)

        """
        if not updated_activities or not execution:
            return None, None

        new_status = await self._maybe_update_execution_paused_status(execution, existing_activities)
        approval_changed = self._update_approval_pending_flag(execution, existing_activities)
        return new_status, approval_changed

    async def _publish_patches_and_emit_telemetry(
        self,
        metadata: ExecutionMonitorMetadata,
        updated_activities: list[tuple[ActivityExecution, dict[str, Any]]],
        timed_out_activities: list[tuple[str, dict[str, Any]]],
        *,
        new_execution_status: ExecutionStatus | None,
        approval_pending_changed: bool | None,
        execution: Execution | None,
        new_iteration_activities: list[ActivityExecution] | None = None,
    ) -> None:
        """Publish activity and execution patches after DB commit and emit telemetry.

        Args:
            metadata: Execution monitoring metadata
            updated_activities: List of updated activities with their before/after diffs
            timed_out_activities: List of (activity_id, timeout_info) tuples for timed-out activities
            new_execution_status: New execution status if it changed
            approval_pending_changed: New approval_pending value if it changed
            execution: Execution record (for approval_pending patch)
            new_iteration_activities: Newly created per-iteration records needing "add" ops

        """
        # Publish activity patches after commit
        if updated_activities or new_iteration_activities:
            await self._publish_activity_patches(
                metadata, updated_activities, new_iteration_activities=new_iteration_activities or []
            )

        # Coalesce execution-level patches into a single message to avoid intermediate render states
        execution_patches: list[JsonPatchOperation] = []
        if new_execution_status is not None:
            execution_patches.append(JsonPatchOperation(op="replace", path="/status", value=new_execution_status.value))
        if approval_pending_changed is not None and execution:
            execution_patches.append(
                JsonPatchOperation(op="replace", path="/approval_pending", value=approval_pending_changed)
            )

        if execution_patches:
            await self._publish_execution_patch(metadata.execution_id, execution_patches)

        self._emit_post_commit_telemetry(metadata, updated_activities, timed_out_activities)

    async def _sync_activities_to_db(
        self,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
    ) -> None:
        """Sync activities from pending updates to database (UPDATE only).

        Since all activities are created upfront, this method only updates existing records
        with status changes and runtime data from Temporal events.

        Args:
            metadata: Monitoring metadata containing execution and pending updates
            handle: Temporal workflow handle for queries

        """
        if not metadata.pending_sync_event_ids:
            return

        async with self.session_factory() as session:
            try:
                # Load existing activities with proper ordering (matches relationship order_by)
                result = await session.exec(
                    select(ActivityExecution)
                    .where(ActivityExecution.execution_id == metadata.execution_id)
                    .order_by(ActivityExecution.created_at, ActivityExecution.activity_name)  # type: ignore[arg-type]
                )
                existing_activities_list = result.all()
                existing_activities = {activity.activity_name: activity for activity in existing_activities_list}

                # Track which activities were updated for patch generation
                updated_activities: list[tuple[ActivityExecution, dict[str, Any]]] = []
                new_iteration_activities: list[ActivityExecution] = []
                removed_entries: dict[int, dict[str, Any]] = {}

                # Snapshot mutable counters for rollback restoration
                saved_iteration_counters = dict(metadata.iteration_counters)
                saved_next_activity_index = metadata.next_activity_index
                saved_activity_index_map = dict(metadata.activity_index_map)
                saved_terminal_activity_ids = set(metadata.terminal_activity_ids)
                saved_last_processed_event_id = metadata.last_processed_event_id

                # Update activities from events (only those marked for sync)
                for scheduled_event_id in metadata.pending_sync_event_ids:
                    activity_data = metadata.pending_activity_updates.get(scheduled_event_id)
                    if not activity_data:
                        continue

                    update_result = await self._process_single_activity_sync(
                        metadata, handle, activity_data, existing_activities, session
                    )
                    if update_result is not None:
                        activity, old_values, is_new = update_result
                        updated_activities.append((activity, old_values))
                        if is_new:
                            new_iteration_activities.append(activity)

                # Clear terminal activities from pending to avoid re-processing.
                # Collect timeout info before clearing, for post-commit emission.
                _terminal_scheduled_ids, timed_out_activities, removed_entries = self._collect_terminal_activities(
                    metadata
                )

                # Update execution's last processed event ID
                exec_result = await session.exec(select(Execution).where(Execution.id == metadata.execution_id))
                execution = exec_result.one_or_none()
                if execution:
                    execution.last_processed_event_id = metadata.last_processed_event_id

                # Check if execution should transition between PAUSED and RUNNING
                # using already-loaded data from this session (no extra DB roundtrip).
                new_execution_status, approval_pending_changed = await self._update_execution_flags(
                    execution, updated_activities, list(existing_activities.values())
                )

                await session.commit()
                metadata.pending_sync_event_ids.clear()

                # Publish patches and emit telemetry after successful commit
                await self._publish_patches_and_emit_telemetry(
                    metadata,
                    updated_activities,
                    timed_out_activities,
                    new_execution_status=new_execution_status,
                    approval_pending_changed=approval_pending_changed,
                    execution=execution,
                    new_iteration_activities=new_iteration_activities,
                )

            except Exception:
                await session.rollback()
                metadata.pending_activity_updates.update(removed_entries)
                metadata.iteration_counters = saved_iteration_counters
                metadata.next_activity_index = saved_next_activity_index
                metadata.activity_index_map = saved_activity_index_map
                metadata.terminal_activity_ids = saved_terminal_activity_ids
                metadata.last_processed_event_id = saved_last_processed_event_id
                logger.exception(
                    "Error syncing activities to database for execution", execution_id=metadata.execution_id
                )
                raise

    async def _fetch_activity_definitions_map(self, workflow_version_id: UUID) -> dict[str, dict[str, Any]]:
        """Fetch activity definitions from V2 workflow version.

        Args:
            workflow_version_id: Workflow version ID

        Returns:
            Dictionary mapping activity/node ID to definition

        """
        async with self.session_factory() as session:
            result = await session.exec(select(WorkflowVersion).where(WorkflowVersion.id == workflow_version_id))
            workflow_version = result.one_or_none()

            activity_definitions_map: dict[str, dict[str, Any]] = {}

            if workflow_version and workflow_version.workflow_definition:
                workflow_def = workflow_version.workflow_definition

                # V2 structure: nodes array at top level
                nodes = workflow_def.get("nodes", [])
                triggers = workflow_def.get("triggers", [])

                # Include triggers as nodes (they create activity records in V2)
                all_nodes = triggers + nodes

                # Build map of all nodes by ID
                for node in all_nodes:
                    if "id" in node:
                        activity_definitions_map[node["id"]] = node

            return activity_definitions_map

    async def _sync_skipped_nodes(
        self,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
    ) -> None:
        """Query workflow for skipped and pre-resolved nodes and update them in database."""
        skipped_node_ids: list[str] = []
        pre_resolved_node_ids: list[str] = []

        try:
            skipped_node_ids = await handle.query("get_skipped_nodes")
        except Exception:
            logger.exception(
                "Error querying skipped nodes",
                execution_id=metadata.execution_id,
            )

        try:
            pre_resolved_node_ids = await handle.query("get_pre_resolved_nodes")
        except Exception:
            logger.exception(
                "Error querying pre-resolved nodes",
                execution_id=metadata.execution_id,
            )

        all_skipped = list(set(skipped_node_ids) | set(pre_resolved_node_ids))
        if not all_skipped:
            return

        try:
            # Pre-resolved nodes never get Temporal activities, so they may not have
            # ActivityExecution records. Create SKIPPED records for any that are missing.
            if pre_resolved_node_ids:
                await self._ensure_activity_records_exist(metadata, pre_resolved_node_ids, ActivityStatus.SKIPPED)

            await self._sync_nodes_to_terminal_status(
                metadata,
                node_ids=all_skipped,
                target_status=ActivityStatus.SKIPPED,
            )
        except Exception:
            logger.exception(
                "Error syncing skipped nodes to database",
                execution_id=metadata.execution_id,
            )

    async def _ensure_activity_records_exist(
        self,
        metadata: ExecutionMonitorMetadata,
        node_ids: list[str],
        status: ActivityStatus,
    ) -> None:
        """Create ActivityExecution records for nodes that don't have one yet."""
        async with self.session_factory() as session:
            result = await session.exec(
                select(ActivityExecution.activity_name).where(
                    ActivityExecution.execution_id == metadata.execution_id,
                    ActivityExecution.activity_name.in_(node_ids),  # type: ignore[attr-defined]
                )
            )
            existing = set(result.all())
            missing = [nid for nid in node_ids if nid not in existing]

            if not missing:
                return

            now = datetime.now(UTC)
            for node_id in missing:
                activity_def = metadata.activity_definitions_map.get(node_id, {})
                node_type_str = activity_def.get("type", "script")

                # Safely construct NodeType enum with fallback to INTERNAL_ACTIVITY
                try:
                    node_type = NodeType(node_type_str)
                except ValueError:
                    logger.warning(
                        "Invalid node type in workflow definition, defaulting to INTERNAL_ACTIVITY",
                        execution_id=metadata.execution_id,
                        node_id=node_id,
                        invalid_type=node_type_str,
                    )
                    node_type = NodeType.INTERNAL_ACTIVITY

                session.add(
                    ActivityExecution(
                        execution_id=metadata.execution_id,
                        activity_name=node_id,
                        node_type=node_type,
                        temporal_activity_id=f"{PRE_RESOLVED_ACTIVITY_ID_PREFIX}{node_id}"[
                            : FieldLimits.NAME_MAX_LENGTH
                        ],
                        status=status,
                        started_at=now,
                        completed_at=now,
                    )
                )
            await session.commit()
            logger.info(
                "Created activity records for pre-resolved nodes",
                execution_id=metadata.execution_id,
                node_count=len(missing),
            )

    async def _sync_failed_nodes(
        self,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
    ) -> dict[str, str] | None:
        """Query workflow for failed nodes and update them in database.

        Nodes that fail before a Temporal activity is scheduled (e.g., expression
        resolution errors) have no Temporal events, so their ActivityExecution
        records remain PENDING. Nodes that already have a non-PENDING status
        (synced via Temporal events) are left untouched.

        Returns:
            Map of node ID to error message for failed nodes, or ``None`` when
            the query fails (distinguishes "no failures" from "query error").

        """
        try:
            failed_node_map: dict[str, str] = await handle.query("get_failed_nodes")
            await self._sync_nodes_to_terminal_status(
                metadata,
                node_ids=list(failed_node_map.keys()),
                target_status=ActivityStatus.FAILED,
                error_map=failed_node_map,
            )
        except Exception:
            logger.exception(
                "Error syncing failed nodes (activities may remain PENDING)",
                execution_id=metadata.execution_id,
            )
            return None
        else:
            return failed_node_map

    async def _sync_nodes_to_terminal_status(
        self,
        metadata: ExecutionMonitorMetadata,
        node_ids: list[str],
        target_status: ActivityStatus,
        error_map: dict[str, str] | None = None,
    ) -> None:
        """Update ActivityExecution records to a terminal status and publish patches.

        Fetches all activities matching node_ids, then skips any that are already
        in a terminal status. This prevents overwriting one terminal state with
        another (e.g. a COMPLETED activity should not be changed to SKIPPED).

        Args:
            metadata: Monitoring metadata containing execution and activity index map
            node_ids: Node IDs to update
            target_status: Terminal status to set (SKIPPED, FAILED, etc.)
            error_map: Optional mapping of node ID to error message

        """
        if not node_ids:
            return

        execution_id = metadata.execution_id
        logger.debug(
            "Syncing nodes to terminal status",
            execution_id=execution_id,
            target_status=target_status.value,
            node_count=len(node_ids),
        )

        async with self.session_factory() as session:
            # Match base activity names and any per-iteration composite keys (#iter-N)
            name_conditions = [
                ActivityExecution.activity_name.in_(node_ids),  # type: ignore[attr-defined]
                *[ActivityExecution.activity_name.startswith(f"{nid}{_COMPOSITE_ITER_SEP}") for nid in node_ids],
            ]
            result = await session.exec(
                select(ActivityExecution).where(
                    ActivityExecution.execution_id == execution_id,
                    or_(*name_conditions),
                )
            )
            activities = result.all()

            if not activities:
                return

            updated_activities: list[tuple[ActivityExecution, dict[str, Any]]] = []
            now = datetime.now(UTC)
            for activity in activities:
                if activity.status in TERMINAL_ACTIVITY_STATUSES:
                    continue
                old_values = {
                    "status": activity.status,
                    "started_at": activity.started_at,
                    "completed_at": activity.completed_at,
                    "error_details": activity.error_details,
                    "output_data": activity.output_data,
                    "iteration": activity.iteration,
                }
                activity.status = target_status
                activity.completed_at = now
                if error_map is not None:
                    base_name = activity.activity_name.split(_COMPOSITE_ITER_SEP)[0]
                    activity.error_details = error_map.get(base_name)
                activity.updated_at = now
                updated_activities.append((activity, old_values))

            if not updated_activities:
                return

            await session.commit()

            logger.info(
                "Marked nodes in database",
                execution_id=execution_id,
                target_status=target_status.value,
                count=len(updated_activities),
            )

            await self._publish_activity_patches(metadata, updated_activities)

    async def _create_all_activities_upfront(
        self,
        execution_id: UUID,
        activity_definitions_map: dict[str, dict[str, Any]],
    ) -> None:
        """Create all ActivityExecution records upfront with status=PENDING.

        This method checks if activities already exist for this execution. If so, it returns
        immediately. Otherwise, it creates ActivityExecution records for all task activities
        in the workflow definition.

        Only task activities are tracked (condition/sequence/parallel/loop containers
        are not created as ActivityExecution records).

        Args:
            execution_id: Database execution ID
            activity_definitions_map: Map of activity definitions from workflow

        """
        async with self.session_factory() as session:
            try:
                # Check if any activities already exist for this execution
                result = await session.exec(
                    select(ActivityExecution).where(ActivityExecution.execution_id == execution_id).limit(1)
                )
                existing = result.one_or_none()

                if existing:
                    logger.debug(
                        "Activities already exist for execution, skipping upfront creation", execution_id=execution_id
                    )
                    return

                # Create ActivityExecution records for all trackable activities
                new_activities: list[ActivityExecution] = []

                for activity_id, activity_def in activity_definitions_map.items():
                    activity_type_str = activity_def.get("type")

                    # Safely construct NodeType enum with fallback to INTERNAL_ACTIVITY
                    try:
                        node_type = NodeType(activity_type_str)
                    except ValueError:
                        logger.warning(
                            "Invalid node type in workflow definition, defaulting to INTERNAL_ACTIVITY",
                            execution_id=execution_id,
                            activity_id=activity_id,
                            invalid_type=activity_type_str,
                        )
                        node_type = NodeType.INTERNAL_ACTIVITY

                    # V2 workflows: Create records for all node types (triggers, control, executors)
                    new_activity = ActivityExecution(
                        execution_id=execution_id,
                        activity_name=activity_id,
                        node_type=node_type,
                        temporal_activity_id=activity_id,  # Set to activity_name initially
                        status=ActivityStatus.PENDING,
                        started_at=None,
                        completed_at=None,
                        input_data={},
                        output_data=None,
                        error_details=None,
                        retry_count=0,
                        iteration=None,
                    )
                    new_activities.append(new_activity)

                # Bulk insert all activities
                if new_activities:
                    for activity in new_activities:
                        session.add(activity)

                    await session.commit()
                    logger.info(
                        "Created ActivityExecution records upfront for execution",
                        record_count=len(new_activities),
                        execution_id=execution_id,
                    )

                    # Publish initial snapshot after activities are created
                    await self._publish_snapshot(execution_id, "initial_snapshot")

            except Exception:
                await session.rollback()
                logger.exception("Error creating activities upfront for execution", execution_id=execution_id)
                raise

    @staticmethod
    def _build_field_patch_ops(
        activity: ActivityExecution,
        old_values: dict[str, Any],
        activity_idx: int,
    ) -> list[dict[str, Any]]:
        """Build JSON Patch "replace" ops for changed fields on a single activity."""
        ops: list[dict[str, Any]] = []
        fields_to_check = [
            ("status", activity.status.value if activity.status else None),
            ("started_at", activity.started_at.isoformat() if activity.started_at else None),
            ("completed_at", activity.completed_at.isoformat() if activity.completed_at else None),
            ("error_details", activity.error_details),
            ("output_data", activity.output_data),
            ("iteration", activity.iteration),
        ]

        for field_name, new_value in fields_to_check:
            old_value = old_values.get(field_name)
            if field_name == "status" and old_value is not None:
                old_value = old_value.value
            elif field_name in ("started_at", "completed_at") and old_value is not None:
                old_value = old_value.isoformat()
            if old_value != new_value:
                ops.append({"op": "replace", "path": f"/activities/{activity_idx}/{field_name}", "value": new_value})

        return ops

    @staticmethod
    def _build_iteration_patch_ops(
        new_iteration_activities: list[ActivityExecution],
        activity_index_map: dict[str, int],
    ) -> list[dict[str, Any]]:
        """Build JSON Patch ops for newly created per-iteration activity records.

        Generates "add" ops to append new records to the activities array, plus
        "replace" ops to set ``iteration=0`` on original records.

        """
        ops: list[dict[str, Any]] = []
        patched_originals: set[str] = set()

        for activity in new_iteration_activities:
            data = ActivityData(
                activity_id=activity.activity_name,
                status=activity.status.value if activity.status else "pending",
                started_at=activity.started_at,
                completed_at=activity.completed_at,
                error_details=activity.error_details,
                output_data=activity.output_data,
                iteration=activity.iteration,
            )
            ops.append({"op": "add", "path": "/activities/-", "value": data.model_dump(mode="json")})

            base_id = activity.activity_name.split(_COMPOSITE_ITER_SEP)[0]
            if base_id not in patched_originals:
                original_idx = activity_index_map.get(base_id)
                if original_idx is not None:
                    ops.append({"op": "replace", "path": f"/activities/{original_idx}/iteration", "value": 0})
                    patched_originals.add(base_id)

        return ops

    async def _publish_activity_patches(
        self,
        metadata: ExecutionMonitorMetadata,
        updated_activities: list[tuple[ActivityExecution, dict[str, Any]]],
        *,
        new_iteration_activities: list[ActivityExecution] | None = None,
    ) -> None:
        """Publish activity patches for incremental updates.

        Creates JSON Patch operations manually without costly DB reads by directly
        constructing patch operations for each changed field. For newly created
        per-iteration records, publishes "add" ops to append to the activities array.

        Args:
            metadata: Monitoring metadata containing execution and activity index map
            updated_activities: List of (activity, old_values) tuples for activities that were updated
            new_iteration_activities: Newly created per-iteration records needing "add" ops

        """
        execution_id = metadata.execution_id
        new_activity_names = {a.activity_name for a in (new_iteration_activities or [])}
        try:
            # Create patch operations for each updated activity
            patch_ops: list[dict[str, Any]] = []

            for activity, old_values in updated_activities:
                # New per-iteration records get "add" ops (appended below), not "replace"
                if activity.activity_name in new_activity_names:
                    continue

                activity_idx = metadata.activity_index_map.get(activity.activity_name)
                if activity_idx is None:
                    logger.warning(
                        "Activity not found in activities list for execution",
                        activity_name=activity.activity_name,
                        execution_id=execution_id,
                    )
                    continue

                patch_ops.extend(self._build_field_patch_ops(activity, old_values, activity_idx))

            # Append "add" ops for new per-iteration records and iteration=0 patches for originals
            if new_iteration_activities:
                patch_ops.extend(self._build_iteration_patch_ops(new_iteration_activities, metadata.activity_index_map))

            # Publish patches if there are any operations
            if patch_ops:
                # Wrap operations in a JsonPatch object
                json_patch = JsonPatch(patch_ops)
                await self.activity_publisher.publish_activity_patch(execution_id, [json_patch])

                logger.debug(
                    "Published patch operations for execution (activities updated)",
                    operation_count=len(patch_ops),
                    execution_id=execution_id,
                    updated_activity_count=len(updated_activities),
                    new_iteration_count=len(new_iteration_activities or []),
                )

        except Exception:
            # Log error but don't fail database sync (publishing is best-effort)
            logger.exception("Failed to publish activity patches for execution (non-fatal)", execution_id=execution_id)
