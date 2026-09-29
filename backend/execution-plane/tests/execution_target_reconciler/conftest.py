"""Shared builders for ExecutionTarget Reconciler tests."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from execution_plane.execution_target_reconciler.filters import default_filters
from execution_plane.execution_target_reconciler.protocols import ExecutionTargetRegistry
from execution_plane.execution_target_reconciler.reconciler import ExecutionTargetReconciler
from execution_plane.execution_target_reconciler.types import (
    ACTIVE_LIFECYCLE,
    ClusterSnapshot,
    ExecutionTargetSnapshot,
)
from execution_plane.models.cluster import ClusterType
from execution_plane.models.execution_target import BackendType

MakeCluster = Callable[..., ClusterSnapshot]
MakeTarget = Callable[..., ExecutionTargetSnapshot]


def cluster_snapshot(
    *,
    name: str = "local-openshift",
    labels: dict[str, str] | None = None,
    enabled: bool = True,
    cluster_type: ClusterType = ClusterType.OPENSHIFT,
    cluster_id: uuid.UUID | None = None,
) -> ClusterSnapshot:
    """Build a Cluster snapshot with stable defaults."""
    return ClusterSnapshot(
        id=cluster_id or uuid.uuid4(),
        name=name,
        labels=labels or {},
        cluster_type=cluster_type,
        enabled=enabled,
    )


def target_snapshot(
    cluster: ClusterSnapshot,
    *,
    name: str = "ep-default",
    namespace: str = "ao-execution",
    backend_type: BackendType = BackendType.VANILLA_K8S,
    labels: dict[str, str] | None = None,
    lifecycle: str = ACTIVE_LIFECYCLE,
    enabled: bool = True,
    is_default: bool = False,
    target_id: uuid.UUID | None = None,
) -> ExecutionTargetSnapshot:
    """Build an ExecutionTarget snapshot attached to `cluster`."""
    return ExecutionTargetSnapshot(
        id=target_id or uuid.uuid4(),
        cluster=cluster,
        name=name,
        namespace=namespace,
        backend_type=backend_type,
        labels=labels or {},
        lifecycle=lifecycle,
        enabled=enabled,
        is_default=is_default,
    )


class StaticTargetRegistry(ExecutionTargetRegistry):
    """In-memory ExecutionTargetRegistry Protocol implementation."""

    def __init__(self, targets: list[ExecutionTargetSnapshot]) -> None:
        """Hold the ExecutionTarget snapshots to return from list."""
        self.targets = targets

    async def list(self) -> list[ExecutionTargetSnapshot]:
        return self.targets


def reconciler_for(targets: list[ExecutionTargetSnapshot]) -> ExecutionTargetReconciler:
    """Build a reconciler over a flat static target list."""
    return ExecutionTargetReconciler(StaticTargetRegistry(targets), default_filters())


@pytest.fixture
def make_cluster() -> MakeCluster:
    return cluster_snapshot


@pytest.fixture
def make_target() -> MakeTarget:
    return target_snapshot


@pytest.fixture
def make_reconciler() -> Callable[[list[ExecutionTargetSnapshot]], ExecutionTargetReconciler]:
    return reconciler_for
