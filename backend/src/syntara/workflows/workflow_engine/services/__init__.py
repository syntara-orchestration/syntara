"""Workflow engine services for Temporal execution and worker management.

This module uses lazy imports via __getattr__ to avoid circular import issues
while maintaining a clean public API.
"""

from typing import Any

__all__ = [
    "TemporalExecutionService",
    "TemporalWorkerService",
    "create_temporal_execution_service",
    "get_activity_sync_service",
    "get_worker",
    "start_worker",
    "stop_worker",
]


def __getattr__(name: str) -> Any:  # noqa: ANN401, PLR0911
    """Lazy import to avoid circular dependencies.

    This allows the registry to be imported without triggering imports
    of temporal_worker, which would create a circular dependency with
    internal activities.

    Args:
        name: Attribute name to import

    Returns:
        The imported attribute

    Raises:
        AttributeError: If the attribute is not defined

    """
    if name == "get_activity_sync_service":
        from syntara.workflows.workflow_engine.services.activity_sync_registry import (  # noqa: PLC0415
            get_activity_sync_service,
        )

        return get_activity_sync_service

    if name == "TemporalExecutionService":
        from syntara.workflows.workflow_engine.services.temporal_execution_service import (  # noqa: PLC0415
            TemporalExecutionService,
        )

        return TemporalExecutionService

    if name == "create_temporal_execution_service":
        from syntara.workflows.workflow_engine.services.temporal_execution_service import (  # noqa: PLC0415
            create_temporal_execution_service,
        )

        return create_temporal_execution_service

    if name == "TemporalWorkerService":
        from syntara.workflows.workflow_engine.services.temporal_worker import (  # noqa: PLC0415
            TemporalWorkerService,
        )

        return TemporalWorkerService

    if name == "get_worker":
        from syntara.workflows.workflow_engine.services.temporal_worker import get_worker  # noqa: PLC0415

        return get_worker

    if name == "start_worker":
        from syntara.workflows.workflow_engine.services.temporal_worker import start_worker  # noqa: PLC0415

        return start_worker

    if name == "stop_worker":
        from syntara.workflows.workflow_engine.services.temporal_worker import stop_worker  # noqa: PLC0415

        return stop_worker

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
