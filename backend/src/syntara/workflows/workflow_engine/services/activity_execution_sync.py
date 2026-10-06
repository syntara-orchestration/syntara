"""Activity execution record synchronization and Temporal I/O resolution."""

from datetime import UTC, datetime
from typing import Any, cast

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.client import WorkflowHandle
from temporalio.exceptions import ApplicationError, TemporalError
from temporalio.service import RPCError, RPCStatusCode

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.telemetry.events.workflow_emitters import emit_activities
from syntara.telemetry.events.workflow_error import TimedOutComponent
from syntara.workflows.audit.execution_error import WorkflowExecutionErrorEvent
from syntara.workflows.models.activity_execution import TERMINAL_ACTIVITY_STATUSES, ActivityExecution, ActivityStatus
from syntara.workflows.utils.datetime import ensure_timezone_aware
from syntara.workflows.workflow_engine.services.activity_sync_types import ExecutionMonitorMetadata
from syntara.workflows.workflow_engine.utils.credential_scrubber import scrub_credentials

logger = structlog.stdlib.get_logger(__name__)

_COMPOSITE_ITER_SEP = "#iter-"


class ActivityExecutionSyncMixin:
    """Activity record updates, I/O queries, and loop iteration handling."""

    @staticmethod
    def _merge_output(initial: dict[str, Any] | None, queried: dict[str, Any]) -> dict[str, Any]:
        """Merge heartbeat partial output with workflow-queried output."""
        return {**initial, **queried} if initial else queried

    async def _fetch_completed_activity_output(
        self,
        handle: WorkflowHandle[Any, Any],
        activity_id: str,
    ) -> dict[str, Any] | None:
        """Resolve output for a completed activity when the initial query returned None."""
        try:
            return cast(
                "dict[str, Any] | None",
                await handle.execute_update("get_activity_output_when_ready", activity_id),
            )
        except RPCError as e:
            if e.status == RPCStatusCode.NOT_FOUND:
                # Workflow already completed — the update was rejected because
                # the server has already recorded the final state.  This means
                # set_namespace() has run (completion requires it), so a query
                # against the completed workflow's final state is guaranteed to
                # return the output.
                try:
                    return cast(
                        "dict[str, Any] | None",
                        await handle.query("get_activity_output", activity_id),
                    )
                except (TemporalError, ValueError):
                    logger.warning(
                        "Could not query activity data",
                        activity_id=activity_id,
                    )
                    raise
            logger.warning(
                "Workflow update for activity output failed",
                activity_id=activity_id,
            )
            return None
        except ApplicationError:
            logger.warning(
                "Workflow update for activity output timed out",
                activity_id=activity_id,
            )
            return None

    async def _query_activity_io(
        self,
        handle: WorkflowHandle[Any, Any],
        activity_id: str,
        activity_data: dict[str, Any],
        initial_output_data: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Query workflow for activity input and output data.

        Queries ``get_activity_input`` and ``get_activity_output`` from the
        workflow.  For completed activities whose output is not yet available
        (race where Temporal emits ACTIVITY_TASK_COMPLETED before the workflow
        stores the result), falls back to the ``get_activity_output_when_ready``
        workflow update which blocks until the resolver namespace is populated.
        The query-first approach ensures this works even after the workflow has
        completed (updates cannot target completed workflows).

        Args:
            handle: Temporal workflow handle for queries
            activity_id: Activity ID to query
            activity_data: Activity update data (used to check completion status)
            initial_output_data: Pre-existing output data (e.g. from heartbeat partial output)

        Returns:
            Tuple of (input_data, output_data).

        Raises:
            TemporalError: When the workflow query fails (worker unreachable, rejected, etc.).
            ValueError: When query arguments are invalid.

        """
        input_data: dict[str, Any] = {}
        output_data = initial_output_data

        try:
            input_data = await handle.query("get_activity_input", activity_id) or {}
            queried_output = await handle.query("get_activity_output", activity_id)
        except (TemporalError, ValueError):
            logger.warning("Could not query activity data", activity_id=activity_id)
            raise

        if queried_output is None and activity_data["status"] == ActivityStatus.COMPLETED:
            queried_output = await self._fetch_completed_activity_output(handle, activity_id)

        if queried_output is not None:
            output_data = self._merge_output(initial_output_data, queried_output)

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

    async def _resolve_replayed_timestamps(
        self,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
    ) -> dict[str, dict[str, datetime | None]]:
        """Collect source timestamps for the replayed nodes finishing in this batch.

        One workflow update per replayed node, asked before the sync transaction
        opens because the update blocks until the workflow can answer and a
        database transaction must not be held across that wait.

        Only terminal events are asked about. A node that has merely been
        scheduled has not replayed yet, so asking would wait for a timestamp that
        is minutes away, and its source times would be applied to a node that has
        not run. Non-retry runs ask nothing at all.
        """
        if not metadata.is_retry:
            return {}

        resolved: dict[str, dict[str, datetime | None]] = {}
        for event_id in metadata.pending_sync_event_ids:
            activity_data = metadata.pending_activity_updates.get(event_id)
            if not activity_data or activity_data.get("status") not in TERMINAL_ACTIVITY_STATUSES:
                continue
            activity_id = activity_data["activity_id"]
            if activity_id in resolved:
                continue
            restored_ts = await self._replayed_node_timestamps(metadata, handle, activity_id)
            if restored_ts is not None:
                resolved[activity_id] = restored_ts
        return resolved

    async def _replayed_node_timestamps(
        self,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
        activity_id: str,
    ) -> dict[str, datetime | None] | None:
        """Ask the workflow for one replayed node's source-run times, or None.

        Called when the node completes, which is the moment its row is written.
        The workflow update blocks until it can say whether this activity is a
        replay and, if so, has the source times ready — a plain query would race
        the event and lose them, since the event is only processed once.

        Returns None when the activity was an ordinary execution, or when the
        workflow cannot answer in time. Either way the caller keeps Temporal's
        timestamps, so a failure here degrades to a restored node reporting the
        replay time rather than losing the node's record.
        """
        try:
            raw = cast(
                "dict[str, str | None] | None",
                await handle.execute_update("get_replayed_node_timestamps_when_ready", activity_id),
            )
        except RPCError as e:
            if e.status == RPCStatusCode.NOT_FOUND:
                # The workflow already closed, so the update was rejected and
                # there is no handler left to ask. Source times were written
                # before the node's result was published, so they do exist — but
                # nothing reads them back now. Keeping Temporal's times still
                # yields a correct row, only stamped with the replay time.
                logger.info(
                    "Workflow closed before replayed node timestamps could be read",
                    activity_id=activity_id,
                    execution_id=metadata.execution_id,
                )
                return None
            logger.warning(
                "Workflow update for replayed node timestamps failed",
                activity_id=activity_id,
            )
            return None
        except (ApplicationError, TemporalError, ValueError):
            logger.warning(
                "Workflow update for replayed node timestamps did not return",
                activity_id=activity_id,
            )
            return None

        if not raw:
            return None
        return {
            "started_at": self._parse_source_timestamp(raw.get("started_at")),
            "completed_at": self._parse_source_timestamp(raw.get("completed_at")),
        }

    @staticmethod
    def _parse_source_timestamp(value: str | None) -> datetime | None:
        """Parse an ISO timestamp from the replay activity, or None."""
        if not value:
            return None
        try:
            return ensure_timezone_aware(datetime.fromisoformat(value))
        except ValueError:
            return None

    @staticmethod
    def _apply_replayed_timestamps(
        restored_ts: dict[str, datetime | None] | None,
        activity_data: dict[str, Any],
    ) -> None:
        """Swap a replayed node's event times for its source-run timestamps.

        A replayed node is recorded through the normal event path with this run's
        event times. These source timestamps are applied over them so the node
        reports when the work actually ran rather than when it was replayed.
        No-op for a node this retry did not replay.
        """
        if restored_ts is None:
            return
        if restored_ts.get("started_at") is not None:
            activity_data["started_at"] = restored_ts["started_at"]
        if restored_ts.get("completed_at") is not None and activity_data.get("status") == ActivityStatus.COMPLETED:
            activity_data["completed_at"] = restored_ts["completed_at"]

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
            workflow_id=metadata.workflow_id,
            mode=metadata.mode,
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
        replayed_timestamps: dict[str, dict[str, datetime | None]] | None = None,
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
            replayed_timestamps: Source timestamps resolved before this call, keyed
                by activity id. Empty for an ordinary execution.

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

        input_data, output_data = await self._resolve_activity_io(handle, activity_id, activity_data, existing)

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

        # A retry-replayed node is recorded through this normal path with this
        # run's event times; its source times were resolved before the
        # transaction opened and are swapped in here.
        self._apply_replayed_timestamps((replayed_timestamps or {}).get(activity_id), activity_data)

        # Update existing activity and track old values for patch generation
        old_values = self._update_activity_record(
            existing,
            activity_data,
            input_data,
            output_data,
            is_loop_control=is_loop_control,
        )
        return existing, old_values, is_new

    @staticmethod
    def _io_after_query_failure(
        existing: ActivityExecution,
        activity_data: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Return input/output safe to persist when a Temporal query failed."""
        input_data = existing.input_data or {}
        event_output = activity_data.get("output_data")
        if event_output is not None:
            output_data: dict[str, Any] | None = event_output | (existing.output_data or {})
        else:
            output_data = existing.output_data
        return input_data, output_data

    async def _resolve_activity_io(
        self,
        handle: WorkflowHandle[Any, Any],
        activity_id: str,
        activity_data: dict[str, Any],
        existing: ActivityExecution,
    ) -> tuple[dict[str, Any], Any]:
        """Resolve input/output data for an activity, avoiding a per-event query storm.

        Querying Temporal on every event of a loop workflow (~600 events) replays
        history each time and exhausts the DB pool. To avoid that while keeping the
        UI's input panel populated mid-run:
        - Terminal statuses: full query (input + final output, with the retry loop).
        - First non-terminal event (input not yet stored): query once for input only;
          output stays whatever the event carried (e.g. heartbeat partial output).
        - Subsequent non-terminal events: no query — reuse the stored input.
        """
        if activity_data.get("status") in TERMINAL_ACTIVITY_STATUSES:
            try:
                return await self._query_activity_io(
                    handle, activity_id, activity_data, activity_data.get("output_data")
                )
            except (TemporalError, ValueError):
                return self._io_after_query_failure(existing, activity_data)
        if not existing.input_data:
            try:
                input_data, _ = await self._query_activity_io(handle, activity_id, activity_data, None)
                return input_data, activity_data.get("output_data")
            except (TemporalError, ValueError):
                return self._io_after_query_failure(existing, activity_data)
        return existing.input_data, activity_data.get("output_data")

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
