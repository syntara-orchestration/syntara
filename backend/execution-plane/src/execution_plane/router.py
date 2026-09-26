"""Execution Plane API endpoints."""

from typing import Annotated

import structlog
from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlmodel.ext.asyncio.session import AsyncSession

from execution_plane.cluster.cluster_registry import ClusterRegistry, NoopDiscoveryMechanism
from execution_plane.cluster.cluster_store import ClusterStore
from execution_plane.execution_target.execution_target_registry import ExecutionTargetRegistry
from execution_plane.execution_target.execution_target_store import ExecutionTargetStore
from execution_plane.models.execution_target import ExecutionTarget
from execution_plane.models.work_item import WorkItem
from execution_plane.services import WorkItemRegistry
from syntara.authz.dependencies import PermissionChecker
from syntara.core.database.session import get_db
from syntara.core.syntara_router import SyntaraRouter

logger = structlog.stdlib.get_logger(__name__)

router = SyntaraRouter(prefix="/api/execution_plane/v1", tags=["Execution Plane"])

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


def get_execution_target_registry(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExecutionTargetRegistry:
    """Build a request-scoped target registry using Syntara's DB session."""
    return ExecutionTargetRegistry(ExecutionTargetStore.from_session(db))


def get_cluster_registry(
    target_registry: Annotated[ExecutionTargetRegistry, Depends(get_execution_target_registry)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClusterRegistry:
    """Build a request-scoped Cluster registry using the target registry."""
    return ClusterRegistry(
        ClusterStore.from_session(db),
        target_registry,
        NoopDiscoveryMechanism(),
    )


def get_work_item_registry(db: Annotated[AsyncSession, Depends(get_db)]) -> WorkItemRegistry:
    """Build the work item registry for the current request."""
    return WorkItemRegistry(db)


@router.get(
    "/execution_targets",
    operation_id="list_execution_targets",
    summary="List execution targets",
    description="Retrieve registered execution targets.",
    dependencies=[Depends(_perm_et_read)],
)
async def list_execution_targets(
    registry: Annotated[ExecutionTargetRegistry, Depends(get_execution_target_registry)],
    limit: int = Query(default=20, ge=1, le=100),
) -> ExecutionTargetListResponse:
    """List registered execution targets."""
    items = await registry.list(limit=limit)
    logger.info("Listed execution targets", count=len(items))
    return ExecutionTargetListResponse(resources=items)


@router.get(
    "/work_items",
    operation_id="list_work_items",
    summary="List work items",
    description="Retrieve work items.",
    dependencies=[Depends(_perm_wi_read)],
)
async def list_work_items(
    registry: Annotated[WorkItemRegistry, Depends(get_work_item_registry)],
    limit: int = Query(default=20, ge=1, le=100),
) -> WorkItemListResponse:
    """List dispatched work items."""
    items = await registry.list(limit)
    logger.info("Listed work items", count=len(items))
    return WorkItemListResponse(resources=items)
