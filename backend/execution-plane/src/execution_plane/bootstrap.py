"""Bootstrap the local execution environment used by the Execution Plane worker."""

from __future__ import annotations

import uuid

from execution_plane.cluster.cluster_registry import (
    ClusterRegistration,
    ClusterRegistry,
    DiscoveredExecutionTarget,
    DiscoveryMechanism,
    DiscoveryResult,
)
from execution_plane.cluster.cluster_store import ClusterStore
from execution_plane.execution_target.execution_target_registry import ExecutionTargetRegistry
from execution_plane.execution_target.execution_target_store import ExecutionTargetStore
from execution_plane.models.cluster import Cluster, ClusterStatus
from execution_plane.models.execution_target import BackendType, ExecutionTarget, TargetStatus

LOCAL_CLUSTER_NAME = "local-execution-plane"
LOCAL_CLUSTER_ENDPOINT = "local://execution-plane"
LOCAL_TARGET_NAME = "local-default"
LOCAL_TARGET_ENDPOINT = "local://execution-plane/default"
LOCAL_API_KEY = "local-execution-plane"
BOOTSTRAP_ACTOR_ID = uuid.UUID(int=0)


class LocalClusterBootstrapError(RuntimeError):
    """Raised when the persisted local Cluster cannot safely be used."""

    def __init__(self, status: ClusterStatus) -> None:
        """Identify the incomplete registration state."""
        super().__init__(f"Local Cluster registration is incomplete: {status.value}")


class LocalDiscoveryMechanism:
    """Describe the local compute environment as one default target."""

    def discover(self, registration: ClusterRegistration) -> DiscoveryResult:  # noqa: ARG002
        """Return the in-process local execution target."""
        return DiscoveryResult.discovered(
            [
                DiscoveredExecutionTarget(
                    name=LOCAL_TARGET_NAME,
                    backend_type=BackendType.VANILLA_K8S,
                    endpoint=LOCAL_TARGET_ENDPOINT,
                    api_key=LOCAL_API_KEY,
                    is_default=True,
                )
            ]
        )


async def bootstrap_local_cluster(
    database_url: str,
    created_by: uuid.UUID = BOOTSTRAP_ACTOR_ID,
) -> Cluster:
    """Ensure the local Cluster and its default target exist before polling."""
    discovery: DiscoveryMechanism = LocalDiscoveryMechanism()
    async with (
        ClusterStore.from_database_url(database_url) as cluster_store,
        ExecutionTargetStore.from_database_url(database_url) as target_store,
    ):
        target_registry = ExecutionTargetRegistry(target_store)
        cluster_registry = ClusterRegistry(cluster_store, target_registry, discovery)
        cluster = next(
            (candidate for candidate in await cluster_registry.list() if candidate.endpoint == LOCAL_CLUSTER_ENDPOINT),
            None,
        )
        if cluster is None:
            cluster = await cluster_registry.register(
                LOCAL_CLUSTER_NAME,
                LOCAL_CLUSTER_ENDPOINT,
                LOCAL_API_KEY,
                created_by,
            )
            targets = await target_registry.list(cluster_id=cluster.id)
            if _is_healthy(cluster, targets):
                return cluster
            raise LocalClusterBootstrapError(cluster.status)

        targets = await target_registry.list(cluster_id=cluster.id)
        if _is_healthy(cluster, targets):
            return cluster
        if targets or not cluster.enabled or cluster.status is not ClusterStatus.REGISTERING:
            raise LocalClusterBootstrapError(cluster.status)

        result = discovery.discover(ClusterRegistration(LOCAL_CLUSTER_NAME, LOCAL_CLUSTER_ENDPOINT, "", {}))
        target = result.targets[0]
        created_target = await target_registry.create(
            cluster_id=cluster.id,
            name=target.name,
            backend_type=target.backend_type,
            endpoint=target.endpoint,
            api_key=target.api_key,
            is_default=target.is_default,
            created_by=created_by,
        )
        await target_registry.activate(created_target.id, created_by)
        return await cluster_store.record_discovery_state(
            cluster.id,
            ClusterStatus.ACTIVE,
            None,
            created_by,
        )


def _is_healthy(cluster: Cluster, targets: list[ExecutionTarget]) -> bool:
    """Return whether the local Cluster has one usable default target."""
    defaults = [target for target in targets if target.is_default]
    return (
        cluster.enabled
        and cluster.status is ClusterStatus.ACTIVE
        and len(defaults) == 1
        and defaults[0].enabled
        and defaults[0].status is TargetStatus.ACTIVE
    )
