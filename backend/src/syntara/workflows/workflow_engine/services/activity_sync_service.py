"""Background service for syncing activity executions from Temporal to database.

This service monitors running workflow executions and syncs activity data
to the database in real-time by streaming Temporal history events.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.api.enums.v1 import PendingActivityState
from temporalio.api.history.v1 import HistoryEvent
from temporalio.client import Client, WorkflowHandle, WorkflowHistoryEventFilterType
from temporalio.exceptions import TemporalError

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.workflows.audit.execution_started import WorkflowStartEvent
from syntara.workflows.models.activity_execution import TERMINAL_ACTIVITY_STATUSES, ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.visualization import JsonPatchOperation
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.services.activity_update_publisher import ActivityUpdatePublisher
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.activity_execution_state import ActivityExecutionStateMixin
from syntara.workflows.workflow_engine.services.activity_execution_sync import ActivityExecutionSyncMixin
from syntara.workflows.workflow_engine.services.activity_execution_synchronizer import ActivityExecutionSynchronizer
from syntara.workflows.workflow_engine.services.activity_node_sync import ActivityNodeSyncMixin
from syntara.workflows.workflow_engine.services.activity_sync_event_processor import ActivitySyncEventProcessorMixin
from syntara.workflows.workflow_engine.services.activity_sync_lifecycle import ActivitySyncLifecycle
from syntara.workflows.workflow_engine.services.activity_sync_monitor import ActivitySyncMonitorMixin
from syntara.workflows.workflow_engine.services.activity_sync_probe import ActivitySyncProbeMixin
from syntara.workflows.workflow_engine.services.activity_sync_publisher import ActivitySyncPublisherMixin
from syntara.workflows.workflow_engine.services.activity_sync_types import (
    ExecutionMonitorMetadata,
    QueueItem,
    SyntheticActivityStarted,
    SyntheticPartialOutput,
)

PRE_RESOLVED_ACTIVITY_ID_PREFIX = "pre-resolved-"


logger = structlog.stdlib.get_logger(__name__)

# Temporal defers ACTIVITY_TASK_STARTED events until the activity completes,
# so the sync service never sees RUNNING status for in-flight activities.
# After SCHEDULED, we probe describe() to detect the real state, retrying
# with exponential backoff if the activity hasn't been picked up yet.
_DESCRIBE_PROBE_INITIAL_DELAY_S = 1.0
_DESCRIBE_PROBE_MAX_DELAY_S = 30.0
_DESCRIBE_PROBE_BACKOFF_FACTOR = 2.0
_DESCRIBE_PROBE_MAX_TOTAL_S = 600.0  # 10 minutes
_DESCRIBE_PROBE_MAX_TASKS = 25

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


_QueueItem = QueueItem

__all__ = [
    "ActivitySyncService",
    "ExecutionMonitorMetadata",
    "SyntheticActivityStarted",
    "SyntheticPartialOutput",
]


class ActivitySyncService(
    ActivityNodeSyncMixin,
    ActivityExecutionSyncMixin,
    ActivityExecutionStateMixin,
    ActivitySyncEventProcessorMixin,
    ActivitySyncProbeMixin,
    ActivitySyncPublisherMixin,
    ActivitySyncMonitorMixin,
):
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
        self._lifecycle = ActivitySyncLifecycle(self)
        self._execution_synchronizer = ActivityExecutionSynchronizer(self)

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
        self._lifecycle.start(execution_id, temporal_workflow_id, request_id=request_id)

    def _cleanup_task(self, execution_id: UUID, task: asyncio.Task[None]) -> None:
        """Clean up completed monitoring task.

        Args:
            execution_id: Database execution ID
            task: Completed task

        """
        self._lifecycle.cleanup(execution_id, task)

    @staticmethod
    def _dispatch_audit_event(event: object) -> None:
        """Dispatch an audit event through the façade-owned integration seam."""
        AuditEventDispatcher.dispatch(event)

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
        await self._lifecycle.shutdown()

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

    def _update_execution_flags(
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

        new_status = self._maybe_update_execution_paused_status(execution, existing_activities)
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
        await self._execution_synchronizer.sync(metadata, handle)

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
