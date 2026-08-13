"""Standalone Temporal background worker entrypoint.

This worker polls the ``orchestrator-background-queue`` task queue and executes
built-in workflows only (Document Conversion, Agent Execution).

It runs a reduced activity set — only the activities required by built-in
workflows — which gives it a smaller attack surface and lower resource
footprint compared to the main workflow worker.

The main workflow worker (syntara.workflows.worker) continues to handle all
user-authored workflows on the ``orchestrator-workflow-queue`` task queue. Queue
isolation ensures that a burst of system operations (e.g. bulk file uploads
triggering many document conversions) cannot starve user workflow execution.

Usage:
    python -m syntara.workflows.background_worker

Environment Variables:
    APP_TEMPORAL_ADDRESS: Temporal server address (default: localhost:7233)
    APP_TEMPORAL_NAMESPACE: Temporal namespace (default: default)
    APP_BACKGROUND_TASK_QUEUE: Background task queue name (default: orchestrator-background-queue)
    APP_FALLBACK_LOG_LEVEL: Logging level before runtime settings load (default: INFO)

"""

import asyncio

from syntara.core.config.base import get_settings, validate_encryption_key_at_startup
from syntara.core.logging.lifecycle import start_loggers, stop_loggers
from syntara.workflows.worker_lifecycle import run_worker
from syntara.workflows.workflow_engine.activities.registry import BACKGROUND_ACTIVITY_REGISTRY
from syntara.workflows.workflow_engine.services.temporal_worker import TemporalWorkerService, start_worker

# Initialize logging subsystems (stdout + OTLP handlers)
start_loggers()


async def main() -> None:
    """Run the Temporal background worker."""
    validate_encryption_key_at_startup()
    # Fail fast if timezone data is missing (AAP-86297)
    from syntara.workflows.workflow_engine.models.workflow_definition import _get_valid_timezones  # noqa: PLC0415

    _get_valid_timezones()
    settings = get_settings()

    async def _start() -> TemporalWorkerService:
        return await start_worker(
            task_queue=settings.background_task_queue,
            activity_registry=BACKGROUND_ACTIVITY_REGISTRY,
        )

    try:
        await run_worker(_start, worker_name="orchestrator-background-worker")
    finally:
        stop_loggers()


if __name__ == "__main__":
    asyncio.run(main())
