from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.group_list_response import GroupListResponse
from ...models.list_groups_created_at import ListGroupsCreatedAt
from ...models.list_groups_created_by import ListGroupsCreatedBy
from ...models.list_groups_description import ListGroupsDescription
from ...models.list_groups_id import ListGroupsId
from ...models.list_groups_name import ListGroupsName
from ...models.list_groups_source import ListGroupsSource
from ...models.list_groups_updated_at import ListGroupsUpdatedAt
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListGroupsId | Unset = UNSET,
    created_at: ListGroupsCreatedAt | Unset = UNSET,
    updated_at: ListGroupsUpdatedAt | Unset = UNSET,
    name: ListGroupsName | Unset = UNSET,
    description: ListGroupsDescription | Unset = UNSET,
    created_by: ListGroupsCreatedBy | Unset = UNSET,
    source: ListGroupsSource | Unset = UNSET,
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

    json_description: dict[str, Any] | Unset = UNSET
    if not isinstance(description, Unset):
        json_description = description.to_dict()
    if not isinstance(json_description, Unset):
        params.update(json_description)

    json_created_by: dict[str, Any] | Unset = UNSET
    if not isinstance(created_by, Unset):
        json_created_by = created_by.to_dict()
    if not isinstance(json_created_by, Unset):
        params.update(json_created_by)

    json_source: dict[str, Any] | Unset = UNSET
    if not isinstance(source, Unset):
        json_source = source.to_dict()
    if not isinstance(json_source, Unset):
        params.update(json_source)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/groups",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | GroupListResponse | None:
    if response.status_code == 200:
        response_200 = GroupListResponse.from_dict(response.json())

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
) -> Response[ErrorData | GroupListResponse]:
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
    id: ListGroupsId | Unset = UNSET,
    created_at: ListGroupsCreatedAt | Unset = UNSET,
    updated_at: ListGroupsUpdatedAt | Unset = UNSET,
    name: ListGroupsName | Unset = UNSET,
    description: ListGroupsDescription | Unset = UNSET,
    created_by: ListGroupsCreatedBy | Unset = UNSET,
    source: ListGroupsSource | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | GroupListResponse]:
    """List groups

     Retrieve list of groups with visibility filtering.

    Users with ``group:read:any`` see all groups.
    Users with ``group:read:self`` see only their own groups.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListGroupsId | Unset):
        created_at (ListGroupsCreatedAt | Unset):
        updated_at (ListGroupsUpdatedAt | Unset):
        name (ListGroupsName | Unset):
        description (ListGroupsDescription | Unset):
        created_by (ListGroupsCreatedBy | Unset):
        source (ListGroupsSource | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | GroupListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        description=description,
        created_by=created_by,
        source=source,
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
    id: ListGroupsId | Unset = UNSET,
    created_at: ListGroupsCreatedAt | Unset = UNSET,
    updated_at: ListGroupsUpdatedAt | Unset = UNSET,
    name: ListGroupsName | Unset = UNSET,
    description: ListGroupsDescription | Unset = UNSET,
    created_by: ListGroupsCreatedBy | Unset = UNSET,
    source: ListGroupsSource | Unset = UNSET,
) -> ErrorData | GroupListResponse | None:
    """List groups

     Retrieve list of groups with visibility filtering.

    Users with ``group:read:any`` see all groups.
    Users with ``group:read:self`` see only their own groups.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListGroupsId | Unset):
        created_at (ListGroupsCreatedAt | Unset):
        updated_at (ListGroupsUpdatedAt | Unset):
        name (ListGroupsName | Unset):
        description (ListGroupsDescription | Unset):
        created_by (ListGroupsCreatedBy | Unset):
        source (ListGroupsSource | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | GroupListResponse
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
        name=name,
        description=description,
        created_by=created_by,
        source=source,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListGroupsId | Unset = UNSET,
    created_at: ListGroupsCreatedAt | Unset = UNSET,
    updated_at: ListGroupsUpdatedAt | Unset = UNSET,
    name: ListGroupsName | Unset = UNSET,
    description: ListGroupsDescription | Unset = UNSET,
    created_by: ListGroupsCreatedBy | Unset = UNSET,
    source: ListGroupsSource | Unset = UNSET,
) -> Response[ErrorData | GroupListResponse]:
    """List groups

     Retrieve list of groups with visibility filtering.

    Users with ``group:read:any`` see all groups.
    Users with ``group:read:self`` see only their own groups.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListGroupsId | Unset):
        created_at (ListGroupsCreatedAt | Unset):
        updated_at (ListGroupsUpdatedAt | Unset):
        name (ListGroupsName | Unset):
        description (ListGroupsDescription | Unset):
        created_by (ListGroupsCreatedBy | Unset):
        source (ListGroupsSource | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | GroupListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        description=description,
        created_by=created_by,
        source=source,
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
    id: ListGroupsId | Unset = UNSET,
    created_at: ListGroupsCreatedAt | Unset = UNSET,
    updated_at: ListGroupsUpdatedAt | Unset = UNSET,
    name: ListGroupsName | Unset = UNSET,
    description: ListGroupsDescription | Unset = UNSET,
    created_by: ListGroupsCreatedBy | Unset = UNSET,
    source: ListGroupsSource | Unset = UNSET,
) -> ErrorData | GroupListResponse | None:
    """List groups

     Retrieve list of groups with visibility filtering.

    Users with ``group:read:any`` see all groups.
    Users with ``group:read:self`` see only their own groups.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListGroupsId | Unset):
        created_at (ListGroupsCreatedAt | Unset):
        updated_at (ListGroupsUpdatedAt | Unset):
        name (ListGroupsName | Unset):
        description (ListGroupsDescription | Unset):
        created_by (ListGroupsCreatedBy | Unset):
        source (ListGroupsSource | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | GroupListResponse
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
            name=name,
            description=description,
            created_by=created_by,
            source=source,
        )
    ).parsed
