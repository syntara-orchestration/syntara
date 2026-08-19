from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.approval_list_response import ApprovalListResponse
from ...models.error_data import ErrorData
from ...models.list_project_approvals_created_at import ListProjectApprovalsCreatedAt
from ...models.list_project_approvals_execution_id import ListProjectApprovalsExecutionId
from ...models.list_project_approvals_id import ListProjectApprovalsId
from ...models.list_project_approvals_name import ListProjectApprovalsName
from ...models.list_project_approvals_status import ListProjectApprovalsStatus
from ...models.list_project_approvals_timeout_at import ListProjectApprovalsTimeoutAt
from ...models.list_project_approvals_updated_at import ListProjectApprovalsUpdatedAt
from ...types import UNSET, Response, Unset


def _get_kwargs(
    project_id: UUID,
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListProjectApprovalsId | Unset = UNSET,
    created_at: ListProjectApprovalsCreatedAt | Unset = UNSET,
    updated_at: ListProjectApprovalsUpdatedAt | Unset = UNSET,
    name: ListProjectApprovalsName | Unset = UNSET,
    execution_id: ListProjectApprovalsExecutionId | Unset = UNSET,
    status: ListProjectApprovalsStatus | Unset = UNSET,
    timeout_at: ListProjectApprovalsTimeoutAt | Unset = UNSET,
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

    json_name: dict[str, Any] | Unset = UNSET
    if not isinstance(name, Unset):
        json_name = name.to_dict()
    if not isinstance(json_name, Unset):
        params.update(json_name)

    json_execution_id: dict[str, Any] | Unset = UNSET
    if not isinstance(execution_id, Unset):
        json_execution_id = execution_id.to_dict()
    if not isinstance(json_execution_id, Unset):
        params.update(json_execution_id)

    json_status: dict[str, Any] | Unset = UNSET
    if not isinstance(status, Unset):
        json_status = status.to_dict()
    if not isinstance(json_status, Unset):
        params.update(json_status)

    json_timeout_at: dict[str, Any] | Unset = UNSET
    if not isinstance(timeout_at, Unset):
        json_timeout_at = timeout_at.to_dict()
    if not isinstance(json_timeout_at, Unset):
        params.update(json_timeout_at)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/projects/{project_id}/approvals",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ApprovalListResponse | ErrorData | None:
    if response.status_code == 200:
        response_200 = ApprovalListResponse.from_dict(response.json())

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
) -> Response[ApprovalListResponse | ErrorData]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    project_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListProjectApprovalsId | Unset = UNSET,
    created_at: ListProjectApprovalsCreatedAt | Unset = UNSET,
    updated_at: ListProjectApprovalsUpdatedAt | Unset = UNSET,
    name: ListProjectApprovalsName | Unset = UNSET,
    execution_id: ListProjectApprovalsExecutionId | Unset = UNSET,
    status: ListProjectApprovalsStatus | Unset = UNSET,
    timeout_at: ListProjectApprovalsTimeoutAt | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ApprovalListResponse | ErrorData]:
    """List project approvals

     List approval requests belonging to a specific project.

    Returns only approvals with project_id matching the given project.
    Requires: approval:read permission scoped to this project.

    Args:
        project_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListProjectApprovalsId | Unset):
        created_at (ListProjectApprovalsCreatedAt | Unset):
        updated_at (ListProjectApprovalsUpdatedAt | Unset):
        name (ListProjectApprovalsName | Unset):
        execution_id (ListProjectApprovalsExecutionId | Unset):
        status (ListProjectApprovalsStatus | Unset):
        timeout_at (ListProjectApprovalsTimeoutAt | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApprovalListResponse | ErrorData]
    """

    kwargs = _get_kwargs(
        project_id=project_id,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        execution_id=execution_id,
        status=status,
        timeout_at=timeout_at,
        additional_params=additional_params,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    project_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListProjectApprovalsId | Unset = UNSET,
    created_at: ListProjectApprovalsCreatedAt | Unset = UNSET,
    updated_at: ListProjectApprovalsUpdatedAt | Unset = UNSET,
    name: ListProjectApprovalsName | Unset = UNSET,
    execution_id: ListProjectApprovalsExecutionId | Unset = UNSET,
    status: ListProjectApprovalsStatus | Unset = UNSET,
    timeout_at: ListProjectApprovalsTimeoutAt | Unset = UNSET,
) -> ApprovalListResponse | ErrorData | None:
    """List project approvals

     List approval requests belonging to a specific project.

    Returns only approvals with project_id matching the given project.
    Requires: approval:read permission scoped to this project.

    Args:
        project_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListProjectApprovalsId | Unset):
        created_at (ListProjectApprovalsCreatedAt | Unset):
        updated_at (ListProjectApprovalsUpdatedAt | Unset):
        name (ListProjectApprovalsName | Unset):
        execution_id (ListProjectApprovalsExecutionId | Unset):
        status (ListProjectApprovalsStatus | Unset):
        timeout_at (ListProjectApprovalsTimeoutAt | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApprovalListResponse | ErrorData
    """

    return sync_detailed(
        project_id=project_id,
        client=client,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        execution_id=execution_id,
        status=status,
        timeout_at=timeout_at,
    ).parsed


async def asyncio_detailed(
    project_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListProjectApprovalsId | Unset = UNSET,
    created_at: ListProjectApprovalsCreatedAt | Unset = UNSET,
    updated_at: ListProjectApprovalsUpdatedAt | Unset = UNSET,
    name: ListProjectApprovalsName | Unset = UNSET,
    execution_id: ListProjectApprovalsExecutionId | Unset = UNSET,
    status: ListProjectApprovalsStatus | Unset = UNSET,
    timeout_at: ListProjectApprovalsTimeoutAt | Unset = UNSET,
) -> Response[ApprovalListResponse | ErrorData]:
    """List project approvals

     List approval requests belonging to a specific project.

    Returns only approvals with project_id matching the given project.
    Requires: approval:read permission scoped to this project.

    Args:
        project_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListProjectApprovalsId | Unset):
        created_at (ListProjectApprovalsCreatedAt | Unset):
        updated_at (ListProjectApprovalsUpdatedAt | Unset):
        name (ListProjectApprovalsName | Unset):
        execution_id (ListProjectApprovalsExecutionId | Unset):
        status (ListProjectApprovalsStatus | Unset):
        timeout_at (ListProjectApprovalsTimeoutAt | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApprovalListResponse | ErrorData]
    """

    kwargs = _get_kwargs(
        project_id=project_id,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        execution_id=execution_id,
        status=status,
        timeout_at=timeout_at,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    project_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListProjectApprovalsId | Unset = UNSET,
    created_at: ListProjectApprovalsCreatedAt | Unset = UNSET,
    updated_at: ListProjectApprovalsUpdatedAt | Unset = UNSET,
    name: ListProjectApprovalsName | Unset = UNSET,
    execution_id: ListProjectApprovalsExecutionId | Unset = UNSET,
    status: ListProjectApprovalsStatus | Unset = UNSET,
    timeout_at: ListProjectApprovalsTimeoutAt | Unset = UNSET,
) -> ApprovalListResponse | ErrorData | None:
    """List project approvals

     List approval requests belonging to a specific project.

    Returns only approvals with project_id matching the given project.
    Requires: approval:read permission scoped to this project.

    Args:
        project_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListProjectApprovalsId | Unset):
        created_at (ListProjectApprovalsCreatedAt | Unset):
        updated_at (ListProjectApprovalsUpdatedAt | Unset):
        name (ListProjectApprovalsName | Unset):
        execution_id (ListProjectApprovalsExecutionId | Unset):
        status (ListProjectApprovalsStatus | Unset):
        timeout_at (ListProjectApprovalsTimeoutAt | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApprovalListResponse | ErrorData
    """

    return (
        await asyncio_detailed(
            project_id=project_id,
            client=client,
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            name=name,
            execution_id=execution_id,
            status=status,
            timeout_at=timeout_at,
        )
    ).parsed
