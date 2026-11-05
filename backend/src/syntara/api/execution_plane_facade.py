"""Execution Plane target CRUD and resource reads through the AO API boundary.

Query controls mirror syntara.core.models.base.query_params.BaseListParams.
The client publishes filterable/sortable field metadata that both EP and the
facade use for validation. This ensures filter/sort validation happens at the
facade layer before forwarding to EP, matching syntara's own resource pattern.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated, Any, Literal
from uuid import UUID  # noqa: TC003 — Pydantic resolves model annotations at runtime

import structlog
from execution_plane_client.models.execution_target import (
    EXECUTION_TARGET_FILTERABLE_FIELDS,
    EXECUTION_TARGET_SORTABLE_FIELDS,
    ExecutionTargetCreate,
    ExecutionTargetDeleteAccepted,
    ExecutionTargetHealthResult,
    ExecutionTargetListParams,
    ExecutionTargetRead,
    ExecutionTargetUpdate,
)
from execution_plane_client.models.shared import EPListParams, ResourcesResponse
from execution_plane_client.models.work_item import (
    WORK_ITEM_FILTERABLE_FIELDS,
    WORK_ITEM_SORTABLE_FIELDS,
    WorkItemListParams,
    WorkItemRead,
)
from fastapi import Depends, HTTPException, Query, Request, Response, status
from pydantic import ValidationError

from syntara.authz.dependencies import PermissionChecker, ProjectScopeFilter
from syntara.authz.engine import AllowedProjectsResult  # noqa: TC001 — FastAPI resolves dependency annotations
from syntara.core.models.base import BaseListParams
from syntara.core.syntara_router import SyntaraRouter
from syntara.execution_plane.client import (
    ExecutionPlaneHttpClient,
    ExecutionPlaneRejectedError,
    ExecutionPlaneUnavailableError,
)
from syntara.execution_plane.targets import (
    create_target,
    delete_target,
    get_target_health,
    update_target,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.stdlib.get_logger(__name__)

router = SyntaraRouter(prefix="/api/execution_plane/v1", tags=["Execution Plane"])
_target_scope = ProjectScopeFilter("execution_target", "read")
_work_item_scope = ProjectScopeFilter("work_item", "read")
_TARGET_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "Execution target or installed cluster not found"},
    409: {"description": "Cluster not ready or protected target lifecycle conflict"},
    502: {"description": "Invalid Execution Plane response"},
    503: {"description": "Execution Plane unavailable"},
}


_BRACKET_PATTERN = re.compile(r"^([a-z][a-z0-9_]*)\[([a-z]+)\]$")


def _validate_query_params(
    query_params: list[tuple[str, str]],
    filterable_fields: list[str],
    *,
    supports_labels: bool = True,
) -> None:
    """Validate filter and sort fields against EP metadata before forwarding.

    Raises HTTPException 422 if invalid fields are detected. Matches syntara's
    server-side validation pattern for its own resources.
    """
    excluded = {"limit", "cursor", "sort", "include_total"}

    for key, _value in query_params:
        if key in excluded:
            continue

        # Check labels[key] pattern
        if key.startswith("labels[") and key.endswith("]"):
            if not supports_labels:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Label filtering not supported for this resource: {key}",
                )
            continue

        # Check field[operator] pattern
        bracket_match = _BRACKET_PATTERN.match(key)
        field = bracket_match.group(1) if bracket_match else key

        # Validate field is filterable
        if field not in filterable_fields:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid filter field: {field}",
            )


def _validate_sort(sort_value: str | None, sortable_fields: list[str]) -> None:
    """Validate sort field against EP metadata.

    Pydantic already validates the pattern (^-?[a-z][a-z0-9_]*$), this validates
    the field name is in the sortable list.
    """
    if not sort_value:
        return

    # Strip leading '-' for descending sort
    field = sort_value.lstrip("-")

    if field not in sortable_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid sort field: {field}. Valid fields: {', '.join(sortable_fields)}",
        )


@asynccontextmanager
async def _target_client() -> AsyncIterator[ExecutionPlaneHttpClient]:
    """Translate domain failures while keeping service-auth failures private."""
    try:
        async with ExecutionPlaneHttpClient() as client:
            yield client
    except ExecutionPlaneUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Execution Plane unavailable") from exc
    except ExecutionPlaneRejectedError as exc:
        if exc.status_code in {404, 409, 422}:
            raise HTTPException(exc.status_code, exc.detail or str(exc)) from exc
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Invalid Execution Plane response") from exc
    except (ValidationError, KeyError, TypeError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Invalid Execution Plane response") from exc


@router.post(
    "/execution_targets",
    operation_id="create_execution_target",
    summary="Create execution target",
    status_code=status.HTTP_201_CREATED,
    responses={
        **_TARGET_RESPONSES,
        201: {
            "description": "Created execution target",
            "headers": {"Location": {"description": "AO target detail path", "schema": {"type": "string"}}},
        },
    },
    dependencies=[Depends(PermissionChecker("execution_target", "create"))],
)
async def create_execution_target(data: ExecutionTargetCreate, response: Response) -> ExecutionTargetRead:
    """Create a Kubernetes target on the installed cluster through EP commands."""
    async with _target_client() as client:
        target_data = await create_target(client, data)
        target = ExecutionTargetRead.model_validate(target_data)
    response.headers["Location"] = f"/api/execution_plane/v1/execution_targets/{target.id}"
    return target


@router.get(
    "/execution_targets/{target_id}",
    operation_id="get_execution_target",
    summary="Get execution target",
    responses=_TARGET_RESPONSES,
    dependencies=[Depends(PermissionChecker("execution_target", "read", resource_id_param="target_id"))],
)
async def get_execution_target(target_id: UUID) -> ExecutionTargetRead:
    """Read the authoritative EP target by its physical UUID."""
    async with _target_client() as client:
        target = ExecutionTargetRead.model_validate(await client.get_execution_target(target_id=target_id))
        if target.id != target_id:
            raise ExecutionPlaneRejectedError
        return target


@router.get(
    "/execution_targets/{target_id}/health",
    operation_id="get_execution_target_health",
    summary="Get execution target health",
    responses={**_TARGET_RESPONSES, 200: {"description": "On-demand execution target health"}},
    dependencies=[Depends(PermissionChecker("execution_target", "read", resource_id_param="target_id"))],
)
async def get_execution_target_health(target_id: UUID) -> ExecutionTargetHealthResult:
    """Dispatch a target health command and return EP's shallow typed result."""
    async with _target_client() as client:
        return await get_target_health(client, target_id)


@router.patch(
    "/execution_targets/{target_id}",
    operation_id="update_execution_target",
    summary="Update execution target",
    responses=_TARGET_RESPONSES,
    dependencies=[Depends(PermissionChecker("execution_target", "update", resource_id_param="target_id"))],
)
async def update_execution_target(target_id: UUID, data: ExecutionTargetUpdate) -> ExecutionTargetRead:
    """Patch target placement, routing labels, name, enabled state, or default selection through EP."""
    async with _target_client() as client:
        return ExecutionTargetRead.model_validate(await update_target(client, target_id, data))


@router.delete(
    "/execution_targets/{target_id}",
    operation_id="delete_execution_target",
    summary="Delete execution target",
    status_code=status.HTTP_202_ACCEPTED,
    responses=_TARGET_RESPONSES,
    dependencies=[Depends(PermissionChecker("execution_target", "delete", resource_id_param="target_id"))],
)
async def delete_execution_target(target_id: UUID) -> ExecutionTargetDeleteAccepted:
    """Begin draining a target; promote another target before deleting the default."""
    async with _target_client() as client:
        await delete_target(client, target_id)
    return ExecutionTargetDeleteAccepted(id=target_id)


@router.get(
    "/execution_targets",
    operation_id="list_execution_targets",
    summary="List execution targets",
    description=(
        "Retrieve registered execution targets. Filters use field=value or field[operator]=value; "
        "labels[key]=value matches a label and an empty value tests key existence. "
        "EP validates fields and operators. Keep filters, sort, and limit unchanged when following opaque cursors."
    ),
    responses={
        502: {"description": "Invalid Execution Plane response"},
        503: {"description": "Execution Plane unavailable"},
    },
)
async def list_execution_targets(
    request: Request,
    allowed_projects: Annotated[AllowedProjectsResult, Depends(_target_scope)],
    params: Annotated[ExecutionTargetListParams, Query()],
) -> ResourcesResponse[ExecutionTargetRead]:
    """Read registered execution targets from EP after AO permission checks."""
    # Validate query params against EP metadata before forwarding
    _validate_query_params(
        request.query_params.multi_items(),
        EXECUTION_TARGET_FILTERABLE_FIELDS,
        supports_labels=True,
    )
    _validate_sort(params.sort, EXECUTION_TARGET_SORTABLE_FIELDS)

    try:
        async with ExecutionPlaneHttpClient() as client:
            page = await _list_ep_resources(
                client,
                operation="execution_targets",
                allowed_projects=allowed_projects,
                params=params,
                query_params=request.query_params.multi_items(),
            )
        resources = [ExecutionTargetRead.model_validate(item) for item in page["resources"]]
    except ExecutionPlaneUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution Plane unavailable",
        ) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid Execution Plane response") from exc
    logger.info("Listed execution targets", count=len(resources))
    return ResourcesResponse(
        resources=resources,
        next=page.get("next"),
        prev=page.get("prev"),
        total=page.get("total"),
    )


@router.get(
    "/work_items",
    operation_id="list_work_items",
    summary="List work items",
    description=(
        "Retrieve work items. Filters use field=value or field[operator]=value; comma-separated "
        "values within one field/operator use OR and different fields/operators use AND. "
        "EP validates fields and operators. Keep filters, sort, and limit unchanged when following opaque cursors."
    ),
    responses={
        502: {"description": "Invalid Execution Plane response"},
        503: {"description": "Execution Plane unavailable"},
    },
)
async def list_work_items(
    request: Request,
    allowed_projects: Annotated[AllowedProjectsResult, Depends(_work_item_scope)],
    params: Annotated[WorkItemListParams, Query()],
) -> ResourcesResponse[WorkItemRead]:
    """Read work-item state from EP after AO permission checks."""
    # Validate query params against EP metadata before forwarding
    _validate_query_params(
        request.query_params.multi_items(),
        WORK_ITEM_FILTERABLE_FIELDS,
        supports_labels=False,  # Work items don't have labels
    )
    _validate_sort(params.sort, WORK_ITEM_SORTABLE_FIELDS)

    try:
        async with ExecutionPlaneHttpClient() as client:
            page = await _list_ep_resources(
                client,
                operation="work_items",
                allowed_projects=allowed_projects,
                params=params,
                query_params=request.query_params.multi_items(),
            )
        resources = [WorkItemRead.model_validate(item) for item in page["resources"]]
    except ExecutionPlaneUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution Plane unavailable",
        ) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid Execution Plane response") from exc
    logger.info("Listed work items", count=len(resources))
    return ResourcesResponse(
        resources=resources,
        next=page.get("next"),
        prev=page.get("prev"),
        total=page.get("total"),
    )


async def _list_ep_resources(
    client: ExecutionPlaneHttpClient,
    *,
    operation: Literal["execution_targets", "work_items"],
    allowed_projects: AllowedProjectsResult,
    params: EPListParams,
    query_params: list[tuple[str, str]],
) -> dict[str, Any]:
    """List EP resources after AO permission checks. EP has no project scope."""
    if not allowed_projects.all_projects and not allowed_projects.project_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No project-scoped access to EP resources")
    filters = {key: value for key, value in query_params if key not in BaseListParams.model_fields}
    sort = params.sort if any(key == "sort" for key, _ in query_params) else None
    try:
        list_page = client.list_work_items if operation == "work_items" else client.list_execution_targets
        return await list_page(
            limit=params.limit,
            cursor=params.cursor,
            sort=sort,
            include_total=params.include_total,
            filters=filters,
        )
    except ExecutionPlaneRejectedError as exc:
        if exc.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.detail if exc.detail is not None else str(exc),
            ) from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid Execution Plane response") from exc
