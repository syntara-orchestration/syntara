"""Temporal history queue and retrying execution monitor."""

import asyncio
import secrets
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError
from temporalio.api.enums.v1 import EventType
from temporalio.api.history.v1 import HistoryEvent
from temporalio.client import WorkflowHandle
from temporalio.exceptions import TemporalError

from syntara.audit.context_managers import actor_context
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.activity_sync_types import (
    ExecutionMonitorMetadata,
    QueueItem,
    SyntheticActivityStarted,
    SyntheticPartialOutput,
)

logger = structlog.stdlib.get_logger(__name__)

_DESCRIBE_PROBE_MAX_TASKS = 25
_MONITOR_RETRY_BASE_DELAY_S = 1.0
_MONITOR_RETRY_MAX_DELAY_S = 30.0
_MONITOR_RETRY_BACKOFF_FACTOR = 2.0
_MONITOR_RETRY_JITTER_FACTOR = 0.5


class ActivitySyncMonitorMixin:
    """Consume Temporal history and coordinate activity synchronization."""

    _shutdown: bool
    _sync_activities_to_db: Any
    _update_execution_to_running: Any
    _sync_failed_nodes: Any
    _sync_restored_retry_nodes: Any
    _sync_skipped_nodes: Any
    _sync_detached_nodes: Any
    _update_execution_status_from_event: Any
    _schedule_describe_probe: Any
    _process_synthetic_activity_started: Any
    _process_synthetic_partial_output: Any
    _TRIGGER_ACTIVITY_TYPES: Any
    _extract_failed_activities_from_event: Any
    temporal_client: Any
    _initialize_monitoring: Any
    _process_activity_scheduled: Any
    _process_activity_started: Any
    _process_activity_completed: Any
    _process_activity_failed: Any
    _process_activity_timed_out: Any
    _process_activity_canceled: Any

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
        queue: asyncio.Queue[QueueItem],
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

    async def _process_history_event(
        self,
        event: HistoryEvent,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
        queue: asyncio.Queue[QueueItem],
        probe_tasks: list[asyncio.Task[None]],
    ) -> bool:
        """Process a single Temporal history event.

        Returns False if the monitor loop should stop (shutdown requested).
        """
        if event.event_id <= metadata.last_processed_event_id:
            return not self._shutdown

        # Handle workflow execution started event
        if event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED:
            await self._update_execution_to_running(metadata, event)
            metadata.last_processed_event_id = event.event_id
            return not self._shutdown

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
            await self._sync_detached_nodes(metadata, handle)
            await self._update_execution_status_from_event(metadata, event, failed_node_map)
            metadata.last_processed_event_id = event.event_id
            return not self._shutdown

        # Restore retained iterations before assigning IDs to new loop activity events.
        if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            await self._sync_restored_retry_nodes(metadata, handle)

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
                    # Temporal pending_activities is keyed by the real activity_id
                    # (e.g. approval_iter_0). Strip only when looking up canvas
                    # definitions after STARTED is observed.
                    probe_tasks.append(
                        asyncio.create_task(
                            self._schedule_describe_probe(
                                handle,
                                queue,
                                attrs.activity_id,
                                event.event_id,
                            )
                        )
                    )

        return not self._shutdown

    async def _dispatch_queue_item(
        self,
        item: QueueItem,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
        queue: asyncio.Queue[QueueItem],
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
                # Retry jitter only affects scheduling; it is not used for secrets or authorization.
                jitter = (1 - _MONITOR_RETRY_JITTER_FACTOR) + (
                    secrets.SystemRandom().random() * _MONITOR_RETRY_JITTER_FACTOR  # NOSONAR
                )
                jittered_delay = delay * jitter
                await asyncio.sleep(jittered_delay)
                delay = min(delay * _MONITOR_RETRY_BACKOFF_FACTOR, _MONITOR_RETRY_MAX_DELAY_S)

        except asyncio.CancelledError:
            logger.info("Activity monitoring cancelled for execution", execution_id=execution_id)
            raise
        except TemporalError:
            logger.warning(
                "Temporal error while monitoring execution, will not retry",
                execution_id=execution_id,
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
        queue: asyncio.Queue[QueueItem] = asyncio.Queue()
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
