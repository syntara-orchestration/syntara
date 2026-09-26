"""Tests for execution-plane local bootstrap."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from execution_plane.models.cluster import Cluster, ClusterStatus
from execution_plane.models.execution_target import BackendType, ExecutionTarget, TargetStatus


def _cluster() -> Cluster:
    now = datetime.now(UTC)
    return Cluster(
        name="local-execution-plane",
        endpoint="local://execution-plane",
        api_key="cluster-secret",
        status=ClusterStatus.REGISTERING,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_by=uuid.uuid4(),
        updated_at=now,
    )


class _StoreContext:
    def __init__(self, store: object) -> None:
        self.store = store

    async def __aenter__(self) -> object:
        return self.store

    async def __aexit__(self, *_: object) -> None:
        return None


class _ClusterStore:
    def __init__(self, cluster: Cluster | None = None) -> None:
        self.cluster = cluster
        self.create_calls = 0
        self.state_calls = 0

    async def list(self, **_: object) -> list[Cluster]:
        return [] if self.cluster is None else [self.cluster]

    async def create(self, *_: object, **__: object) -> Cluster:
        self.create_calls += 1
        self.cluster = _cluster()
        return self.cluster

    async def record_discovery_state(
        self, _cluster_id: uuid.UUID, status: ClusterStatus, status_message: str | None, _updated_by: uuid.UUID
    ) -> Cluster:
        assert self.cluster is not None
        self.state_calls += 1
        self.cluster.status = status
        self.cluster.status_message = status_message
        self.cluster.enabled = status is not ClusterStatus.ERROR
        return self.cluster


class _ExecutionTargetStore:
    def __init__(self, targets: list[ExecutionTarget] | None = None) -> None:
        self.targets = targets or []
        self.create_calls = 0
        self.activate_calls = 0

    async def list(self, *, cluster_id: uuid.UUID | None = None, **_: object) -> list[ExecutionTarget]:
        return [target for target in self.targets if cluster_id is None or target.cluster_id == cluster_id]

    async def create(
        self,
        cluster_id: uuid.UUID,
        name: str,
        backend_type: BackendType,
        endpoint: str,
        api_key: str,
        is_default: bool,  # noqa: FBT001
        created_by: uuid.UUID,
        labels: dict[str, object] | None = None,
        **_: object,
    ) -> ExecutionTarget:
        self.create_calls += 1
        target = ExecutionTarget(
            cluster_id=cluster_id,
            name=name,
            backend_type=backend_type,
            endpoint=endpoint,
            api_key=api_key,
            is_default=is_default,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_by=created_by,
            updated_at=datetime.now(UTC),
            labels=labels or {},
        )
        self.targets.append(target)
        return target

    async def activate(self, target_id: uuid.UUID, _updated_by: uuid.UUID) -> ExecutionTarget:
        self.activate_calls += 1
        target = next(target for target in self.targets if target.id == target_id)
        target.status = TargetStatus.ACTIVE
        target.enabled = True
        return target


@pytest.mark.asyncio
async def test_bootstrap_creates_a_local_cluster_and_default_target(monkeypatch: pytest.MonkeyPatch) -> None:
    from execution_plane import bootstrap
    from execution_plane.cluster.cluster_store import ClusterStore
    from execution_plane.execution_target.execution_target_store import ExecutionTargetStore

    cluster_store = _ClusterStore()
    target_store = _ExecutionTargetStore()
    monkeypatch.setattr(ClusterStore, "from_database_url", lambda _url: _StoreContext(cluster_store))
    monkeypatch.setattr(ExecutionTargetStore, "from_database_url", lambda _url: _StoreContext(target_store))

    cluster = await bootstrap.bootstrap_local_cluster("postgresql+asyncpg://localhost/syntara")

    assert cluster.status is ClusterStatus.ACTIVE
    assert cluster_store.create_calls == 1
    assert target_store.create_calls == 1
    assert target_store.activate_calls == 1
    assert target_store.targets[0].is_default is True


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_for_existing_cluster_and_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from execution_plane import bootstrap
    from execution_plane.cluster.cluster_store import ClusterStore
    from execution_plane.execution_target.execution_target_store import ExecutionTargetStore

    cluster = _cluster()
    cluster.status = ClusterStatus.ACTIVE
    target = ExecutionTarget(
        cluster_id=cluster.id,
        name="local-default",
        endpoint="local://execution-plane/default",
        api_key="target-secret",
        backend_type=BackendType.VANILLA_K8S,
        is_default=True,
        status=TargetStatus.ACTIVE,
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_by=uuid.uuid4(),
        updated_at=datetime.now(UTC),
    )
    cluster_store = _ClusterStore(cluster)
    target_store = _ExecutionTargetStore([target])
    monkeypatch.setattr(ClusterStore, "from_database_url", lambda _url: _StoreContext(cluster_store))
    monkeypatch.setattr(ExecutionTargetStore, "from_database_url", lambda _url: _StoreContext(target_store))

    result = await bootstrap.bootstrap_local_cluster("postgresql+asyncpg://localhost/syntara")

    assert result.id == cluster.id
    assert cluster_store.create_calls == 0
    assert target_store.create_calls == 0


@pytest.mark.asyncio
async def test_bootstrap_rejects_incomplete_existing_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    from execution_plane import bootstrap
    from execution_plane.cluster.cluster_store import ClusterStore
    from execution_plane.execution_target.execution_target_store import ExecutionTargetStore

    cluster = _cluster()
    target = ExecutionTarget(
        cluster_id=cluster.id,
        name="local-default",
        endpoint="local://execution-plane/default",
        api_key="target-secret",
        backend_type=BackendType.VANILLA_K8S,
        is_default=True,
        status=TargetStatus.ACTIVE,
        created_by=uuid.uuid4(),
        created_at=datetime.now(UTC),
        updated_by=uuid.uuid4(),
        updated_at=datetime.now(UTC),
    )
    cluster_store = _ClusterStore(cluster)
    target_store = _ExecutionTargetStore([target])
    monkeypatch.setattr(ClusterStore, "from_database_url", lambda _url: _StoreContext(cluster_store))
    monkeypatch.setattr(ExecutionTargetStore, "from_database_url", lambda _url: _StoreContext(target_store))

    with pytest.raises(RuntimeError, match="incomplete"):
        await bootstrap.bootstrap_local_cluster("postgresql+asyncpg://localhost/syntara")


@pytest.mark.asyncio
async def test_bootstrap_repairs_existing_cluster_without_target(monkeypatch: pytest.MonkeyPatch) -> None:
    from execution_plane import bootstrap
    from execution_plane.cluster.cluster_store import ClusterStore
    from execution_plane.execution_target.execution_target_store import ExecutionTargetStore

    cluster_store = _ClusterStore(_cluster())
    target_store = _ExecutionTargetStore()
    monkeypatch.setattr(ClusterStore, "from_database_url", lambda _url: _StoreContext(cluster_store))
    monkeypatch.setattr(ExecutionTargetStore, "from_database_url", lambda _url: _StoreContext(target_store))

    cluster = await bootstrap.bootstrap_local_cluster("postgresql+asyncpg://localhost/syntara")

    assert cluster.status is ClusterStatus.ACTIVE
    assert cluster_store.create_calls == 0
    assert cluster_store.state_calls == 1
    assert target_store.create_calls == 1
    assert target_store.activate_calls == 1
