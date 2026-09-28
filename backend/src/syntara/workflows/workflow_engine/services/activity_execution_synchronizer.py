"""Database transaction coordinator for activity synchronization."""

# The host is deliberately the existing service façade; these calls preserve
# its established helper seams while the transaction boundary lives here.
# ruff: noqa: SLF001

from typing import Any

import structlog
from sqlmodel import select
from temporalio.client import WorkflowHandle

from syntara.workflows.models.activity_execution import ActivityExecution
from syntara.workflows.models.execution import Execution
from syntara.workflows.workflow_engine.services.activity_sync_types import ExecutionMonitorMetadata

logger = structlog.stdlib.get_logger(__name__)


class ActivityExecutionSynchronizer:
    """Coordinate one atomic activity sync and its post-commit side effects.

    The service remains the owner of the domain helpers. Keeping this object
    focused on transaction boundaries makes rollback behavior explicit without
    creating another mixin with implicit ``self`` dependencies.
    """

    def __init__(self, host: Any) -> None:  # noqa: ANN401
        """Create a synchronizer attached to the activity-sync façade."""
        self.host = host

    async def sync(
        self,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
    ) -> None:
        """Apply pending activity updates in one transaction."""
        if not metadata.pending_sync_event_ids:
            return

        async with self.host.session_factory() as session:
            removed_entries: dict[int, dict[str, Any]] = {}
            saved_iteration_counters = dict(metadata.iteration_counters)
            saved_next_activity_index = metadata.next_activity_index
            saved_activity_index_map = dict(metadata.activity_index_map)
            saved_terminal_activity_ids = set(metadata.terminal_activity_ids)
            saved_last_processed_event_id = metadata.last_processed_event_id

            try:
                result = await session.exec(
                    select(ActivityExecution)
                    .where(ActivityExecution.execution_id == metadata.execution_id)
                    .order_by(ActivityExecution.created_at, ActivityExecution.activity_name)  # type: ignore[arg-type]
                )
                existing_activities = {activity.activity_name: activity for activity in result.all()}

                updated_activities: list[tuple[ActivityExecution, dict[str, Any]]] = []
                new_iteration_activities: list[ActivityExecution] = []

                for scheduled_event_id in metadata.pending_sync_event_ids:
                    activity_data = metadata.pending_activity_updates.get(scheduled_event_id)
                    if not activity_data:
                        continue

                    update_result = await self.host._process_single_activity_sync(
                        metadata, handle, activity_data, existing_activities, session
                    )
                    if update_result is not None:
                        activity, old_values, is_new = update_result
                        updated_activities.append((activity, old_values))
                        if is_new:
                            new_iteration_activities.append(activity)

                _, timed_out_activities, removed_entries = self.host._collect_terminal_activities(metadata)

                exec_result = await session.exec(select(Execution).where(Execution.id == metadata.execution_id))
                execution = exec_result.one_or_none()
                if execution:
                    execution.last_processed_event_id = metadata.last_processed_event_id

                new_execution_status, approval_pending_changed = await self.host._update_execution_flags(
                    execution, updated_activities, list(existing_activities.values())
                )

                await session.commit()
                metadata.pending_sync_event_ids.clear()

                await self.host._publish_patches_and_emit_telemetry(
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
