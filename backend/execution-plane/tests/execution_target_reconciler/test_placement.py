"""PlacementResolver and WorkerManagerRegistry."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import pytest
from execution_plane.execution_target_reconciler.exceptions import UnknownBackendTypeError
from execution_plane.execution_target_reconciler.placement import PlacementResolver, WorkerManagerRegistry
from execution_plane.execution_target_reconciler.reconciler import ExecutionTargetReconciler
from execution_plane.execution_target_reconciler.types import (
    ClusterSnapshot,
    ExecutionTargetSnapshot,
    ResolveOutcome,
    WorkRequirements,
)

if TYPE_CHECKING:
    from execution_plane.models.work_item import WorkItem

MakeCluster = Callable[..., ClusterSnapshot]
MakeTarget = Callable[..., ExecutionTargetSnapshot]
MakeReconciler = Callable[[list[ExecutionTargetSnapshot]], ExecutionTargetReconciler]


class _Manager:
    async def dispatch(self, work_item: WorkItem) -> dict[str, Any]:
        return {"id": str(work_item.id)}


@pytest.mark.asyncio
async def test_placement_resolver_delegates_resolve_and_looks_up_backend(
    make_cluster: MakeCluster, make_target: MakeTarget, make_reconciler: MakeReconciler
) -> None:
    cluster = make_cluster()
    target = make_target(cluster, backend_type="openshell", labels={"backend_type": "openshell"})
    reconciler = make_reconciler([target])
    managers = WorkerManagerRegistry()
    manager = _Manager()
    managers.register("openshell", manager)
    placement = PlacementResolver(reconciler, managers)

    result = await placement.resolve(WorkRequirements(selectors={"backend_type": "openshell"}))

    assert result.outcome is ResolveOutcome.MATCHED
    assert placement.worker_manager_for(result.available_targets[0]) is manager


def test_worker_manager_registry_raises_for_unknown_backend(make_cluster: MakeCluster, make_target: MakeTarget) -> None:
    cluster = make_cluster()
    target = make_target(cluster, backend_type="agent_sandbox")
    placement = PlacementResolver(
        object(),  # type: ignore[arg-type]
        WorkerManagerRegistry(),
    )
    with pytest.raises(UnknownBackendTypeError, match="agent_sandbox"):
        placement.worker_manager_for(target)
