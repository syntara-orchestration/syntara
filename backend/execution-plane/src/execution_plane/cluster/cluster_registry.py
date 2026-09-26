"""Cluster registration orchestration and discovery boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from execution_plane.models.cluster import Cluster, ClusterStatus

if TYPE_CHECKING:
    import uuid
    from typing import Any

    from execution_plane.cluster.cluster_store import ClusterStore
    from execution_plane.execution_target.execution_target_registry import ExecutionTargetRegistry
    from execution_plane.models.execution_target import BackendType


@dataclass(frozen=True)
class ClusterRegistration:
    """Credential-bearing input passed only to the discovery mechanism."""

    name: str
    endpoint: str
    api_key: str = field(repr=False)
    labels: dict[str, Any]


@dataclass(frozen=True)
class DiscoveredExecutionTarget:
    """Domain-level target definition returned by discovery."""

    name: str
    backend_type: BackendType
    endpoint: str
    api_key: str = field(repr=False)
    is_default: bool = False


class DiscoveryState(StrEnum):
    """Outcome of a synchronous discovery attempt."""

    DISCOVERED = "discovered"
    FAILED = "failed"


@dataclass(frozen=True)
class DiscoveryResult:
    """Discovery state and domain target definitions."""

    state: DiscoveryState
    targets: tuple[DiscoveredExecutionTarget, ...] = ()
    status_message: str | None = None

    @classmethod
    def failed(cls, status_message: str) -> DiscoveryResult:
        """Build a failed discovery result."""
        return cls(DiscoveryState.FAILED, status_message=status_message)

    @classmethod
    def discovered(cls, targets: list[DiscoveredExecutionTarget]) -> DiscoveryResult:
        """Build a successful result containing discovered target definitions."""
        return cls(DiscoveryState.DISCOVERED, tuple(targets))


class DiscoveryMechanism(Protocol):
    """Synchronous, session-free boundary for provider-specific discovery."""

    def discover(self, registration: ClusterRegistration) -> DiscoveryResult:
        """Discover targets for a registered Cluster."""
        ...


class NoopDiscoveryMechanism:
    """Discovery implementation used until a provider-specific mechanism is configured."""

    def discover(self, _registration: ClusterRegistration) -> DiscoveryResult:
        """Report that no discovery mechanism has been configured."""
        return DiscoveryResult.failed("No discovery mechanism is configured")


class ClusterRegistry:
    """Coordinate discovery and target registration without owning sessions."""

    def __init__(
        self,
        store: ClusterStore,
        execution_target_registry: ExecutionTargetRegistry,
        discovery: DiscoveryMechanism,
    ) -> None:
        """Use stores and registries for persistence and target creation."""
        self._store = store
        self._execution_target_registry = execution_target_registry
        self._discovery = discovery

    async def register(
        self,
        name: str,
        endpoint: str,
        api_key: str,
        created_by: uuid.UUID,
        labels: dict[str, Any] | None = None,
    ) -> Cluster:
        """Persist first, discover second, and persist the resulting state."""
        registration = ClusterRegistration(name, endpoint, api_key, labels or {})
        cluster = await self._store.create(name, endpoint, api_key, created_by, labels)
        try:
            result = self._discovery.discover(registration)
        except Exception:  # noqa: BLE001
            return await self._store.record_discovery_state(
                cluster.id, ClusterStatus.ERROR, "discovery failed", created_by
            )
        if result.state is DiscoveryState.FAILED:
            return await self._store.record_discovery_state(
                cluster.id, ClusterStatus.ERROR, "discovery failed", created_by
            )

        defaults = [target for target in result.targets if target.is_default]
        if len(defaults) != 1:
            return await self._store.record_discovery_state(
                cluster.id, ClusterStatus.ERROR, "Discovery did not provide exactly one default target", created_by
            )
        failures: list[str] = []
        ordered_targets = [defaults[0], *(target for target in result.targets if not target.is_default)]
        for target in ordered_targets:
            try:
                created_target = await self._execution_target_registry.create(
                    cluster_id=cluster.id,
                    name=target.name,
                    backend_type=target.backend_type,
                    endpoint=target.endpoint,
                    api_key=target.api_key,
                    is_default=target.is_default,
                    created_by=created_by,
                )
                await self._execution_target_registry.activate(created_target.id, created_by)
            except Exception:  # noqa: BLE001
                if target.is_default:
                    return await self._store.record_discovery_state(
                        cluster.id, ClusterStatus.ERROR, "default target registration failed", created_by
                    )
                failures.append(target.name)
        status_message = f"Target registration failures: {', '.join(failures)}" if failures else None
        return await self._store.record_discovery_state(cluster.id, ClusterStatus.ACTIVE, status_message, created_by)

    async def get(self, cluster_id: uuid.UUID) -> Cluster | None:
        """Return a Cluster through the persistence boundary."""
        return await self._store.get(cluster_id)

    async def list(self, *, status: ClusterStatus | None = None, enabled: bool | None = None) -> list[Cluster]:
        """List Clusters for administrative or recovery workflows."""
        return await self._store.list(status=status, enabled=enabled)

    async def request_delete(self, cluster_id: uuid.UUID, updated_by: uuid.UUID) -> Cluster:
        """Disable a Cluster and mark its targets as DRAINING."""
        return await self._store.request_delete(cluster_id, updated_by)
