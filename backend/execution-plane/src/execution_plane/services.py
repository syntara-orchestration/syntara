"""Execution Plane service layer — read-only DB access behind the router."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlmodel import col, select

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

from execution_plane.models.execution_target import ExecutionTarget, TargetStatus
from execution_plane.models.work_item import WorkItem
from execution_plane.work_store import WorkStore


class ExecutionTargetRegistry:
    """Read registered execution targets from the database."""

    def __init__(self, db: AsyncSession) -> None:
        """Use the request-scoped database session."""
        self.db = db

    async def list(self, limit: int) -> list[ExecutionTarget]:
        """Return up to limit registered execution targets."""
        result = await self.db.execute(select(ExecutionTarget).limit(limit))
        return list(result.scalars().all())

    async def find_matching(self, selector: dict[str, Any]) -> ExecutionTarget | None:
        """Return the first active target whose labels contain the selector."""
        result = await self.db.execute(
            select(ExecutionTarget)
            .where(col(ExecutionTarget.enabled).is_(True))
            .where(col(ExecutionTarget.status) == TargetStatus.ACTIVE)
            .order_by(col(ExecutionTarget.name))
        )
        for target in result.scalars().all():
            if all(target.labels.get(key) == value for key, value in selector.items()):
                return target
        return None

    async def find_active_by_id(self, target_id: uuid.UUID) -> ExecutionTarget | None:
        """Resolve the target selected by a Syntara OpenShift integration."""
        result = await self.db.execute(
            select(ExecutionTarget).where(
                col(ExecutionTarget.id) == target_id,
                col(ExecutionTarget.enabled).is_(True),
                col(ExecutionTarget.status) == TargetStatus.ACTIVE,
            )
        )
        return result.scalar_one_or_none()


class WorkItemRegistry:
    """Read dispatched work items from the database."""

    def __init__(self, db: AsyncSession, database_url: str) -> None:
        """Use the request-scoped session for reads and a WorkStore for writes."""
        self.db = db
        self.database_url = database_url

    async def list(self, limit: int) -> list[WorkItem]:
        """Return up to limit work items."""
        result = await self.db.execute(select(WorkItem).limit(limit))
        return list(result.scalars().all())

    async def submit(
        self,
        *,
        activity_handle: str | None,
        work_correlation_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> WorkItem:
        """Queue a work item through the lifecycle-owning store."""
        async with WorkStore(self.database_url) as store:
            return await store.dispatch(
                activity_handle=activity_handle,
                work_correlation_id=work_correlation_id,
                payload=payload,
            )
