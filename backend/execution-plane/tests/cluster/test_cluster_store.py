"""Additional unit tests for ClusterStore persistence branches."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Self

import pytest
from execution_plane.cluster.cluster_store import (
    ClusterNotFoundError,
    ClusterStore,
)
from execution_plane.models.cluster import Cluster, ClusterStatus
from execution_plane.models.execution_target import BackendType, ExecutionTarget, TargetStatus

_DATABASE_UNAVAILABLE = "database unavailable"


def _cluster(*, status: ClusterStatus = ClusterStatus.ACTIVE) -> Cluster:
    now = datetime.now(UTC)
    return Cluster(
        id=uuid.uuid4(),
        name="cluster-a",
        endpoint="https://cluster.example",
        api_key="secret",
        status=status,
        enabled=status is not ClusterStatus.ERROR,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_by=uuid.uuid4(),
        updated_at=now,
    )


def _target(cluster_id: uuid.UUID) -> ExecutionTarget:
    now = datetime.now(UTC)
    return ExecutionTarget(
        id=uuid.uuid4(),
        cluster_id=cluster_id,
        name="target-a",
        backend_type=BackendType.VANILLA_K8S,
        endpoint="https://target.example",
        api_key="secret",
        status=TargetStatus.ACTIVE,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_by=uuid.uuid4(),
        updated_at=now,
    )


class _Result:
    def __init__(self, clusters: list[Cluster] | None = None, targets: list[ExecutionTarget] | None = None) -> None:
        self.clusters = clusters or []
        self.targets = targets or []

    def scalars(self) -> Self:
        return self

    def all(self) -> list[Cluster] | list[ExecutionTarget]:
        return self.clusters or self.targets


class _Session:
    def __init__(
        self,
        *,
        cluster: Cluster | None = None,
        targets: list[ExecutionTarget] | None = None,
        fail_commit: bool = False,
    ) -> None:
        self.cluster = cluster
        self.result = _Result(targets=targets)
        self.fail_commit = fail_commit
        self.deleted: Cluster | None = None
        self.added: Cluster | None = None
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
        return self.result

    async def commit(self) -> None:
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


def _store(session: _Session) -> ClusterStore:
    store = ClusterStore("postgresql+asyncpg://localhost/syntara")
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]
    return store


@pytest.mark.asyncio
async def test_get_redacts_cluster_credentials_and_returns_none_when_missing() -> None:
    cluster = _cluster()
    store = _store(_Session(cluster=cluster))

    result = await store.get(cluster.id)
    assert result is not None
    assert result.api_key == ""
    assert await _store(_Session()).get(uuid.uuid4()) is None
    await store.close()


@pytest.mark.asyncio
async def test_create_preserves_database_rejection_for_a_duplicate_endpoint() -> None:
    from sqlalchemy.exc import IntegrityError

    class DuplicateEndpointSession(_Session):
        async def commit(self) -> None:
            statement = "insert"
            raise IntegrityError(statement, {}, RuntimeError("clusters_endpoint_key"))

    session = DuplicateEndpointSession()
    store = _store(session)

    with pytest.raises(IntegrityError):
        await store.create("cluster-a", "https://cluster.example", "secret", uuid.uuid4())

    assert session.rollbacks == 1
    await store.close()


@pytest.mark.asyncio
async def test_list_redacts_clusters_and_supports_status_and_enabled_filters() -> None:
    cluster = _cluster()
    store = _store(_Session())
    session = _Session()
    session.result = _Result([cluster])
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]

    result = await store.list(status=ClusterStatus.ACTIVE, enabled=True)

    assert [item.api_key for item in result] == [""]
    await store.close()


@pytest.mark.asyncio
async def test_record_discovery_state_rolls_back_for_a_missing_cluster() -> None:
    session = _Session()
    store = _store(session)

    with pytest.raises(ClusterNotFoundError):
        await store.record_discovery_state(uuid.uuid4(), ClusterStatus.ERROR, "failed", uuid.uuid4())

    assert session.rollbacks == 1
    await store.close()


@pytest.mark.asyncio
async def test_record_discovery_state_does_not_undo_a_delete_request() -> None:
    cluster = _cluster(status=ClusterStatus.DRAINING)
    cluster.enabled = False
    session = _Session(cluster=cluster)
    store = _store(session)

    result = await store.record_discovery_state(cluster.id, ClusterStatus.ACTIVE, None, uuid.uuid4())

    assert result.status is ClusterStatus.DRAINING
    assert result.enabled is False
    await store.close()


@pytest.mark.asyncio
async def test_mark_drain_failed_persists_error_on_a_draining_cluster() -> None:
    cluster = _cluster(status=ClusterStatus.DRAINING)
    cluster.enabled = False
    session = _Session(cluster=cluster)
    store = _store(session)
    actor_id = uuid.uuid4()

    result = await store.mark_drain_failed(cluster.id, "cluster drain failed", actor_id)

    assert result.status is ClusterStatus.ERROR
    assert result.enabled is False
    assert result.status_message == "cluster drain failed"
    assert result.updated_by == actor_id
    await store.close()


@pytest.mark.asyncio
async def test_request_delete_rolls_back_for_a_missing_cluster() -> None:
    session = _Session()
    store = _store(session)

    with pytest.raises(ClusterNotFoundError):
        await store.request_delete(uuid.uuid4(), uuid.uuid4())

    assert session.rollbacks == 1
    await store.close()


@pytest.mark.asyncio
async def test_finalize_delete_removes_a_drained_cluster_without_targets() -> None:
    cluster = _cluster(status=ClusterStatus.DRAINING)
    cluster.enabled = False
    session = _Session(cluster=cluster)
    store = _store(session)

    await store.finalize_delete(cluster.id)

    assert session.deleted is cluster
    await store.close()


@pytest.mark.asyncio
async def test_finalize_delete_ignores_a_missing_cluster() -> None:
    session = _Session()
    store = _store(session)

    await store.finalize_delete(uuid.uuid4())

    assert session.rollbacks == 0
    await store.close()


@pytest.mark.asyncio
async def test_finalize_delete_rolls_back_when_commit_fails() -> None:
    cluster = _cluster(status=ClusterStatus.DRAINING)
    cluster.enabled = False
    session = _Session(cluster=cluster, fail_commit=True)
    store = _store(session)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await store.finalize_delete(cluster.id)

    assert session.rollbacks == 1
    await store.close()


@pytest.mark.asyncio
async def test_request_delete_marks_each_target_as_draining() -> None:
    cluster = _cluster()
    targets = [_target(cluster.id)]
    session = _Session(cluster=cluster, targets=targets)
    store = _store(session)

    result = await store.request_delete(cluster.id, uuid.uuid4())

    assert result.status is ClusterStatus.DRAINING
    assert targets[0].status is TargetStatus.DRAINING
    await store.close()


@pytest.mark.asyncio
async def test_finalize_delete_ignores_a_cluster_with_remaining_targets() -> None:
    cluster = _cluster(status=ClusterStatus.DRAINING)
    cluster.enabled = False
    session = _Session(cluster=cluster, targets=[_target(cluster.id)])
    store = _store(session)

    await store.finalize_delete(cluster.id)

    await store.close()


@pytest.mark.asyncio
async def test_finalize_delete_ignores_an_enabled_cluster() -> None:
    cluster = _cluster(status=ClusterStatus.DRAINING)
    cluster.enabled = True
    session = _Session(cluster=cluster)
    store = _store(session)

    await store.finalize_delete(cluster.id)

    await store.close()
