"""Execution Plane API endpoints."""

from typing import Annotated

import structlog
from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.dependencies import PermissionChecker
from syntara.core.database.session import get_db
from syntara.core.syntara_router import SyntaraRouter

from execution_plane.models.execution_target import ExecutionTarget
from execution_plane.models.work_item import WorkItem

logger = structlog.stdlib.get_logger(__name__)

router = SyntaraRouter(prefix="/api/execution-plane/v1", tags=["Execution Plane"])

_perm_et_read = PermissionChecker("execution_target", "read")
_perm_wi_read = PermissionChecker("work_item", "read")


class ExecutionTargetListResponse(BaseModel):
    """Paginated list response for ExecutionTarget."""

    model_config = ConfigDict(from_attributes=True)

    resources: list[ExecutionTarget]
    next: str | None = None
    prev: str | None = None
    total: int | None = None


class WorkItemListResponse(BaseModel):
    """Paginated list response for WorkItem."""

    model_config = ConfigDict(from_attributes=True)

    resources: list[WorkItem]
    next: str | None = None
    prev: str | None = None
    total: int | None = None


@router.get(
    "/execution-targets",
    operation_id="list_execution_targets",
    summary="List execution targets",
    description="Retrieve registered execution targets.",
    dependencies=[Depends(_perm_et_read)],
)
async def list_execution_targets(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
) -> ExecutionTargetListResponse:
    """List execution targets."""
    result = await db.exec(select(ExecutionTarget).limit(limit))
    items = result.all()
    logger.info("Listed execution targets", count=len(items))
    return ExecutionTargetListResponse(resources=list(items))


@router.get(
    "/work-items",
    operation_id="list_work_items",
    summary="List work items",
    description="Retrieve work items.",
    dependencies=[Depends(_perm_wi_read)],
)
async def list_work_items(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
) -> WorkItemListResponse:
    """List work items."""
    result = await db.exec(select(WorkItem).limit(limit))
    items = result.all()
    logger.info("Listed work items", count=len(items))
    return WorkItemListResponse(resources=list(items))
