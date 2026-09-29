"""Adapt persisted Cluster and ExecutionTarget rows into reconciler snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING

from execution_plane.execution_target_reconciler.filters import default_filters
from execution_plane.execution_target_reconciler.placement import PlacementResolver, WorkerManagerRegistry
from execution_plane.execution_target_reconciler.protocols import ExecutionTargetRegistry
from execution_plane.execution_target_reconciler.reconciler import ExecutionTargetReconciler
from execution_plane.execution_target_reconciler.types import ClusterSnapshot, ExecutionTargetSnapshot
from execution_plane.models.cluster import ClusterStatus

if TYPE_CHECKING:
    from collections.abc import Sequence

    from execution_plane.cluster.cluster_store import ClusterStore
    from execution_plane.execution_target.execution_target_store import ExecutionTargetStore
    from execution_plane.execution_target_reconciler.protocols import EligibilityFilter
    from execution_plane.models.cluster import Cluster
    from execution_plane.models.execution_target import ExecutionTarget


def cluster_snapshot_from_model(cluster: Cluster) -> ClusterSnapshot:
    """Map a Cluster row to a reconciler snapshot. Non-ACTIVE clusters are ineligible."""
    return ClusterSnapshot(
        id=cluster.id,
        name=cluster.name,
        labels=dict(cluster.labels),
        cluster_type=cluster.cluster_type,
        enabled=cluster.enabled and cluster.status is ClusterStatus.ACTIVE,
    )


def execution_target_snapshot_from_model(
    target: ExecutionTarget,
    cluster: ClusterSnapshot,
) -> ExecutionTargetSnapshot:
    """Map an ExecutionTarget row onto a snapshot that shares `cluster`."""
    return ExecutionTargetSnapshot(
        id=target.id,
        cluster=cluster,
        name=target.name,
        namespace=target.namespace,
        backend_type=target.backend_type,
        labels=dict(target.labels),
        lifecycle=target.status.value,
        enabled=target.enabled,
        is_default=target.is_default,
    )


class ExecutionTargetStoreAdapter(ExecutionTargetRegistry):
    """`ExecutionTargetRegistry` Protocol backed by Cluster and ExecutionTarget stores."""

    def __init__(self, cluster_store: ClusterStore, target_store: ExecutionTargetStore) -> None:
        """Load Clusters first so every target of a Cluster shares one snapshot instance."""
        self._clusters = cluster_store
        self._targets = target_store

    async def list(self) -> Sequence[ExecutionTargetSnapshot]:
        """Return all targets with interned Cluster backrefs. Orphans with no Cluster are omitted."""
        interned = {cluster.id: cluster_snapshot_from_model(cluster) for cluster in await self._clusters.list()}
        return tuple(
            execution_target_snapshot_from_model(row, interned[row.cluster_id])
            for row in await self._targets.list()
            if row.cluster_id in interned
        )


def store_backed_target_registry(
    cluster_store: ClusterStore,
    target_store: ExecutionTargetStore,
) -> ExecutionTargetStoreAdapter:
    """Build a flat target registry that interns ClusterSnapshot instances."""
    return ExecutionTargetStoreAdapter(cluster_store, target_store)


def build_placement_resolver(
    cluster_store: ClusterStore,
    target_store: ExecutionTargetStore,
    worker_managers: WorkerManagerRegistry | None = None,
    filters: Sequence[EligibilityFilter] | None = None,
) -> PlacementResolver:
    """Construct the co-located PlacementResolver used by the worker process."""
    return PlacementResolver(
        ExecutionTargetReconciler(
            store_backed_target_registry(cluster_store, target_store),
            filters or default_filters(),
        ),
        worker_managers or WorkerManagerRegistry(),
    )
