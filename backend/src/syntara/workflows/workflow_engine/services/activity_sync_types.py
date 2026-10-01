"""State and queue item types used by activity synchronization."""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from temporalio.api.history.v1 import HistoryEvent

from syntara.workflows.models.execution import ExecutionMode


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
        mode: Execution mode of the run (standard, test, debug)
        workflow_version: Version number of the workflow definition used by this run
        used_published: Whether the run used the workflow's published version

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
    mode: ExecutionMode | None = None
    workflow_version: int | None = None
    used_published: bool | None = None
    is_retry: bool = False


type QueueItem = HistoryEvent | SyntheticActivityStarted | SyntheticPartialOutput | None
