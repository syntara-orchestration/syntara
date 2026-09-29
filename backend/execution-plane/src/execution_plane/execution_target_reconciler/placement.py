"""PlacementResolver facade and local WorkerManager registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from execution_plane.execution_target_reconciler.exceptions import UnknownBackendTypeError

if TYPE_CHECKING:
    from execution_plane.execution_target_reconciler.reconciler import ExecutionTargetReconciler
    from execution_plane.execution_target_reconciler.types import (
        ExecutionTargetSnapshot,
        ReconcileResult,
        WorkRequirements,
    )
    from execution_plane.models.execution_target import BackendType
    from execution_plane.worker_manager.base import WorkerManager


class WorkerManagerRegistry:
    """In-process map from ExecutionTarget `backend_type` to a WorkerManager instance."""

    def __init__(self) -> None:
        """Start with no registered backends."""
        self._managers: dict[BackendType, WorkerManager] = {}

    def register(self, backend_type: BackendType, manager: WorkerManager) -> None:
        """Associate a WorkerManager with a backend type. Later registers overwrite."""
        self._managers[backend_type] = manager

    def get(self, backend_type: BackendType) -> WorkerManager:
        """Return the WorkerManager for `backend_type`, or raise if none is registered."""
        try:
            return self._managers[backend_type]
        except KeyError:
            raise UnknownBackendTypeError(backend_type) from None


class PlacementResolver:
    """Thin local facade: reconcile, then look up a WorkerManager after the scheduler picks a target."""

    def __init__(
        self,
        reconciler: ExecutionTargetReconciler,
        worker_managers: WorkerManagerRegistry,
    ) -> None:
        """Bind the query reconciler and the local WorkerManager registry."""
        self._reconciler = reconciler
        self._worker_managers = worker_managers

    async def resolve(self, requirements: WorkRequirements) -> ReconcileResult:
        """Return the eligible ExecutionTarget set. Does not pick a winner."""
        return await self._reconciler.resolve(requirements)

    def worker_manager_for(self, target: ExecutionTargetSnapshot) -> WorkerManager:
        """Return the WorkerManager for this target's backend. Configuration error if missing."""
        return self._worker_managers.get(target.backend_type)
