from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.activity_execution_list_response import ActivityExecutionListResponse
from ...models.error_data import ErrorData
from ...models.list_execution_activities_activity_name import ListExecutionActivitiesActivityName
from ...models.list_execution_activities_created_at import ListExecutionActivitiesCreatedAt
from ...models.list_execution_activities_id import ListExecutionActivitiesId
from ...models.list_execution_activities_node_type import ListExecutionActivitiesNodeType
from ...models.list_execution_activities_status import ListExecutionActivitiesStatus
from ...models.list_execution_activities_updated_at import ListExecutionActivitiesUpdatedAt
from ...types import UNSET, Response, Unset


def _get_kwargs(
    execution_id: UUID,
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListExecutionActivitiesId | Unset = UNSET,
    created_at: ListExecutionActivitiesCreatedAt | Unset = UNSET,
    updated_at: ListExecutionActivitiesUpdatedAt | Unset = UNSET,
    activity_name: ListExecutionActivitiesActivityName | Unset = UNSET,
    node_type: ListExecutionActivitiesNodeType | Unset = UNSET,
    status: ListExecutionActivitiesStatus | Unset = UNSET,
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

    json_activity_name: dict[str, Any] | Unset = UNSET
    if not isinstance(activity_name, Unset):
        json_activity_name = activity_name.to_dict()
    if not isinstance(json_activity_name, Unset):
        params.update(json_activity_name)

    json_node_type: dict[str, Any] | Unset = UNSET
    if not isinstance(node_type, Unset):
        json_node_type = node_type.to_dict()
    if not isinstance(json_node_type, Unset):
        params.update(json_node_type)

    json_status: dict[str, Any] | Unset = UNSET
    if not isinstance(status, Unset):
        json_status = status.to_dict()
    if not isinstance(json_status, Unset):
        params.update(json_status)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/executions/{execution_id}/activities",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ActivityExecutionListResponse | ErrorData | None:
    if response.status_code == 200:
        response_200 = ActivityExecutionListResponse.from_dict(response.json())

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
) -> Response[ActivityExecutionListResponse | ErrorData]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListExecutionActivitiesId | Unset = UNSET,
    created_at: ListExecutionActivitiesCreatedAt | Unset = UNSET,
    updated_at: ListExecutionActivitiesUpdatedAt | Unset = UNSET,
    activity_name: ListExecutionActivitiesActivityName | Unset = UNSET,
    node_type: ListExecutionActivitiesNodeType | Unset = UNSET,
    status: ListExecutionActivitiesStatus | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ActivityExecutionListResponse | ErrorData]:
    """List activity executions

     Retrieve activity executions for a workflow execution.

    Args:
        execution_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListExecutionActivitiesId | Unset):
        created_at (ListExecutionActivitiesCreatedAt | Unset):
        updated_at (ListExecutionActivitiesUpdatedAt | Unset):
        activity_name (ListExecutionActivitiesActivityName | Unset):
        node_type (ListExecutionActivitiesNodeType | Unset):
        status (ListExecutionActivitiesStatus | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ActivityExecutionListResponse | ErrorData]
    """

    kwargs = _get_kwargs(
        execution_id=execution_id,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        activity_name=activity_name,
        node_type=node_type,
        status=status,
        additional_params=additional_params,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListExecutionActivitiesId | Unset = UNSET,
    created_at: ListExecutionActivitiesCreatedAt | Unset = UNSET,
    updated_at: ListExecutionActivitiesUpdatedAt | Unset = UNSET,
    activity_name: ListExecutionActivitiesActivityName | Unset = UNSET,
    node_type: ListExecutionActivitiesNodeType | Unset = UNSET,
    status: ListExecutionActivitiesStatus | Unset = UNSET,
) -> ActivityExecutionListResponse | ErrorData | None:
    """List activity executions

     Retrieve activity executions for a workflow execution.

    Args:
        execution_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListExecutionActivitiesId | Unset):
        created_at (ListExecutionActivitiesCreatedAt | Unset):
        updated_at (ListExecutionActivitiesUpdatedAt | Unset):
        activity_name (ListExecutionActivitiesActivityName | Unset):
        node_type (ListExecutionActivitiesNodeType | Unset):
        status (ListExecutionActivitiesStatus | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ActivityExecutionListResponse | ErrorData
    """

    return sync_detailed(
        execution_id=execution_id,
        client=client,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        activity_name=activity_name,
        node_type=node_type,
        status=status,
    ).parsed


async def asyncio_detailed(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListExecutionActivitiesId | Unset = UNSET,
    created_at: ListExecutionActivitiesCreatedAt | Unset = UNSET,
    updated_at: ListExecutionActivitiesUpdatedAt | Unset = UNSET,
    activity_name: ListExecutionActivitiesActivityName | Unset = UNSET,
    node_type: ListExecutionActivitiesNodeType | Unset = UNSET,
    status: ListExecutionActivitiesStatus | Unset = UNSET,
) -> Response[ActivityExecutionListResponse | ErrorData]:
    """List activity executions

     Retrieve activity executions for a workflow execution.

    Args:
        execution_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListExecutionActivitiesId | Unset):
        created_at (ListExecutionActivitiesCreatedAt | Unset):
        updated_at (ListExecutionActivitiesUpdatedAt | Unset):
        activity_name (ListExecutionActivitiesActivityName | Unset):
        node_type (ListExecutionActivitiesNodeType | Unset):
        status (ListExecutionActivitiesStatus | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ActivityExecutionListResponse | ErrorData]
    """

    kwargs = _get_kwargs(
        execution_id=execution_id,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        activity_name=activity_name,
        node_type=node_type,
        status=status,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListExecutionActivitiesId | Unset = UNSET,
    created_at: ListExecutionActivitiesCreatedAt | Unset = UNSET,
    updated_at: ListExecutionActivitiesUpdatedAt | Unset = UNSET,
    activity_name: ListExecutionActivitiesActivityName | Unset = UNSET,
    node_type: ListExecutionActivitiesNodeType | Unset = UNSET,
    status: ListExecutionActivitiesStatus | Unset = UNSET,
) -> ActivityExecutionListResponse | ErrorData | None:
    """List activity executions

     Retrieve activity executions for a workflow execution.

    Args:
        execution_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListExecutionActivitiesId | Unset):
        created_at (ListExecutionActivitiesCreatedAt | Unset):
        updated_at (ListExecutionActivitiesUpdatedAt | Unset):
        activity_name (ListExecutionActivitiesActivityName | Unset):
        node_type (ListExecutionActivitiesNodeType | Unset):
        status (ListExecutionActivitiesStatus | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ActivityExecutionListResponse | ErrorData
    """

    return (
        await asyncio_detailed(
            execution_id=execution_id,
            client=client,
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            activity_name=activity_name,
            node_type=node_type,
            status=status,
        )
    ).parsed
