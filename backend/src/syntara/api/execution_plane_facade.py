"""Execution Plane API endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime  # noqa: TC003 — Pydantic resolves model annotations at runtime
from typing import Annotated, Literal
from uuid import UUID  # noqa: TC003 — Pydantic resolves model annotations at runtime

import structlog
from fastapi import Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from syntara.authz.dependencies import ProjectScopeFilter
from syntara.authz.engine import AllowedProjectsResult  # noqa: TC001 — FastAPI resolves dependency annotations
from syntara.core.config.base import get_settings
from syntara.core.syntara_router import NO_PERMISSION, SyntaraRouter
from syntara.execution_plane.bridge import (
    CompletionBindingNotFoundError,
    CompletionEventConflictError,
    persist_completion_event,
)
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


class ExecutionTargetFacadeRead(BaseModel):
    """Safe target fields available to AO's authorized management API."""

    id: UUID
    cluster_id: UUID
    name: str
    backend_type: str
    endpoint: str
    namespace: str
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
    project_id: UUID
    request_id: str
    work_correlation_id: UUID
    status: str
    result: dict[str, object] | None = None
    created_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None


class EPCompletionEvent(BaseModel):
    """Authenticated result event delivered by the independent EP service."""

    event_id: UUID
    event_schema_version: Literal[1]
    client_id: str
    project_id: UUID
    work_id: UUID
    request_id: str
    state_revision: int
    status: Literal["completed", "failed", "cancelled"]
    result: dict[str, object]
    completed_at: datetime


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
            items = await _list_in_authorized_projects(
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
            items = await _list_in_authorized_projects(
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


async def _list_in_authorized_projects(
    client: ExecutionPlaneHttpClient,
    *,
    operation: Literal["execution_targets", "work_items"],
    allowed_projects: AllowedProjectsResult,
    limit: int,
) -> list[dict[str, object]]:
    """List EP resources only within AO's resolved project access scope."""
    if allowed_projects.all_projects:
        return await _run_list_operation(client, operation, all_projects=True, limit=limit)
    if not allowed_projects.project_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No project-scoped access to EP resources")
    pages = await asyncio.gather(
        *(
            _run_list_operation(client, operation, project_id=project_id, limit=limit)
            for project_id in allowed_projects.project_ids
        )
    )
    resources = [item for page in pages for item in page]
    resources.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return resources[:limit]


async def _run_list_operation(
    client: ExecutionPlaneHttpClient,
    operation: Literal["execution_targets", "work_items"],
    *,
    limit: int,
    project_id: UUID | None = None,
    all_projects: bool = False,
) -> list[dict[str, object]]:
    """Invoke one supported project-scoped list method on the shared transport."""
    if operation == "work_items":
        return await client.list_work_items(project_id=project_id, all_projects=all_projects, limit=limit)
    return await client.list_execution_targets(project_id=project_id, all_projects=all_projects, limit=limit)


@router.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[NO_PERMISSION],
    operation_id="accept_execution_plane_event",
    summary="Accept an Execution Plane completion event",
)
async def accept_execution_plane_event(request: Request, event: EPCompletionEvent) -> dict[str, str]:
    """Persist an EP callback before acknowledging delivery to the producer."""
    settings = get_settings()
    if (
        not getattr(request.state, "is_cert_authenticated", False)
        or getattr(request.state, "cert_cn", None) != settings.ep_callback_service_cn
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Execution Plane service identity required")
    try:
        await persist_completion_event(event.model_dump())
    except CompletionBindingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No matching AO dispatch is recorded") from exc
    except CompletionEventConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    logger.info("Persisted Execution Plane completion event", event_id=str(event.event_id))
    return {"status": "accepted"}
