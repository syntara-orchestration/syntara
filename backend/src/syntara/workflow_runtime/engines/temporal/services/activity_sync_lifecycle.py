"""Lifecycle management for activity-sync monitoring tasks."""

# This collaborator intentionally drives the façade's private task state.
# ruff: noqa: SLF001

import asyncio
from typing import Any
from uuid import UUID

import structlog

logger = structlog.stdlib.get_logger(__name__)


class ActivitySyncLifecycle:
    """Own monitoring task registration, cleanup, and shutdown."""

    def __init__(self, host: Any) -> None:  # noqa: ANN401
        """Create a lifecycle manager attached to the activity-sync façade."""
        self.host = host

    def start(
        self,
        execution_id: UUID,
        temporal_workflow_id: str,
        *,
        request_id: UUID | None = None,
    ) -> None:
        """Start monitoring an execution unless it is already registered."""
        task_key = str(execution_id)
        if task_key in self.host._sync_tasks:
            logger.warning("Already monitoring execution", execution_id=execution_id)
            return

        logger.info("Starting activity sync monitoring for execution", execution_id=execution_id)
        task = asyncio.create_task(
            self.host._monitor_execution(execution_id, temporal_workflow_id, request_id=request_id),
            name=f"activity_sync_{execution_id}",
        )
        self.host._sync_tasks[task_key] = task
        task.add_done_callback(lambda completed: self.cleanup(execution_id, completed))

    def cleanup(self, execution_id: UUID, task: asyncio.Task[None]) -> None:
        """Remove a completed task and log its terminal outcome."""
        task_key = str(execution_id)
        self.host._sync_tasks.pop(task_key, None)

        if task.cancelled():
            logger.debug("Monitoring task for execution was cancelled", execution_id=execution_id)
        elif task.exception():
            logger.error("Monitoring task for execution failed", execution_id=execution_id)
        else:
            logger.info("Monitoring task for execution completed successfully", execution_id=execution_id)

    async def shutdown(self) -> None:
        """Cancel and await all active monitoring tasks."""
        logger.info("Shutting down activity sync service...")
        self.host._shutdown = True

        for task in self.host._sync_tasks.values():
            if not task.done():
                task.cancel()

        if self.host._sync_tasks:
            await asyncio.gather(*self.host._sync_tasks.values(), return_exceptions=True)

        self.host._sync_tasks.clear()
        logger.info("Activity sync service shutdown complete")
