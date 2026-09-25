"""Execution Plane API endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 - Pydantic resolves model annotations at runtime.
from typing import TYPE_CHECKING, Annotated, Any

import structlog
from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlmodel import Field, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: TC002 - FastAPI resolves dependency annotations.

from execution_plane.models.execution_target import ExecutionTarget  # noqa: TC001 - Pydantic runtime model.
from execution_plane.models.work_item import WorkItemStatus  # noqa: TC001 - Pydantic runtime model.
from execution_plane.services import ExecutionTargetRegistry, WorkItemRegistry
from syntara.authz.dependencies import PermissionChecker
from syntara.core.config.base import get_settings
from syntara.core.database.session import get_db
from syntara.core.syntara_router import SyntaraRouter

logger = structlog.stdlib.get_logger(__name__)

if TYPE_CHECKING:
    from execution_plane.models.work_item import WorkItem

router = SyntaraRouter(prefix="/api/execution_plane/v1", tags=["Execution Plane"])

_perm_et_read = PermissionChecker("execution_target", "read")
_perm_wi_read = PermissionChecker("work_item", "read")
_perm_wi_create = PermissionChecker("work_item", "create")


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

    resources: list[WorkItemRead]
    next: str | None = None
    prev: str | None = None
    total: int | None = None


class WorkerTaskDefinition(SQLModel):
    """OCI image and JSONL invocation used for a cold-start worker."""

    image: str = Field(min_length=1, max_length=512)
    pod_command: list[str] | None = Field(default=None, min_length=1, max_length=32)
    command: list[str] = Field(min_length=1, max_length=32)
    input: dict[str, Any]
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    image_pull_policy: str = Field(default="IfNotPresent", regex="^(Always|IfNotPresent|Never)$")


class WorkItemSubmit(SQLModel):
    """Direct Task Executor submission request."""

    work_correlation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    activity_handle: str | None = None
    target_selector: dict[str, Any] = Field(default_factory=dict)
    task_definition: WorkerTaskDefinition


class WorkItemRead(SQLModel):
    """Public work-item representation that excludes execution inputs and task tokens."""

    id: uuid.UUID
    work_correlation_id: uuid.UUID
    status: WorkItemStatus
    execution_target_id: uuid.UUID | None = None
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    created_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    signaled_at: datetime | None = None


def get_execution_target_registry(db: Annotated[AsyncSession, Depends(get_db)]) -> ExecutionTargetRegistry:
    """Build the execution target registry for the current request."""
    return ExecutionTargetRegistry(db)


def get_work_item_registry(db: Annotated[AsyncSession, Depends(get_db)]) -> WorkItemRegistry:
    """Build the work item registry for the current request."""
    return WorkItemRegistry(db, get_settings().database_url.render_as_string(hide_password=False))


def _public_work_item(item: WorkItem) -> WorkItemRead:
    """Never return potentially secret HTTP headers, URLs, script code, or env vars."""
    visible_keys = {"target_selector", "execution_target_id", "workflow_node_type"}
    public_payload = {key: value for key, value in item.payload.items() if key in visible_keys}
    return WorkItemRead.model_validate(item, from_attributes=True).model_copy(update={"payload": public_payload})


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
    items = await registry.list(limit)
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
    resources = [_public_work_item(item) for item in items]
    return WorkItemListResponse(resources=resources)


@router.post(
    "/submit",
    operation_id="submit_execution_plane_work_item",
    summary="Submit a cold-start execution-plane work item",
    description="Queue a JSONL task for execution on a matching registered target.",
    dependencies=[Depends(_perm_wi_create)],
    status_code=202,
)
async def submit_work_item(
    request: WorkItemSubmit,
    registry: Annotated[WorkItemRegistry, Depends(get_work_item_registry)],
) -> WorkItemRead:
    """Persist a queued work item and wake the execution-plane worker."""
    payload = {
        "target_selector": request.target_selector,
        "task_definition": request.task_definition.model_dump(),
    }
    item = await registry.submit(
        activity_handle=request.activity_handle,
        work_correlation_id=request.work_correlation_id,
        payload=payload,
    )
    logger.info("Submitted execution-plane work item", work_item_id=str(item.id))
    return _public_work_item(item)
