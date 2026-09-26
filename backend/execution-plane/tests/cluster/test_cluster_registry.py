"""Tests for Cluster persistence and registration orchestration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Self

import pytest
from execution_plane.models.cluster import Cluster, ClusterStatus
from execution_plane.models.execution_target import BackendType, ExecutionTarget, TargetStatus

_DATABASE_UNAVAILABLE = "database unavailable"
_TARGET_UNAVAILABLE = "target unavailable"
_DISCOVERY_UNAVAILABLE = "discovery unavailable"


def _cluster(*, status: ClusterStatus = ClusterStatus.REGISTERING) -> Cluster:
    now = datetime.now(UTC)
    return Cluster(
        id=uuid.uuid4(),
        name="cluster-a",
        endpoint="https://cluster.example",
        api_key="cluster-secret",
        status=status,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_by=uuid.uuid4(),
        updated_at=now,
    )


def _target(*, cluster_id: uuid.UUID | None = None, is_default: bool = False) -> ExecutionTarget:
    now = datetime.now(UTC)
    return ExecutionTarget(
        id=uuid.uuid4(),
        cluster_id=cluster_id or uuid.uuid4(),
        name="target-a",
        endpoint="https://target.example",
        api_key="target-secret",
        backend_type=BackendType.VANILLA_K8S,
        is_default=is_default,
        status=TargetStatus.ACTIVE,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_by=uuid.uuid4(),
        updated_at=now,
    )


class _Result:
    def __init__(self, cluster: Cluster | None = None, targets: list[ExecutionTarget] | None = None) -> None:
        self.cluster = cluster
        self.targets = targets or []

    def scalar_one_or_none(self) -> ExecutionTarget | None:
        return self.targets[0] if self.targets else None

    def scalars(self) -> Self:
        return self

    def all(self) -> list[ExecutionTarget]:
        return self.targets


class _Session:
    def __init__(
        self, *, cluster: Cluster | None = None, targets: list[ExecutionTarget] | None = None, fail_commit: bool = False
    ) -> None:
        self.cluster = cluster
        self.targets = targets or []
        self.fail_commit = fail_commit
        self.added: Cluster | None = None
        self.deleted: Cluster | None = None
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def add(self, cluster: Cluster) -> None:
        self.added = cluster

    async def get(self, _model: object, _cluster_id: uuid.UUID, **_: object) -> Cluster | None:
        return self.cluster

    async def execute(self, _statement: object) -> _Result:
        return _Result(self.cluster, self.targets)

    async def commit(self) -> None:
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError(_DATABASE_UNAVAILABLE)

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def delete(self, cluster: Cluster) -> None:
        self.deleted = cluster


class _SessionFactory:
    def __init__(self, session: _Session) -> None:
        self.session = session

    def __call__(self) -> _Session:
        return self.session


@pytest.mark.asyncio
async def test_store_creates_a_registering_cluster_and_owns_commit() -> None:
    from execution_plane.cluster.cluster_store import ClusterStore

    store = ClusterStore("postgresql+asyncpg://localhost/syntara")
    session = _Session()
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]
    actor_id = uuid.uuid4()

    cluster = await store.create(
        "cluster-a", "https://cluster.example", "cluster-secret", actor_id, {"region": "eu-west"}
    )

    assert cluster.status is ClusterStatus.REGISTERING
    assert cluster.enabled is True
    assert cluster.api_key == ""
    assert session.added is not None
    assert session.added.api_key == "cluster-secret"
    assert session.added.created_by == actor_id
    assert session.commits == 1
    await store.close()


@pytest.mark.asyncio
async def test_store_rolls_back_failed_cluster_creation() -> None:
    from execution_plane.cluster.cluster_store import ClusterStore

    store = ClusterStore("postgresql+asyncpg://localhost/syntara")
    session = _Session(fail_commit=True)
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="database unavailable"):
        await store.create("cluster-a", "https://cluster.example", "secret", uuid.uuid4())

    assert session.rollbacks == 1
    await store.close()


@pytest.mark.asyncio
async def test_store_records_discovery_failure_on_persisted_cluster() -> None:
    from execution_plane.cluster.cluster_store import ClusterStore

    cluster = _cluster()
    store = ClusterStore("postgresql+asyncpg://localhost/syntara")
    session = _Session(cluster=cluster)
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]

    result = await store.record_discovery_state(cluster.id, ClusterStatus.ERROR, "authentication failed", uuid.uuid4())

    assert result.status is ClusterStatus.ERROR
    assert result.enabled is False
    assert result.status_message == "authentication failed"
    assert session.commits == 1
    await store.close()


@pytest.mark.asyncio
async def test_store_request_delete_drains_cluster_and_its_targets() -> None:
    from execution_plane.cluster.cluster_store import ClusterStore

    cluster = _cluster(status=ClusterStatus.ACTIVE)
    targets = [_target(cluster_id=cluster.id), _target(cluster_id=cluster.id)]
    store = ClusterStore("postgresql+asyncpg://localhost/syntara")
    session = _Session(cluster=cluster, targets=targets)
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]
    actor_id = uuid.uuid4()

    result = await store.request_delete(cluster.id, actor_id)

    assert result.status is ClusterStatus.DRAINING
    assert result.enabled is False
    assert all(target.status is TargetStatus.DRAINING and not target.enabled for target in targets)
    assert all(target.updated_by == actor_id for target in targets)
    await store.close()


@pytest.mark.asyncio
async def test_store_ignores_cluster_finalization_until_targets_are_removed() -> None:
    from execution_plane.cluster.cluster_store import ClusterStore

    cluster = _cluster(status=ClusterStatus.DRAINING)
    cluster.enabled = False
    store = ClusterStore("postgresql+asyncpg://localhost/syntara")
    session = _Session(cluster=cluster, targets=[_target(cluster_id=cluster.id)])
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]

    await store.finalize_delete(cluster.id)

    assert session.deleted is None
    await store.close()


@pytest.mark.asyncio
async def test_store_ignores_cluster_finalization_before_draining() -> None:
    from execution_plane.cluster.cluster_store import ClusterStore

    cluster = _cluster(status=ClusterStatus.ACTIVE)
    store = ClusterStore("postgresql+asyncpg://localhost/syntara")
    session = _Session(cluster=cluster)
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]

    await store.finalize_delete(cluster.id)

    assert session.deleted is None
    await store.close()


class _ClusterStore:
    def __init__(self, cluster: Cluster) -> None:
        self.cluster = cluster
        self.states: list[tuple[ClusterStatus, str | None]] = []
        self.created = False
        self.finalized = False

    async def create(self, *_: object, **__: object) -> Cluster:
        self.created = True
        return self.cluster

    async def record_discovery_state(
        self, _cluster_id: uuid.UUID, status: ClusterStatus, status_message: str | None, _updated_by: uuid.UUID
    ) -> Cluster:
        self.states.append((status, status_message))
        self.cluster.status = status
        self.cluster.status_message = status_message
        self.cluster.enabled = status is not ClusterStatus.ERROR
        return self.cluster

    async def get(self, _cluster_id: uuid.UUID) -> Cluster | None:
        return self.cluster

    async def list(self, **_: object) -> list[Cluster]:
        return [self.cluster]

    async def request_delete(self, _cluster_id: uuid.UUID, _updated_by: uuid.UUID) -> Cluster:
        self.cluster.status = ClusterStatus.DRAINING
        self.cluster.enabled = False
        return self.cluster

    async def finalize_delete(self, _cluster_id: uuid.UUID) -> None:
        self.finalized = True


class _TargetRegistry:
    def __init__(
        self,
        *,
        fail_default: bool = False,
        fail_named: str | None = None,
        targets: list[ExecutionTarget] | None = None,
    ) -> None:
        self.fail_default = fail_default
        self.fail_named = fail_named
        self.created: list[dict[str, object]] = []
        self.targets = targets or []
        self.finalized: list[uuid.UUID] = []

    async def create(self, **kwargs: object) -> ExecutionTarget:
        self.created.append(kwargs)
        if (kwargs["is_default"] and self.fail_default) or kwargs["name"] == self.fail_named:
            raise RuntimeError(_TARGET_UNAVAILABLE)
        return _target(cluster_id=kwargs["cluster_id"] if isinstance(kwargs["cluster_id"], uuid.UUID) else None)

    async def activate(self, target_id: uuid.UUID, _updated_by: uuid.UUID) -> ExecutionTarget:
        return _target(cluster_id=self.targets[0].cluster_id if self.targets else uuid.uuid4())

    async def list(self, **_: object) -> list[ExecutionTarget]:
        return self.targets

    async def finalize_delete(self, target_id: uuid.UUID) -> None:
        self.finalized.append(target_id)

    async def finalize_cluster_target(self, _cluster_id: uuid.UUID, target_id: uuid.UUID) -> None:
        self.finalized.append(target_id)


class _Discovery:
    def __init__(self, result: object) -> None:
        self.result = result
        self.received: object | None = None

    def discover(self, registration: object) -> object:
        self.received = registration
        return self.result


class _FailingDiscovery:
    def discover(self, _registration: object) -> object:
        raise RuntimeError(_DISCOVERY_UNAVAILABLE)


@pytest.mark.asyncio
async def test_registry_creates_every_discovered_target_via_target_registry_then_activates_cluster() -> None:
    from execution_plane.cluster.cluster_registry import (
        ClusterRegistry,
        DiscoveredExecutionTarget,
        DiscoveryResult,
    )

    cluster = _cluster()
    store = _ClusterStore(cluster)
    targets = _TargetRegistry()
    discovery = _Discovery(
        DiscoveryResult.discovered(
            [
                DiscoveredExecutionTarget("primary", BackendType.VANILLA_K8S, "https://one", "key-1", is_default=True),
                DiscoveredExecutionTarget("extra", BackendType.OPENSHELL, "https://two", "key-2"),
            ]
        )
    )
    registry = ClusterRegistry(store, targets, discovery)  # type: ignore[arg-type]

    result = await registry.register("cluster-a", "https://cluster.example", "cluster-secret", uuid.uuid4())

    assert result.status is ClusterStatus.ACTIVE
    assert [target["is_default"] for target in targets.created] == [True, False]
    assert store.states == [(ClusterStatus.ACTIVE, None)]
    assert discovery.received is not None


@pytest.mark.asyncio
async def test_registry_marks_persisted_cluster_error_when_discovery_or_default_target_fails() -> None:
    from execution_plane.cluster.cluster_registry import (
        ClusterRegistry,
        DiscoveredExecutionTarget,
        DiscoveryResult,
    )

    cluster = _cluster()
    store = _ClusterStore(cluster)
    failed_discovery = ClusterRegistry(store, _TargetRegistry(), _Discovery(DiscoveryResult.failed("unreachable")))  # type: ignore[arg-type]

    result = await failed_discovery.register("cluster-a", "https://cluster.example", "cluster-secret", uuid.uuid4())

    assert result.status is ClusterStatus.ERROR
    assert store.states == [(ClusterStatus.ERROR, "discovery failed")]

    cluster = _cluster()
    store = _ClusterStore(cluster)
    default_failure = ClusterRegistry(
        store,  # type: ignore[arg-type]
        _TargetRegistry(fail_default=True),  # type: ignore[arg-type]
        _Discovery(  # type: ignore[arg-type]
            DiscoveryResult.discovered(
                [DiscoveredExecutionTarget("primary", BackendType.VANILLA_K8S, "https://one", "key-1", is_default=True)]
            )
        ),
    )

    result = await default_failure.register("cluster-a", "https://cluster.example", "cluster-secret", uuid.uuid4())

    assert result.status is ClusterStatus.ERROR
    assert "default target" in (result.status_message or "")


@pytest.mark.asyncio
async def test_registry_marks_persisted_cluster_error_when_discovery_raises() -> None:
    from execution_plane.cluster.cluster_registry import ClusterRegistry

    cluster = _cluster()
    store = _ClusterStore(cluster)
    registry = ClusterRegistry(store, _TargetRegistry(), _FailingDiscovery())  # type: ignore[arg-type]

    result = await registry.register("cluster-a", "https://cluster.example", "cluster-secret", uuid.uuid4())

    assert result.status is ClusterStatus.ERROR
    assert result.status_message == "discovery failed"


@pytest.mark.asyncio
async def test_registry_persists_cluster_drain_request() -> None:
    from execution_plane.cluster.cluster_registry import ClusterRegistry

    cluster = _cluster(status=ClusterStatus.ACTIVE)
    store = _ClusterStore(cluster)
    registry = ClusterRegistry(store, _TargetRegistry(), _Discovery(object()))  # type: ignore[arg-type]

    actor_id = uuid.uuid4()
    result = await registry.request_delete(cluster.id, actor_id)

    assert result.status is ClusterStatus.DRAINING


@pytest.mark.asyncio
async def test_registry_marks_cluster_error_when_discovery_returns_no_single_default() -> None:
    from execution_plane.cluster.cluster_registry import (
        ClusterRegistry,
        DiscoveredExecutionTarget,
        DiscoveryResult,
    )

    cluster = _cluster()
    store = _ClusterStore(cluster)
    discovery = _Discovery(
        DiscoveryResult.discovered([DiscoveredExecutionTarget("one", BackendType.VANILLA_K8S, "https://one", "key")])
    )

    result = await ClusterRegistry(store, _TargetRegistry(), discovery).register(  # type: ignore[arg-type]
        "cluster-a", "https://cluster.example", "secret", uuid.uuid4()
    )

    assert result.status is ClusterStatus.ERROR
    assert result.status_message == "Discovery did not provide exactly one default target"


@pytest.mark.asyncio
async def test_registry_keeps_cluster_active_when_a_non_default_target_fails() -> None:
    from execution_plane.cluster.cluster_registry import (
        ClusterRegistry,
        DiscoveredExecutionTarget,
        DiscoveryResult,
    )

    cluster = _cluster()
    store = _ClusterStore(cluster)
    targets = _TargetRegistry(fail_named="extra")
    discovery = _Discovery(
        DiscoveryResult.discovered(
            [
                DiscoveredExecutionTarget("primary", BackendType.VANILLA_K8S, "https://one", "key", is_default=True),
                DiscoveredExecutionTarget("extra", BackendType.OPENSHELL, "https://two", "key"),
            ]
        )
    )

    result = await ClusterRegistry(store, targets, discovery).register(  # type: ignore[arg-type]
        "cluster-a", "https://cluster.example", "secret", uuid.uuid4()
    )

    assert result.status is ClusterStatus.ACTIVE
    assert result.status_message == "Target registration failures: extra"


@pytest.mark.asyncio
async def test_registry_delegates_get_and_list_to_the_cluster_store() -> None:
    from execution_plane.cluster.cluster_registry import ClusterRegistry

    cluster = _cluster()
    registry = ClusterRegistry(_ClusterStore(cluster), _TargetRegistry(), _Discovery(object()))  # type: ignore[arg-type]

    assert await registry.get(cluster.id) is cluster
    assert await registry.list(status=ClusterStatus.ACTIVE, enabled=True) == [cluster]


def test_noop_discovery_returns_a_failed_result() -> None:
    from execution_plane.cluster.cluster_registry import ClusterRegistration, NoopDiscoveryMechanism

    result = NoopDiscoveryMechanism().discover(ClusterRegistration("name", "endpoint", "secret", {}))

    assert result.state.value == "failed"
    assert result.status_message == "No discovery mechanism is configured"
