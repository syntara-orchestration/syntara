"""Persistence operations for execution-target lifecycle transitions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col

from execution_plane.models.cluster import Cluster, ClusterStatus
from execution_plane.models.execution_target import BackendType, ExecutionTarget, TargetStatus
from execution_plane.models.work_item import WorkItem, WorkItemStatus
from execution_plane.store_base import StoreBase

if TYPE_CHECKING:
    import uuid
    from typing import Any


class ExecutionTargetNotFoundError(LookupError):
    """Raised when a lifecycle transition targets an unknown execution target."""

    def __init__(self, target_id: uuid.UUID) -> None:
        """Identify the missing target."""
        super().__init__(f"Execution target {target_id} does not exist")


class DefaultExecutionTargetError(ValueError):
    """Raised when an operation would violate default-target protection."""


class TargetNotActivatableError(ValueError):
    """Raised when a target is no longer in its registration state."""


class ClusterNotAvailableError(ValueError):
    """Raised when a target is created for a Cluster that cannot accept targets."""


class ExecutionTargetStore(StoreBase):
    """Persist execution targets and own their database resources."""

    @staticmethod
    def _can_add_execution_target(cluster: Cluster | None) -> bool:
        """Return whether a Cluster can accept another target."""
        if cluster is None:
            return False
        if not cluster.enabled:
            return False
        return cluster.status in [ClusterStatus.ACTIVE, ClusterStatus.REGISTERING]

    async def create(
        self,
        cluster_id: uuid.UUID,
        name: str,
        backend_type: BackendType,
        endpoint: str,
        api_key: str,
        is_default: bool,  # noqa: FBT001
        created_by: uuid.UUID,
        labels: dict[str, Any] | None = None,
    ) -> ExecutionTarget:
        """Create a target, rejecting a second default in the same cluster."""
        now = datetime.now(UTC)
        target = ExecutionTarget(
            cluster_id=cluster_id,
            name=name,
            backend_type=backend_type,
            endpoint=endpoint,
            api_key=api_key,
            is_default=is_default,
            labels=labels or {},
            created_by=created_by,
            created_at=now,
            updated_by=created_by,
            updated_at=now,
        )

        async with self._session_context() as session:
            try:
                cluster = await session.get(Cluster, cluster_id, with_for_update=True)
                if not self._can_add_execution_target(cluster):
                    raise ClusterNotAvailableError(cluster_id)  # noqa: TRY301
                if is_default:
                    result = await session.execute(
                        select(ExecutionTarget)
                        .where(col(ExecutionTarget.cluster_id) == cluster_id)
                        .where(col(ExecutionTarget.is_default).is_(True))
                    )
                    if result.scalar_one_or_none() is not None:
                        raise DefaultExecutionTargetError  # noqa: TRY301
                session.add(target)
                await session.commit()
                return self._without_secret(target)
            except IntegrityError as exc:
                await session.rollback()
                if is_default:
                    raise DefaultExecutionTargetError from exc
                raise
            except Exception:
                await session.rollback()
                raise

    async def get(self, target_id: uuid.UUID, *, include_secret: bool = False) -> ExecutionTarget | None:
        """Return a target by ID, redacting its credential by default."""
        async with self._session_context() as session:
            target = await session.get(ExecutionTarget, target_id)
            return target if include_secret or target is None else self._without_secret(target)

    async def list(
        self,
        cluster_id: uuid.UUID | None = None,
        eligible_only: bool = False,  # noqa: FBT001, FBT002
        status: TargetStatus | None = None,
        limit: int | None = None,
    ) -> list[ExecutionTarget]:
        """List targets, optionally restricting results to work-eligible targets."""
        statement = select(ExecutionTarget)
        if cluster_id is not None:
            statement = statement.where(col(ExecutionTarget.cluster_id) == cluster_id)
        if status is not None:
            statement = statement.where(col(ExecutionTarget.status) == status)
        if eligible_only:
            statement = (
                statement.join(Cluster)
                .where(col(ExecutionTarget.enabled).is_(True))
                .where(col(ExecutionTarget.status) == TargetStatus.ACTIVE)
                .where(col(Cluster.enabled).is_(True))
                .where(col(Cluster.status) == ClusterStatus.ACTIVE)
            )
        if limit is not None:
            statement = statement.limit(limit)
        async with self._session_context() as session:
            result = await session.execute(statement)
            targets = list(result.scalars().all())
            return [self._without_secret(target) for target in targets]

    async def request_delete(self, target_id: uuid.UUID, updated_by: uuid.UUID) -> ExecutionTarget:
        """Disable a non-default target and move it to DRAINING."""
        async with self._session_context() as session:
            try:
                target = await session.get(ExecutionTarget, target_id, with_for_update=True)
                if target is None:
                    raise ExecutionTargetNotFoundError(target_id)  # noqa: TRY301
                if target.is_default:
                    raise DefaultExecutionTargetError  # noqa: TRY301
                target.enabled = False
                target.status = TargetStatus.DRAINING
                target.updated_by = updated_by
                target.updated_at = datetime.now(UTC)
                await session.commit()
                return self._without_secret(target)
            except Exception:
                await session.rollback()
                raise

    async def activate(self, target_id: uuid.UUID, updated_by: uuid.UUID) -> ExecutionTarget:
        """Mark a successfully registered target eligible for work."""
        async with self._session_context() as session:
            try:
                target = await session.get(ExecutionTarget, target_id, with_for_update=True)
                if target is None:
                    raise ExecutionTargetNotFoundError(target_id)  # noqa: TRY301
                if target.status is not TargetStatus.REGISTERING:
                    raise TargetNotActivatableError(target_id)  # noqa: TRY301
                target.enabled = True
                target.status = TargetStatus.ACTIVE
                target.updated_by = updated_by
                target.updated_at = datetime.now(UTC)
                await session.commit()
                return self._without_secret(target)
            except Exception:
                await session.rollback()
                raise

    async def update(
        self,
        target_id: uuid.UUID,
        *,
        updated_by: uuid.UUID,
        name: str | None = None,
        endpoint: str | None = None,
        labels: dict[str, Any] | None = None,
        status_message: str | None = None,
        api_key: str | None = None,
    ) -> ExecutionTarget:
        """Update mutable target metadata without changing ownership or default status."""
        async with self._session_context() as session:
            try:
                target = await session.get(ExecutionTarget, target_id)
                if target is None:
                    raise ExecutionTargetNotFoundError(target_id)  # noqa: TRY301
                if name is not None:
                    target.name = name
                if endpoint is not None:
                    target.endpoint = endpoint
                if labels is not None:
                    target.labels = labels
                if status_message is not None:
                    target.status_message = status_message
                if api_key is not None:
                    target.api_key = api_key
                target.updated_by = updated_by
                target.updated_at = datetime.now(UTC)
                await session.commit()
                return self._without_secret(target)
            except Exception:
                await session.rollback()
                raise

    async def mark_failed(self, target_id: uuid.UUID, updated_by: uuid.UUID) -> ExecutionTarget:
        """Record an irrecoverable drain failure without exposing backend details."""
        async with self._session_context() as session:
            try:
                target = await session.get(ExecutionTarget, target_id)
                if target is None:
                    raise ExecutionTargetNotFoundError(target_id)  # noqa: TRY301
                target.enabled = False
                target.status = TargetStatus.FAILED
                target.status_message = "target drain failed"
                target.updated_by = updated_by
                target.updated_at = datetime.now(UTC)
                await session.commit()
                return self._without_secret(target)
            except Exception:
                await session.rollback()
                raise

    async def finalize_delete(self, target_id: uuid.UUID) -> None:
        """Physically delete a drained target when finalization is safe."""
        async with self._session_context() as session:
            try:
                target = await session.get(ExecutionTarget, target_id, with_for_update=True)
                if target is None:
                    return
                if target.enabled or target.status != TargetStatus.DRAINING:
                    return
                active_work = await session.execute(
                    select(col(WorkItem.id))
                    .where(col(WorkItem.execution_target_id) == target_id)
                    .where(col(WorkItem.status).in_([WorkItemStatus.CLAIMED, WorkItemStatus.DISPATCHED]))
                    .limit(1)
                )
                if active_work.scalar_one_or_none() is not None:
                    return
                await session.execute(
                    update(WorkItem)
                    .where(col(WorkItem.execution_target_id) == target_id)
                    .values(execution_target_id=None)
                )
                await session.delete(target)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @staticmethod
    def _without_secret(target: ExecutionTarget) -> ExecutionTarget:
        """Return a detached target representation without its API credential."""
        return target.model_copy(update={"api_key": ""})
