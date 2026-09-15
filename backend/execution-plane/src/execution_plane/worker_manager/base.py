"""WorkerManager protocol — the swappable backend interface.

Concrete implementations (VanillaK8sWorkerManager, OpenShellWorkerManager) live
in submodules. The Task Executor selects an implementation at startup based on the
pool's backend_type.
"""

from __future__ import annotations

from typing import Any, Protocol

from execution_plane.models.work_item import WorkItem


class WorkerManager(Protocol):
    """Claims a worker, dispatches a work item, streams stdout, and returns the result."""

    async def dispatch(self, work_item: WorkItem) -> dict[str, Any]:
        """Dispatch work_item to an available worker and return the terminal result."""
        ...
