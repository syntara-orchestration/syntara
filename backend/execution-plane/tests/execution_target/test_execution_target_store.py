"""Additional unit tests for ExecutionTargetStore persistence branches."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Self

import pytest
from execution_plane.execution_target.execution_target_store import (
    ClusterNotAvailableError,
    DefaultExecutionTargetError,
    ExecutionTargetNotFoundError,
    ExecutionTargetStore,
    TargetNotActivatableError,
)
from execution_plane.models.cluster import Cluster, ClusterStatus
from execution_plane.models.execution_target import BackendType, ExecutionTarget, TargetStatus
from sqlalchemy.exc import IntegrityError

_DATABASE_UNAVAILABLE = "database unavailable"


def _target(*, is_default: bool = False, status: TargetStatus = TargetStatus.ACTIVE) -> ExecutionTarget:
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
        enabled=status is TargetStatus.ACTIVE,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_by=uuid.uuid4(),
        updated_at=now,
    )


def _cluster(*, status: ClusterStatus = ClusterStatus.REGISTERING) -> Cluster:
    now = datetime.now(UTC)
    return Cluster(
        id=uuid.uuid4(),
        name="cluster-a",
        endpoint="https://cluster.example",
        api_key="secret",
        status=status,
        enabled=status in (ClusterStatus.ACTIVE, ClusterStatus.REGISTERING),
        created_by=uuid.uuid4(),
        created_at=now,
        updated_by=uuid.uuid4(),
        updated_at=now,
    )


class _Result:
    def __init__(self, target: ExecutionTarget | None = None, targets: list[ExecutionTarget] | None = None) -> None:
        self.target = target
        self.targets = targets or ([] if target is None else [target])

    def scalar_one_or_none(self) -> ExecutionTarget | None:
        return self.target

    def scalars(self) -> Self:
        return self

    def all(self) -> list[ExecutionTarget]:
        return self.targets


class _ScalarResult:
    def __init__(self, value: uuid.UUID | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> uuid.UUID | None:
        return self.value


class _Session:
    def __init__(
        self,
        *,
        result: _Result | None = None,
        cluster: Cluster | None = None,
        fail_commit: bool = False,
        fail_integrity: bool = False,
    ) -> None:
        self.result = result or _Result()
        self.cluster = cluster or _cluster()
        self.fail_commit = fail_commit
        self.fail_integrity = fail_integrity
        self.deleted: ExecutionTarget | None = None
        self.added: ExecutionTarget | None = None
        self.rollbacks = 0
        self.executed: list[object] = []
        self.get_for_update: list[bool] = []
        self.work_result: _ScalarResult | None = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def add(self, target: ExecutionTarget) -> None:
        self.added = target

    async def get(self, model: object, _target_id: uuid.UUID, **_: object) -> ExecutionTarget | Cluster | None:
        self.get_for_update.append(bool(_.get("with_for_update", False)))
        if model is Cluster:
            return self.cluster
        return self.result.target

    async def execute(self, _statement: object) -> _Result:
        self.executed.append(_statement)
        if self.work_result is not None:
            return self.work_result  # type: ignore[return-value]
        return self.result

    async def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError(_DATABASE_UNAVAILABLE)
        if self.fail_integrity:
            statement = "insert"
            raise IntegrityError(statement, {}, RuntimeError("unique constraint violated"))

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def delete(self, target: ExecutionTarget) -> None:
        self.deleted = target


class _SessionFactory:
    def __init__(self, session: _Session) -> None:
        self.session = session

    def __call__(self) -> _Session:
        return self.session


def _store(session: _Session) -> ExecutionTargetStore:
    store = ExecutionTargetStore("postgresql+asyncpg://localhost/syntara")
    store._session_factory = _SessionFactory(session)  # type: ignore[assignment]
    return store


@pytest.mark.asyncio
async def test_get_redacts_credentials_or_returns_secret_when_requested() -> None:
    target = _target()
    store = _store(_Session(result=_Result(target)))

    redacted = await store.get(target.id)
    included = await store.get(target.id, include_secret=True)

    assert redacted is not None
    assert redacted.api_key == ""
    assert included is target
    await store.close()


@pytest.mark.asyncio
async def test_get_returns_none_for_an_unknown_target() -> None:
    store = _store(_Session())

    assert await store.get(uuid.uuid4()) is None
    await store.close()


@pytest.mark.asyncio
async def test_list_applies_cluster_status_eligibility_and_limit_filters() -> None:
    target = _target()
    store = _store(_Session(result=_Result(target, [target])))

    result = await store.list(
        cluster_id=target.cluster_id,
        eligible_only=True,
        status=TargetStatus.ACTIVE,
        limit=1,
    )

    assert len(result) == 1
    assert result[0].api_key == ""
    await store.close()


@pytest.mark.asyncio
async def test_request_delete_rejects_missing_and_default_targets() -> None:
    missing_store = _store(_Session())
    with pytest.raises(ExecutionTargetNotFoundError):
        await missing_store.request_delete(uuid.uuid4(), uuid.uuid4())
    await missing_store.close()

    default = _target(is_default=True)
    default_store = _store(_Session(result=_Result(default)))
    with pytest.raises(DefaultExecutionTargetError):
        await default_store.request_delete(default.id, uuid.uuid4())
    await default_store.close()


@pytest.mark.asyncio
async def test_request_delete_locks_the_target_before_draining() -> None:
    target = _target()
    session = _Session(result=_Result(target))
    store = _store(session)

    await store.request_delete(target.id, uuid.uuid4())

    assert session.get_for_update == [True]
    await store.close()


@pytest.mark.asyncio
async def test_activate_updates_target_state_and_rolls_back_when_target_is_missing() -> None:
    target = _target(status=TargetStatus.REGISTERING)
    store = _store(_Session(result=_Result(target)))

    result = await store.activate(target.id, uuid.uuid4())
    assert result.status is TargetStatus.ACTIVE
    assert result.enabled is True

    missing_session = _Session()
    missing_store = _store(missing_session)
    with pytest.raises(ExecutionTargetNotFoundError):
        await missing_store.activate(uuid.uuid4(), uuid.uuid4())
    assert missing_session.rollbacks == 1
    await store.close()
    await missing_store.close()


@pytest.mark.asyncio
async def test_create_rejects_a_cluster_that_is_draining() -> None:
    target = _target()
    store = _store(_Session(result=_Result(), cluster=_cluster(status=ClusterStatus.DRAINING)))

    with pytest.raises(ClusterNotAvailableError):
        await store.create(
            target.cluster_id,
            target.name,
            target.backend_type,
            target.endpoint,
            target.api_key,
            is_default=False,
            created_by=uuid.uuid4(),
        )

    await store.close()


@pytest.mark.asyncio
async def test_create_allows_a_new_target_on_an_active_cluster() -> None:
    target = _target()
    session = _Session(cluster=_cluster(status=ClusterStatus.ACTIVE))
    store = _store(session)

    result = await store.create(
        target.cluster_id,
        target.name,
        target.backend_type,
        target.endpoint,
        target.api_key,
        is_default=False,
        created_by=uuid.uuid4(),
    )

    assert result.api_key == ""
    assert session.added is not None
    await store.close()


@pytest.mark.asyncio
async def test_create_rejects_a_missing_cluster() -> None:
    class MissingClusterSession(_Session):
        async def get(self, model: object, _target_id: uuid.UUID, **kwargs: object) -> ExecutionTarget | Cluster | None:
            if model is Cluster:
                return None
            return await super().get(model, _target_id, **kwargs)

    target = _target()
    store = _store(MissingClusterSession())

    with pytest.raises(ClusterNotAvailableError):
        await store.create(
            target.cluster_id,
            target.name,
            target.backend_type,
            target.endpoint,
            target.api_key,
            is_default=False,
            created_by=uuid.uuid4(),
        )

    await store.close()


@pytest.mark.asyncio
async def test_create_rejects_an_enabled_cluster_in_another_state() -> None:
    cluster = _cluster(status=ClusterStatus.ERROR)
    cluster.enabled = True
    target = _target()
    store = _store(_Session(cluster=cluster))

    with pytest.raises(ClusterNotAvailableError):
        await store.create(
            target.cluster_id,
            target.name,
            target.backend_type,
            target.endpoint,
            target.api_key,
            is_default=False,
            created_by=uuid.uuid4(),
        )

    await store.close()


@pytest.mark.asyncio
async def test_concurrent_default_creation_is_translated_to_a_domain_error() -> None:
    target = _target(is_default=True)
    store = _store(_Session(fail_integrity=True))

    with pytest.raises(DefaultExecutionTargetError):
        await store.create(
            target.cluster_id,
            target.name,
            target.backend_type,
            target.endpoint,
            target.api_key,
            is_default=True,
            created_by=uuid.uuid4(),
        )

    await store.close()


@pytest.mark.asyncio
async def test_non_default_integrity_errors_are_preserved() -> None:
    target = _target()
    store = _store(_Session(fail_integrity=True))

    with pytest.raises(IntegrityError):
        await store.create(
            target.cluster_id,
            target.name,
            target.backend_type,
            target.endpoint,
            target.api_key,
            is_default=False,
            created_by=uuid.uuid4(),
        )

    await store.close()


@pytest.mark.asyncio
async def test_activate_rejects_a_target_that_is_already_draining() -> None:
    target = _target(status=TargetStatus.DRAINING)
    store = _store(_Session(result=_Result(target)))

    with pytest.raises(TargetNotActivatableError):
        await store.activate(target.id, uuid.uuid4())

    assert target.status is TargetStatus.DRAINING
    await store.close()


@pytest.mark.asyncio
async def test_update_can_replace_api_key_and_rejects_missing_target() -> None:
    target = _target()
    store = _store(_Session(result=_Result(target)))

    result = await store.update(target.id, updated_by=uuid.uuid4(), api_key="new-secret")

    assert result.api_key == ""
    assert target.api_key == "new-secret"

    missing_session = _Session()
    missing_store = _store(missing_session)
    with pytest.raises(ExecutionTargetNotFoundError):
        await missing_store.update(uuid.uuid4(), updated_by=uuid.uuid4())
    assert missing_session.rollbacks == 1
    await store.close()
    await missing_store.close()


@pytest.mark.asyncio
async def test_mark_failed_records_failure_and_rejects_missing_target() -> None:
    target = _target(status=TargetStatus.DRAINING)
    store = _store(_Session(result=_Result(target)))

    result = await store.mark_failed(target.id, uuid.uuid4())

    assert result.status is TargetStatus.FAILED
    assert result.enabled is False
    assert result.status_message == "target drain failed"

    missing_session = _Session()
    missing_store = _store(missing_session)
    with pytest.raises(ExecutionTargetNotFoundError):
        await missing_store.mark_failed(uuid.uuid4(), uuid.uuid4())
    assert missing_session.rollbacks == 1
    await store.close()
    await missing_store.close()


@pytest.mark.asyncio
async def test_finalize_delete_allows_a_drained_default_target() -> None:
    target = _target(is_default=True, status=TargetStatus.DRAINING)
    target.enabled = False
    session = _Session(result=_Result(target))
    session.work_result = _ScalarResult(None)
    store = _store(session)

    await store.finalize_delete(target.id)

    assert session.deleted is target
    assert session.executed
    await store.close()


@pytest.mark.asyncio
async def test_finalize_delete_ignores_a_missing_target() -> None:
    session = _Session()
    store = _store(session)

    await store.finalize_delete(uuid.uuid4())

    assert session.rollbacks == 0
    await store.close()


@pytest.mark.asyncio
async def test_finalize_delete_rolls_back_when_deletion_commit_fails() -> None:
    target = _target(status=TargetStatus.DRAINING)
    target.enabled = False
    session = _Session(result=_Result(target), fail_commit=True)
    session.work_result = _ScalarResult(None)
    store = _store(session)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await store.finalize_delete(target.id)

    assert session.rollbacks == 1
    await store.close()


@pytest.mark.asyncio
async def test_finalize_delete_rechecks_for_active_work_before_deleting_target() -> None:
    target = _target(status=TargetStatus.DRAINING)
    target.enabled = False
    session = _Session(result=_Result(target))
    session.work_result = _ScalarResult(uuid.uuid4())
    store = _store(session)

    await store.finalize_delete(target.id)

    assert session.deleted is None
    await store.close()
