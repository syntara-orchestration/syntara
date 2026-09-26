"""Tests for execution-target persistence and lifecycle boundaries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Self

import pytest
from execution_plane.execution_target.execution_target_registry import ExecutionTargetRegistry
from execution_plane.execution_target.execution_target_store import (
    DefaultExecutionTargetError,
    ExecutionTargetNotFoundError,
    ExecutionTargetStore,
)
from execution_plane.models.cluster import Cluster, ClusterStatus
from execution_plane.models.execution_target import BackendType, ExecutionTarget, TargetStatus
from sqlalchemy.pool import NullPool

_DATABASE_UNAVAILABLE = "database unavailable"


def _target(*, is_default: bool = False, status: TargetStatus = TargetStatus.REGISTERING) -> ExecutionTarget:
    """Build a target with concrete values independent of the store."""
    now = datetime.now(UTC)
    return ExecutionTarget(
        id=uuid.uuid4(),
        cluster_id=uuid.uuid4(),
        name="target-a",
        backend_type=BackendType.VANILLA_K8S,
        endpoint="https://target.example",
        api_key="secret",
        is_default=is_default,
        status=status,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_by=uuid.uuid4(),
        updated_at=now,
    )


def _cluster() -> Cluster:
    now = datetime.now(UTC)
    return Cluster(
        id=uuid.uuid4(),
        name="cluster-a",
        endpoint="https://cluster.example",
        api_key="secret",
        status=ClusterStatus.REGISTERING,
        enabled=True,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_by=uuid.uuid4(),
        updated_at=now,
    )


class _Result:
    def __init__(self, item: ExecutionTarget | None = None) -> None:
        self.item = item

    def scalar_one_or_none(self) -> ExecutionTarget | None:
        return self.item

    def scalars(self) -> Self:
        return self

    def all(self) -> list[ExecutionTarget]:
        return [] if self.item is None else [self.item]


class _Session:
    def __init__(self, *, result: _Result | None = None, fail_commit: bool = False) -> None:
        self.result = result or _Result()
        self.cluster = _cluster()
        self.fail_commit = fail_commit
        self.added: ExecutionTarget | None = None
        self.deleted: ExecutionTarget | None = None
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def add(self, target: ExecutionTarget) -> None:
        self.added = target

    async def execute(self, _statement: object) -> _Result:
        return self.result

    async def get(self, model: object, _target_id: uuid.UUID, **_: object) -> ExecutionTarget | Cluster | None:
        if model is Cluster:
            return self.cluster
        return self.result.item

    async def commit(self) -> None:
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError(_DATABASE_UNAVAILABLE)

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def delete(self, target: ExecutionTarget) -> None:
        self.deleted = target


class _SessionFactory:
    def __init__(self, session: _Session) -> None:
        self.session = session

    def __call__(self) -> _Session:
        return self.session


class _Store:
    def __init__(self, target: ExecutionTarget) -> None:
        self.target = target
        self.delete_requested = False

    async def create(self, *_: object, **__: object) -> ExecutionTarget:
        return self.target

    async def get(self, _target_id: uuid.UUID) -> ExecutionTarget | None:
        return self.target

    async def list(self, **_: object) -> list[ExecutionTarget]:
        return [self.target]

    async def request_delete(self, _target_id: uuid.UUID, _updated_by: uuid.UUID) -> ExecutionTarget:
        self.delete_requested = True
        return self.target

    async def finalize_delete(self, _target_id: uuid.UUID) -> None:
        self.delete_requested = True

    async def activate(self, _target_id: uuid.UUID, _updated_by: uuid.UUID) -> ExecutionTarget:
        return self.target

    async def update(self, _target_id: uuid.UUID, **_: object) -> ExecutionTarget:
        return self.target


@pytest.mark.asyncio
async def test_store_creates_target_with_audit_fields_and_owns_the_commit() -> None:
    """Removing the store commit would leave newly registered targets unpersisted."""
    store = ExecutionTargetStore("postgresql+asyncpg://localhost/syntara")
    session = _Session()
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]
    cluster_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    target = await store.create(
        cluster_id,
        "target-a",
        BackendType.VANILLA_K8S,
        "https://target.example",
        "secret",
        is_default=False,
        created_by=creator_id,
        labels={"region": "eu-west"},
    )

    assert target.cluster_id == cluster_id
    assert target.created_by == creator_id
    assert target.updated_by == creator_id
    assert target.labels == {"region": "eu-west"}
    assert target.api_key == ""
    assert session.added is not target
    assert session.added.api_key == "secret"  # type: ignore[union-attr]
    assert session.commits == 1
    await store.close()


@pytest.mark.asyncio
async def test_store_rejects_a_second_default_target_for_a_cluster() -> None:
    """Dropping the default lookup would permit duplicate protected targets."""
    existing_default = _target(is_default=True)
    store = ExecutionTargetStore("postgresql+asyncpg://localhost/syntara")
    session = _Session(result=_Result(existing_default))
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]

    with pytest.raises(DefaultExecutionTargetError):
        await store.create(
            existing_default.cluster_id,
            "target-b",
            BackendType.VANILLA_K8S,
            "https://target-b.example",
            "secret",
            is_default=True,
            created_by=uuid.uuid4(),
        )

    assert session.added is None
    assert session.commits == 0
    await store.close()


@pytest.mark.asyncio
async def test_store_rolls_back_when_target_creation_cannot_commit() -> None:
    """Removing rollback would retain a failed target transaction in the owned session."""
    store = ExecutionTargetStore("postgresql+asyncpg://localhost/syntara")
    session = _Session(fail_commit=True)
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match=_DATABASE_UNAVAILABLE):
        await store.create(
            uuid.uuid4(),
            "target-a",
            BackendType.VANILLA_K8S,
            "https://target.example",
            "secret",
            is_default=False,
            created_by=uuid.uuid4(),
        )

    assert session.rollbacks == 1
    await store.close()


@pytest.mark.asyncio
async def test_store_request_delete_disables_and_drains_non_default_target() -> None:
    """Skipping the state transition would allow deleted targets to receive work."""
    target = _target()
    store = ExecutionTargetStore("postgresql+asyncpg://localhost/syntara")
    session = _Session(result=_Result(target))
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]
    actor_id = uuid.uuid4()

    result = await store.request_delete(target.id, actor_id)

    assert result.status == TargetStatus.DRAINING
    assert result.enabled is False
    assert result.updated_by == actor_id
    assert session.commits == 1
    await store.close()


@pytest.mark.asyncio
async def test_store_updates_target_metadata_and_audit_fields_without_exposing_secret() -> None:
    """Target updates must be narrow and must preserve ownership invariants."""
    target = _target(is_default=True)
    original_cluster_id = target.cluster_id
    store = ExecutionTargetStore("postgresql+asyncpg://localhost/syntara")
    session = _Session(result=_Result(target))
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]
    actor_id = uuid.uuid4()

    result = await store.update(
        target.id,
        updated_by=actor_id,
        name="renamed-target",
        endpoint="https://updated.example",
        labels={"region": "eu-west"},
        status_message="updated",
    )

    assert result.name == "renamed-target"
    assert result.endpoint == "https://updated.example"
    assert result.labels == {"region": "eu-west"}
    assert result.status_message == "updated"
    assert result.cluster_id == original_cluster_id
    assert result.is_default is True
    assert result.api_key == ""
    assert result.updated_by == actor_id
    assert session.commits == 1
    await store.close()


@pytest.mark.asyncio
async def test_store_finalizes_a_default_target_during_cluster_deletion() -> None:
    """Default protection applies when deletion is requested, not finalized."""
    target = _target(is_default=True, status=TargetStatus.DRAINING)
    target.enabled = False
    store = ExecutionTargetStore("postgresql+asyncpg://localhost/syntara")
    session = _Session(result=_Result(target))
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]

    await store.finalize_delete(target.id)

    assert session.deleted is None
    await store.close()


@pytest.mark.asyncio
async def test_store_ignores_a_target_that_is_not_drained() -> None:
    """Finalization leaves a target alone when its state changed."""
    target = _target(status=TargetStatus.ACTIVE)
    store = ExecutionTargetStore("postgresql+asyncpg://localhost/syntara")
    session = _Session(result=_Result(target))
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]

    await store.finalize_delete(target.id)

    assert session.deleted is None
    await store.close()


@pytest.mark.asyncio
async def test_registry_rejects_deletion_of_the_protected_default_target() -> None:
    """Removing the registry guard would allow direct deletion of a default target."""
    target = _target(is_default=True)
    store = _Store(target)
    registry = ExecutionTargetRegistry(store)  # type: ignore[arg-type]

    with pytest.raises(DefaultExecutionTargetError):
        await registry.request_delete(target.id, uuid.uuid4())

    assert store.delete_requested is False


@pytest.mark.asyncio
async def test_registry_persists_target_drain_request() -> None:
    """Deletion persists DRAINING; the worker monitor owns finalization."""
    target = _target()
    store = _Store(target)
    registry = ExecutionTargetRegistry(store)  # type: ignore[arg-type]

    await registry.request_delete(target.id, uuid.uuid4())

    assert store.delete_requested is True


@pytest.mark.asyncio
async def test_registry_delegates_eligible_listing_without_a_database_session() -> None:
    """Passing a session into the registry would break the store ownership boundary."""
    target = _target(status=TargetStatus.ACTIVE)
    registry = ExecutionTargetRegistry(_Store(target))  # type: ignore[arg-type]

    assert await registry.list(cluster_id=target.cluster_id, eligible_only=True) == [target]


@pytest.mark.asyncio
async def test_registry_delegates_create_get_activate_and_update() -> None:
    target = _target()
    registry = ExecutionTargetRegistry(_Store(target))  # type: ignore[arg-type]

    assert (
        await registry.create(
            target.cluster_id,
            target.name,
            target.backend_type,
            target.endpoint,
            target.api_key,
            target.is_default,
            target.created_by,
        )
        is target
    )
    assert await registry.get(target.id) is target
    assert await registry.activate(target.id, uuid.uuid4()) is target
    assert await registry.update(target.id, updated_by=uuid.uuid4(), name="renamed") is target


@pytest.mark.asyncio
async def test_registry_rejects_deletion_of_an_unknown_target() -> None:
    class EmptyStore(_Store):
        async def get(self, _target_id: uuid.UUID) -> ExecutionTarget | None:
            return None

    registry = ExecutionTargetRegistry(EmptyStore(_target()))  # type: ignore[arg-type]

    with pytest.raises(ExecutionTargetNotFoundError):
        await registry.request_delete(uuid.uuid4(), uuid.uuid4())


def test_store_accepts_a_pool_for_its_owned_engine() -> None:
    """Callers need to select a pool that matches the store lifecycle."""
    store = ExecutionTargetStore("postgresql+asyncpg://localhost/syntara", poolclass=NullPool)

    assert store._engine is not None
    assert isinstance(store._engine.pool, NullPool)
