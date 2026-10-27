"""Standalone Temporal worker entrypoint.

This module provides the entrypoint for running the Temporal worker
as a separate process or container. The worker polls the Temporal server
for workflow and activity tasks and executes them.

Usage:
    python -m syntara.workflows.worker

Environment Variables:
    APP_TEMPORAL_ADDRESS: Temporal server address (default: localhost:7233)
    APP_TEMPORAL_NAMESPACE: Temporal namespace (default: default)
    APP_TASK_QUEUE: Task queue name (default: orchestrator-workflow-queue)
    APP_FALLBACK_LOG_LEVEL: Logging level before runtime settings load (default: INFO)

"""

import asyncio
from functools import partial

from syntara.core.config.base import validate_encryption_key_at_startup
from syntara.core.logging.lifecycle import start_loggers, stop_loggers
from syntara.workers.registration import build_activity_registry
from syntara.workflow_runtime.engines.temporal.services.temporal_worker import start_worker, stop_worker
from syntara.workflows.worker_lifecycle import run_worker
from syntara.workflows.workflow_engine.activities.registry import ACTIVITY_REGISTRY

__all__ = ["stop_worker"]  # re-exported for backward compat with tests and external callers

# Initialize logging subsystems (stdout + OTLP handlers)
start_loggers()


async def main() -> None:
    """Run the Temporal workflow worker."""
    validate_encryption_key_at_startup()
    # Fail fast if timezone data is missing (AAP-86297)
    from syntara.workflow_runtime.engines.temporal.models.workflow_definition import (  # noqa: PLC0415
        _get_valid_timezones,
    )

    _get_valid_timezones()
    try:
        await run_worker(
            partial(
                start_worker,
                activity_registry=ACTIVITY_REGISTRY,
                registered_activity_registry=build_activity_registry(),
            ),
            worker_name="orchestrator-workflow-worker",
        )
    finally:
        stop_loggers()


if __name__ == "__main__":
    asyncio.run(main())
