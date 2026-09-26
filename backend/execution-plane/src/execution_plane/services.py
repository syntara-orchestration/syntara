"""Execution Plane service layer — read-only DB access behind the router."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import select

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

from execution_plane.models.work_item import WorkItem


class WorkItemRegistry:
    """Read dispatched work items from the database."""

    def __init__(self, db: AsyncSession) -> None:
        """Use the request-scoped database session."""
        self.db = db

    async def list(self, limit: int) -> list[WorkItem]:
        """Return up to limit work items."""
        result = await self.db.exec(select(WorkItem).limit(limit))
        return list(result.all())
