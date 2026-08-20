from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.execution_list_response import ExecutionListResponse
from ...models.list_executions_approval_pending import ListExecutionsApprovalPending
from ...models.list_executions_completed_at import ListExecutionsCompletedAt
from ...models.list_executions_created_at import ListExecutionsCreatedAt
from ...models.list_executions_created_by import ListExecutionsCreatedBy
from ...models.list_executions_deleted_at import ListExecutionsDeletedAt
from ...models.list_executions_deleted_by import ListExecutionsDeletedBy
from ...models.list_executions_id import ListExecutionsId
from ...models.list_executions_mode import ListExecutionsMode
from ...models.list_executions_project_id import ListExecutionsProjectId
from ...models.list_executions_status import ListExecutionsStatus
from ...models.list_executions_updated_at import ListExecutionsUpdatedAt
from ...models.list_executions_updated_by import ListExecutionsUpdatedBy
from ...models.list_executions_workflow_id import ListExecutionsWorkflowId
from ...models.list_executions_workflow_version_id import ListExecutionsWorkflowVersionId
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListExecutionsId | Unset = UNSET,
    created_at: ListExecutionsCreatedAt | Unset = UNSET,
    updated_at: ListExecutionsUpdatedAt | Unset = UNSET,
    created_by: ListExecutionsCreatedBy | Unset = UNSET,
    updated_by: ListExecutionsUpdatedBy | Unset = UNSET,
    deleted_at: ListExecutionsDeletedAt | Unset = UNSET,
    deleted_by: ListExecutionsDeletedBy | Unset = UNSET,
    workflow_id: ListExecutionsWorkflowId | Unset = UNSET,
    workflow_version_id: ListExecutionsWorkflowVersionId | Unset = UNSET,
    project_id: ListExecutionsProjectId | Unset = UNSET,
    status: ListExecutionsStatus | Unset = UNSET,
    mode: ListExecutionsMode | Unset = UNSET,
    completed_at: ListExecutionsCompletedAt | Unset = UNSET,
    approval_pending: ListExecutionsApprovalPending | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if isinstance(additional_params, dict):
        params = additional_params

    params["limit"] = limit

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    json_sort: None | str | Unset
    if isinstance(sort, Unset):
        json_sort = UNSET
    else:
        json_sort = sort
    params["sort"] = json_sort

    params["include_total"] = include_total

    json_id: dict[str, Any] | Unset = UNSET
    if not isinstance(id, Unset):
        json_id = id.to_dict()
    if not isinstance(json_id, Unset):
        params.update(json_id)

    json_created_at: dict[str, Any] | Unset = UNSET
    if not isinstance(created_at, Unset):
        json_created_at = created_at.to_dict()
    if not isinstance(json_created_at, Unset):
        params.update(json_created_at)

    json_updated_at: dict[str, Any] | Unset = UNSET
    if not isinstance(updated_at, Unset):
        json_updated_at = updated_at.to_dict()
    if not isinstance(json_updated_at, Unset):
        params.update(json_updated_at)

    json_created_by: dict[str, Any] | Unset = UNSET
    if not isinstance(created_by, Unset):
        json_created_by = created_by.to_dict()
    if not isinstance(json_created_by, Unset):
        params.update(json_created_by)

    json_updated_by: dict[str, Any] | Unset = UNSET
    if not isinstance(updated_by, Unset):
        json_updated_by = updated_by.to_dict()
    if not isinstance(json_updated_by, Unset):
        params.update(json_updated_by)

    json_deleted_at: dict[str, Any] | Unset = UNSET
    if not isinstance(deleted_at, Unset):
        json_deleted_at = deleted_at.to_dict()
    if not isinstance(json_deleted_at, Unset):
        params.update(json_deleted_at)

    json_deleted_by: dict[str, Any] | Unset = UNSET
    if not isinstance(deleted_by, Unset):
        json_deleted_by = deleted_by.to_dict()
    if not isinstance(json_deleted_by, Unset):
        params.update(json_deleted_by)

    json_workflow_id: dict[str, Any] | Unset = UNSET
    if not isinstance(workflow_id, Unset):
        json_workflow_id = workflow_id.to_dict()
    if not isinstance(json_workflow_id, Unset):
        params.update(json_workflow_id)

    json_workflow_version_id: dict[str, Any] | Unset = UNSET
    if not isinstance(workflow_version_id, Unset):
        json_workflow_version_id = workflow_version_id.to_dict()
    if not isinstance(json_workflow_version_id, Unset):
        params.update(json_workflow_version_id)

    json_project_id: dict[str, Any] | Unset = UNSET
    if not isinstance(project_id, Unset):
        json_project_id = project_id.to_dict()
    if not isinstance(json_project_id, Unset):
        params.update(json_project_id)

    json_status: dict[str, Any] | Unset = UNSET
    if not isinstance(status, Unset):
        json_status = status.to_dict()
    if not isinstance(json_status, Unset):
        params.update(json_status)

    json_mode: dict[str, Any] | Unset = UNSET
    if not isinstance(mode, Unset):
        json_mode = mode.to_dict()
    if not isinstance(json_mode, Unset):
        params.update(json_mode)

    json_completed_at: dict[str, Any] | Unset = UNSET
    if not isinstance(completed_at, Unset):
        json_completed_at = completed_at.to_dict()
    if not isinstance(json_completed_at, Unset):
        params.update(json_completed_at)

    json_approval_pending: dict[str, Any] | Unset = UNSET
    if not isinstance(approval_pending, Unset):
        json_approval_pending = approval_pending.to_dict()
    if not isinstance(json_approval_pending, Unset):
        params.update(json_approval_pending)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/executions",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ExecutionListResponse | None:
    if response.status_code == 200:
        response_200 = ExecutionListResponse.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = ErrorData.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = ErrorData.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = ErrorData.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = ErrorData.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = ErrorData.from_dict(response.json())

        return response_409

    if response.status_code == 422:
        response_422 = ErrorData.from_dict(response.json())

        return response_422

    if response.status_code == 429:
        response_429 = ErrorData.from_dict(response.json())

        return response_429

    if response.status_code == 500:
        response_500 = ErrorData.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorData | ExecutionListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListExecutionsId | Unset = UNSET,
    created_at: ListExecutionsCreatedAt | Unset = UNSET,
    updated_at: ListExecutionsUpdatedAt | Unset = UNSET,
    created_by: ListExecutionsCreatedBy | Unset = UNSET,
    updated_by: ListExecutionsUpdatedBy | Unset = UNSET,
    deleted_at: ListExecutionsDeletedAt | Unset = UNSET,
    deleted_by: ListExecutionsDeletedBy | Unset = UNSET,
    workflow_id: ListExecutionsWorkflowId | Unset = UNSET,
    workflow_version_id: ListExecutionsWorkflowVersionId | Unset = UNSET,
    project_id: ListExecutionsProjectId | Unset = UNSET,
    status: ListExecutionsStatus | Unset = UNSET,
    mode: ListExecutionsMode | Unset = UNSET,
    completed_at: ListExecutionsCompletedAt | Unset = UNSET,
    approval_pending: ListExecutionsApprovalPending | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | ExecutionListResponse]:
    """List executions

     Retrieve executions with filtering, sorting, and cursor-based pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListExecutionsId | Unset):
        created_at (ListExecutionsCreatedAt | Unset):
        updated_at (ListExecutionsUpdatedAt | Unset):
        created_by (ListExecutionsCreatedBy | Unset):
        updated_by (ListExecutionsUpdatedBy | Unset):
        deleted_at (ListExecutionsDeletedAt | Unset):
        deleted_by (ListExecutionsDeletedBy | Unset):
        workflow_id (ListExecutionsWorkflowId | Unset):
        workflow_version_id (ListExecutionsWorkflowVersionId | Unset):
        project_id (ListExecutionsProjectId | Unset):
        status (ListExecutionsStatus | Unset):
        mode (ListExecutionsMode | Unset):
        completed_at (ListExecutionsCompletedAt | Unset):
        approval_pending (ListExecutionsApprovalPending | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ExecutionListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        created_by=created_by,
        updated_by=updated_by,
        deleted_at=deleted_at,
        deleted_by=deleted_by,
        workflow_id=workflow_id,
        workflow_version_id=workflow_version_id,
        project_id=project_id,
        status=status,
        mode=mode,
        completed_at=completed_at,
        approval_pending=approval_pending,
        additional_params=additional_params,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListExecutionsId | Unset = UNSET,
    created_at: ListExecutionsCreatedAt | Unset = UNSET,
    updated_at: ListExecutionsUpdatedAt | Unset = UNSET,
    created_by: ListExecutionsCreatedBy | Unset = UNSET,
    updated_by: ListExecutionsUpdatedBy | Unset = UNSET,
    deleted_at: ListExecutionsDeletedAt | Unset = UNSET,
    deleted_by: ListExecutionsDeletedBy | Unset = UNSET,
    workflow_id: ListExecutionsWorkflowId | Unset = UNSET,
    workflow_version_id: ListExecutionsWorkflowVersionId | Unset = UNSET,
    project_id: ListExecutionsProjectId | Unset = UNSET,
    status: ListExecutionsStatus | Unset = UNSET,
    mode: ListExecutionsMode | Unset = UNSET,
    completed_at: ListExecutionsCompletedAt | Unset = UNSET,
    approval_pending: ListExecutionsApprovalPending | Unset = UNSET,
) -> ErrorData | ExecutionListResponse | None:
    """List executions

     Retrieve executions with filtering, sorting, and cursor-based pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListExecutionsId | Unset):
        created_at (ListExecutionsCreatedAt | Unset):
        updated_at (ListExecutionsUpdatedAt | Unset):
        created_by (ListExecutionsCreatedBy | Unset):
        updated_by (ListExecutionsUpdatedBy | Unset):
        deleted_at (ListExecutionsDeletedAt | Unset):
        deleted_by (ListExecutionsDeletedBy | Unset):
        workflow_id (ListExecutionsWorkflowId | Unset):
        workflow_version_id (ListExecutionsWorkflowVersionId | Unset):
        project_id (ListExecutionsProjectId | Unset):
        status (ListExecutionsStatus | Unset):
        mode (ListExecutionsMode | Unset):
        completed_at (ListExecutionsCompletedAt | Unset):
        approval_pending (ListExecutionsApprovalPending | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ExecutionListResponse
    """

    return sync_detailed(
        client=client,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        created_by=created_by,
        updated_by=updated_by,
        deleted_at=deleted_at,
        deleted_by=deleted_by,
        workflow_id=workflow_id,
        workflow_version_id=workflow_version_id,
        project_id=project_id,
        status=status,
        mode=mode,
        completed_at=completed_at,
        approval_pending=approval_pending,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListExecutionsId | Unset = UNSET,
    created_at: ListExecutionsCreatedAt | Unset = UNSET,
    updated_at: ListExecutionsUpdatedAt | Unset = UNSET,
    created_by: ListExecutionsCreatedBy | Unset = UNSET,
    updated_by: ListExecutionsUpdatedBy | Unset = UNSET,
    deleted_at: ListExecutionsDeletedAt | Unset = UNSET,
    deleted_by: ListExecutionsDeletedBy | Unset = UNSET,
    workflow_id: ListExecutionsWorkflowId | Unset = UNSET,
    workflow_version_id: ListExecutionsWorkflowVersionId | Unset = UNSET,
    project_id: ListExecutionsProjectId | Unset = UNSET,
    status: ListExecutionsStatus | Unset = UNSET,
    mode: ListExecutionsMode | Unset = UNSET,
    completed_at: ListExecutionsCompletedAt | Unset = UNSET,
    approval_pending: ListExecutionsApprovalPending | Unset = UNSET,
) -> Response[ErrorData | ExecutionListResponse]:
    """List executions

     Retrieve executions with filtering, sorting, and cursor-based pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListExecutionsId | Unset):
        created_at (ListExecutionsCreatedAt | Unset):
        updated_at (ListExecutionsUpdatedAt | Unset):
        created_by (ListExecutionsCreatedBy | Unset):
        updated_by (ListExecutionsUpdatedBy | Unset):
        deleted_at (ListExecutionsDeletedAt | Unset):
        deleted_by (ListExecutionsDeletedBy | Unset):
        workflow_id (ListExecutionsWorkflowId | Unset):
        workflow_version_id (ListExecutionsWorkflowVersionId | Unset):
        project_id (ListExecutionsProjectId | Unset):
        status (ListExecutionsStatus | Unset):
        mode (ListExecutionsMode | Unset):
        completed_at (ListExecutionsCompletedAt | Unset):
        approval_pending (ListExecutionsApprovalPending | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ExecutionListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        created_by=created_by,
        updated_by=updated_by,
        deleted_at=deleted_at,
        deleted_by=deleted_by,
        workflow_id=workflow_id,
        workflow_version_id=workflow_version_id,
        project_id=project_id,
        status=status,
        mode=mode,
        completed_at=completed_at,
        approval_pending=approval_pending,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListExecutionsId | Unset = UNSET,
    created_at: ListExecutionsCreatedAt | Unset = UNSET,
    updated_at: ListExecutionsUpdatedAt | Unset = UNSET,
    created_by: ListExecutionsCreatedBy | Unset = UNSET,
    updated_by: ListExecutionsUpdatedBy | Unset = UNSET,
    deleted_at: ListExecutionsDeletedAt | Unset = UNSET,
    deleted_by: ListExecutionsDeletedBy | Unset = UNSET,
    workflow_id: ListExecutionsWorkflowId | Unset = UNSET,
    workflow_version_id: ListExecutionsWorkflowVersionId | Unset = UNSET,
    project_id: ListExecutionsProjectId | Unset = UNSET,
    status: ListExecutionsStatus | Unset = UNSET,
    mode: ListExecutionsMode | Unset = UNSET,
    completed_at: ListExecutionsCompletedAt | Unset = UNSET,
    approval_pending: ListExecutionsApprovalPending | Unset = UNSET,
) -> ErrorData | ExecutionListResponse | None:
    """List executions

     Retrieve executions with filtering, sorting, and cursor-based pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListExecutionsId | Unset):
        created_at (ListExecutionsCreatedAt | Unset):
        updated_at (ListExecutionsUpdatedAt | Unset):
        created_by (ListExecutionsCreatedBy | Unset):
        updated_by (ListExecutionsUpdatedBy | Unset):
        deleted_at (ListExecutionsDeletedAt | Unset):
        deleted_by (ListExecutionsDeletedBy | Unset):
        workflow_id (ListExecutionsWorkflowId | Unset):
        workflow_version_id (ListExecutionsWorkflowVersionId | Unset):
        project_id (ListExecutionsProjectId | Unset):
        status (ListExecutionsStatus | Unset):
        mode (ListExecutionsMode | Unset):
        completed_at (ListExecutionsCompletedAt | Unset):
        approval_pending (ListExecutionsApprovalPending | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ExecutionListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            created_by=created_by,
            updated_by=updated_by,
            deleted_at=deleted_at,
            deleted_by=deleted_by,
            workflow_id=workflow_id,
            workflow_version_id=workflow_version_id,
            project_id=project_id,
            status=status,
            mode=mode,
            completed_at=completed_at,
            approval_pending=approval_pending,
        )
    ).parsed
