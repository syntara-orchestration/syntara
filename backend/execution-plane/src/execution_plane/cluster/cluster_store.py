"""Persistence operations for Cluster lifecycle transitions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlmodel import col

from execution_plane.models.cluster import Cluster, ClusterStatus
from execution_plane.models.execution_target import ExecutionTarget, TargetStatus
from execution_plane.store_base import StoreBase

if TYPE_CHECKING:
    import uuid
    from typing import Any


class ClusterNotFoundError(LookupError):
    """Raised when a lifecycle operation targets an unknown Cluster."""

    def __init__(self, cluster_id: uuid.UUID) -> None:
        """Identify the missing Cluster."""
        super().__init__(f"Cluster {cluster_id} does not exist")


class ClusterStore(StoreBase):
    """Persist Cluster state and own the database resources it uses."""

    @staticmethod
    def _can_record_discovery_state(cluster: Cluster) -> bool:
        """Return whether a Cluster can have its discovery state set."""
        if not cluster.enabled:
            return False
        return cluster.status is ClusterStatus.REGISTERING

    async def create(
        self,
        name: str,
        endpoint: str,
        api_key: str,
        created_by: uuid.UUID,
        labels: dict[str, Any] | None = None,
    ) -> Cluster:
        """Persist a new Cluster in REGISTERING state."""
        now = datetime.now(UTC)
        cluster = Cluster(
            name=name,
            endpoint=endpoint,
            api_key=api_key,
            labels=labels or {},
            status=ClusterStatus.REGISTERING,
            created_by=created_by,
            created_at=now,
            updated_by=created_by,
            updated_at=now,
        )
        async with self._session_context() as session:
            try:
                session.add(cluster)
                await session.commit()
                return self._without_secret(cluster)
            except Exception:
                await session.rollback()
                raise

    async def get(self, cluster_id: uuid.UUID) -> Cluster | None:
        """Return a Cluster without its API credential."""
        async with self._session_context() as session:
            cluster = await session.get(Cluster, cluster_id)
            return None if cluster is None else self._without_secret(cluster)

    async def list(self, *, status: ClusterStatus | None = None, enabled: bool | None = None) -> list[Cluster]:
        """List Clusters for administrative or recovery workflows."""
        statement = select(Cluster)
        if status is not None:
            statement = statement.where(col(Cluster.status) == status)
        if enabled is not None:
            statement = statement.where(col(Cluster.enabled).is_(enabled))
        async with self._session_context() as session:
            result = await session.execute(statement)
            return [self._without_secret(cluster) for cluster in result.scalars().all()]

    async def record_discovery_state(
        self,
        cluster_id: uuid.UUID,
        status: ClusterStatus,
        status_message: str | None,
        updated_by: uuid.UUID,
    ) -> Cluster:
        """Persist registration/discovery state on the existing Cluster."""
        async with self._session_context() as session:
            try:
                cluster = await session.get(Cluster, cluster_id, with_for_update=True)
                if cluster is None:
                    raise ClusterNotFoundError(cluster_id)  # noqa: TRY301
                if not self._can_record_discovery_state(cluster):
                    return self._without_secret(cluster)
                cluster.status = status
                cluster.enabled = status is not ClusterStatus.ERROR
                cluster.status_message = status_message
                cluster.updated_by = updated_by
                cluster.updated_at = datetime.now(UTC)
                await session.commit()
                return self._without_secret(cluster)
            except Exception:
                await session.rollback()
                raise

    async def mark_drain_failed(
        self,
        cluster_id: uuid.UUID,
        status_message: str,
        updated_by: uuid.UUID,
    ) -> Cluster:
        """Persist a failed drain on a Cluster that is no longer available."""
        async with self._session_context() as session:
            try:
                cluster = await session.get(Cluster, cluster_id, with_for_update=True)
                if cluster is None:
                    raise ClusterNotFoundError(cluster_id)  # noqa: TRY301
                cluster.enabled = False
                cluster.status = ClusterStatus.ERROR
                cluster.status_message = status_message
                cluster.updated_by = updated_by
                cluster.updated_at = datetime.now(UTC)
                await session.commit()
                return self._without_secret(cluster)
            except Exception:
                await session.rollback()
                raise

    async def request_delete(self, cluster_id: uuid.UUID, updated_by: uuid.UUID) -> Cluster:
        """Disable a Cluster and all targets before asynchronous draining."""
        async with self._session_context() as session:
            try:
                cluster = await session.get(Cluster, cluster_id, with_for_update=True)
                if cluster is None:
                    raise ClusterNotFoundError(cluster_id)  # noqa: TRY301
                now = datetime.now(UTC)
                cluster.enabled = False
                cluster.status = ClusterStatus.DRAINING
                cluster.updated_by = updated_by
                cluster.updated_at = now
                result = await session.execute(
                    select(ExecutionTarget).where(col(ExecutionTarget.cluster_id) == cluster_id)
                )
                for target in result.scalars().all():
                    target.enabled = False
                    target.status = TargetStatus.DRAINING
                    target.updated_by = updated_by
                    target.updated_at = now
                await session.commit()
                return self._without_secret(cluster)
            except Exception:
                await session.rollback()
                raise

    async def finalize_delete(self, cluster_id: uuid.UUID) -> None:
        """Delete a Cluster when its persisted state makes finalization safe."""
        async with self._session_context() as session:
            try:
                cluster = await session.get(Cluster, cluster_id, with_for_update=True)
                if cluster is None:
                    return
                if cluster.enabled or cluster.status is not ClusterStatus.DRAINING:
                    return
                result = await session.execute(
                    select(ExecutionTarget).where(col(ExecutionTarget.cluster_id) == cluster_id)
                )
                if result.scalars().all():
                    return
                await session.delete(cluster)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @staticmethod
    def _without_secret(cluster: Cluster) -> Cluster:
        return cluster.model_copy(update={"api_key": ""})
