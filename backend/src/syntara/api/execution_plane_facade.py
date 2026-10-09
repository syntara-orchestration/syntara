"""Execution Plane read proxy: AO-authorized endpoints that front the EP service."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — Pydantic resolves model annotations at runtime
from typing import Annotated, Literal
from uuid import UUID  # noqa: TC003 — Pydantic resolves model annotations at runtime

import structlog
from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from syntara.authz.dependencies import ProjectScopeFilter
from syntara.authz.engine import AllowedProjectsResult  # noqa: TC001 — FastAPI resolves dependency annotations
from syntara.core.syntara_router import SyntaraRouter
from syntara.execution_plane.client import ExecutionPlaneHttpClient, ExecutionPlaneUnavailableError

logger = structlog.stdlib.get_logger(__name__)

router = SyntaraRouter(prefix="/api/execution_plane/v1", tags=["Execution Plane"])

_target_scope = ProjectScopeFilter("execution_target", "read")
_work_item_scope = ProjectScopeFilter("work_item", "read")


class ExecutionTargetListResponse(BaseModel):
    """Paginated list response for ExecutionTarget."""

    resources: list[ExecutionTargetFacadeRead]
    next: str | None = None
    prev: str | None = None
    total: int | None = None


class WorkItemListResponse(BaseModel):
    """Paginated list response for WorkItem."""

    resources: list[WorkItemFacadeRead]
    next: str | None = None
    prev: str | None = None
    total: int | None = None


class KubernetesPlacement(BaseModel):
    """Kubernetes scheduling metadata returned by the Execution Plane."""

    type: Literal["kubernetes"]
    namespace: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
    node_selectors: list[str] = Field(default_factory=list)
    tolerations: list[str] = Field(default_factory=list)


class RHELPlacement(BaseModel):
    """RHEL placement marker returned by the Execution Plane."""

    type: Literal["rhel"]


class ExecutionTargetFacadeRead(BaseModel):
    """Safe target fields available to AO's authorized management API."""

    id: UUID
    cluster_id: UUID
    name: str
    backend_type: str
    endpoint: str
    placement: Annotated[KubernetesPlacement | RHELPlacement, Field(discriminator="type")]
    status: str
    enabled: bool
    is_default: bool
    status_message: str | None = None
    labels: dict[str, str]
    created_at: datetime
    last_ran_at: datetime | None = None


class WorkItemFacadeRead(BaseModel):
    """Safe work state; internal tokens and storage metadata stay private."""

    id: UUID
    status: str
    result: dict[str, object] | None = None
    created_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None


@router.get(
    "/execution_targets",
    operation_id="list_execution_targets",
    summary="List execution targets",
    description="Retrieve registered execution targets.",
)
async def list_execution_targets(
    allowed_projects: Annotated[AllowedProjectsResult, Depends(_target_scope)],
    limit: int = Query(default=20, ge=1, le=100),
) -> ExecutionTargetListResponse:
    """Read registered execution targets from EP after AO permission checks."""
    try:
        async with ExecutionPlaneHttpClient() as client:
            items = await _list_ep_resources(
                client,
                operation="execution_targets",
                allowed_projects=allowed_projects,
                limit=limit,
            )
    except ExecutionPlaneUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution Plane unavailable",
        ) from exc
    logger.info("Listed execution targets", count=len(items))
    return ExecutionTargetListResponse(resources=[ExecutionTargetFacadeRead.model_validate(item) for item in items])


@router.get(
    "/work_items",
    operation_id="list_work_items",
    summary="List work items",
    description="Retrieve work items.",
)
async def list_work_items(
    allowed_projects: Annotated[AllowedProjectsResult, Depends(_work_item_scope)],
    limit: int = Query(default=20, ge=1, le=100),
) -> WorkItemListResponse:
    """Read work-item state from EP after AO permission checks."""
    try:
        async with ExecutionPlaneHttpClient() as client:
            items = await _list_ep_resources(
                client,
                operation="work_items",
                allowed_projects=allowed_projects,
                limit=limit,
            )
    except ExecutionPlaneUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution Plane unavailable",
        ) from exc
    logger.info("Listed work items", count=len(items))
    return WorkItemListResponse(resources=[WorkItemFacadeRead.model_validate(item) for item in items])


async def _list_ep_resources(
    client: ExecutionPlaneHttpClient,
    *,
    operation: Literal["execution_targets", "work_items"],
    allowed_projects: AllowedProjectsResult,
    limit: int,
) -> list[dict[str, object]]:
    """List EP resources after AO permission checks. EP has no project scope."""
    if not allowed_projects.all_projects and not allowed_projects.project_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No project-scoped access to EP resources")
    if operation == "work_items":
        return await client.list_work_items(limit=limit)
    return await client.list_execution_targets(limit=limit)
