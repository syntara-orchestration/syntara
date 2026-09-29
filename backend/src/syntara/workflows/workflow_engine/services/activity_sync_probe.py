"""Temporal describe() probing for activity state and heartbeat output."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import structlog
from temporalio.api.enums.v1 import PendingActivityState
from temporalio.client import WorkflowHandle

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.workflow_engine.activities.common import (
    HEARTBEAT_PARTIAL_OUTPUT_KEY,
    HEARTBEAT_STOP_MONITOR,
)
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.activity_sync_types import (
    ExecutionMonitorMetadata,
    QueueItem,
    SyntheticActivityStarted,
    SyntheticPartialOutput,
)
from syntara.workflows.workflow_engine.utils.loop_iteration_ids import strip_loop_iteration_suffixes

logger = structlog.stdlib.get_logger(__name__)

_DESCRIBE_PROBE_INITIAL_DELAY_S = 1.0
_DESCRIBE_PROBE_MAX_DELAY_S = 30.0
_DESCRIBE_PROBE_BACKOFF_FACTOR = 2.0
_DESCRIBE_PROBE_MAX_TOTAL_S = 600.0
_PENDING_ACTIVITY_STATE_STARTED = PendingActivityState.PENDING_ACTIVITY_STATE_STARTED


class ActivitySyncProbeMixin:
    """Describe-based activity state probing used by the monitor."""

    _shutdown: bool
    _scrub_data: Any
    _sync_activities_to_db: Any

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
        queue: asyncio.Queue[QueueItem],
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
        queue: asyncio.Queue[QueueItem],
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
                        partial_output=self._scrub_data(partial_output) or {},
                    )
                )
            return True
        return False

    async def _schedule_describe_probe(
        self,
        handle: WorkflowHandle[Any, Any],
        queue: asyncio.Queue[QueueItem],
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

        # Temporal history does not expose pending-activity STARTED state or
        # heartbeat details, so describe() must be polled until the activity changes.
        while elapsed < _DESCRIBE_PROBE_MAX_TOTAL_S and not self._shutdown:  # NOSONAR
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

        canvas_id = strip_loop_iteration_suffixes(event.activity_id)
        activity_def = metadata.activity_definitions_map.get(canvas_id, {})
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
