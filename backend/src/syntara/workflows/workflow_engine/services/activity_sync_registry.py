"""Registry for ActivitySyncService instance.

This module provides a dependency injection mechanism for the ActivitySyncService,
allowing it to be accessed by internal activities without creating circular imports.
"""

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from syntara.workflows.workflow_engine.services.activity_sync_service import ActivitySyncService


class ActivitySyncRegistry:
    """Registry for managing ActivitySyncService lifecycle without global variables."""

    def __init__(self) -> None:
        """Initialize the registry."""
        self._service: ActivitySyncService | None = None

    def set_service(self, service: "ActivitySyncService | None") -> None:
        """Register the ActivitySyncService instance.

        This should be called by the TemporalWorkerService when it starts/stops.

        Args:
            service: ActivitySyncService instance or None

        """
        self._service = service

    def get_service(self) -> "ActivitySyncService | None":
        """Get the registered ActivitySyncService instance.

        Returns:
            ActivitySyncService if registered, None otherwise

        """
        return self._service


@lru_cache(maxsize=1)
def _get_registry() -> ActivitySyncRegistry:
    """Get the singleton ActivitySyncRegistry instance.

    lru_cache provides thread-safe singleton without global mutable state.
    The registry itself manages the mutable service reference.

    Returns:
        The shared ActivitySyncRegistry instance

    """
    return ActivitySyncRegistry()


def set_activity_sync_service(service: "ActivitySyncService | None") -> None:
    """Register the ActivitySyncService instance.

    This should be called by the TemporalWorkerService when it starts/stops.

    Args:
        service: ActivitySyncService instance or None

    """
    _get_registry().set_service(service)


def get_activity_sync_service() -> "ActivitySyncService | None":
    """Get the registered ActivitySyncService instance.

    Returns:
        ActivitySyncService if registered, None otherwise

    """
    return _get_registry().get_service()
