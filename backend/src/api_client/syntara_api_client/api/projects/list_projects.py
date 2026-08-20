from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.list_projects_created_at import ListProjectsCreatedAt
from ...models.list_projects_deleted_at import ListProjectsDeletedAt
from ...models.list_projects_deleted_by import ListProjectsDeletedBy
from ...models.list_projects_description import ListProjectsDescription
from ...models.list_projects_id import ListProjectsId
from ...models.list_projects_is_builtin import ListProjectsIsBuiltin
from ...models.list_projects_is_default import ListProjectsIsDefault
from ...models.list_projects_name import ListProjectsName
from ...models.list_projects_updated_at import ListProjectsUpdatedAt
from ...models.project_list_response import ProjectListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListProjectsId | Unset = UNSET,
    created_at: ListProjectsCreatedAt | Unset = UNSET,
    updated_at: ListProjectsUpdatedAt | Unset = UNSET,
    name: ListProjectsName | Unset = UNSET,
    description: ListProjectsDescription | Unset = UNSET,
    deleted_at: ListProjectsDeletedAt | Unset = UNSET,
    deleted_by: ListProjectsDeletedBy | Unset = UNSET,
    is_default: ListProjectsIsDefault | Unset = UNSET,
    is_builtin: ListProjectsIsBuiltin | Unset = UNSET,
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

    json_is_default: dict[str, Any] | Unset = UNSET
    if not isinstance(is_default, Unset):
        json_is_default = is_default.to_dict()
    if not isinstance(json_is_default, Unset):
        params.update(json_is_default)

    json_is_builtin: dict[str, Any] | Unset = UNSET
    if not isinstance(is_builtin, Unset):
        json_is_builtin = is_builtin.to_dict()
    if not isinstance(json_is_builtin, Unset):
        params.update(json_is_builtin)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/projects",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ProjectListResponse | None:
    if response.status_code == 200:
        response_200 = ProjectListResponse.from_dict(response.json())

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
) -> Response[ErrorData | ProjectListResponse]:
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
    id: ListProjectsId | Unset = UNSET,
    created_at: ListProjectsCreatedAt | Unset = UNSET,
    updated_at: ListProjectsUpdatedAt | Unset = UNSET,
    name: ListProjectsName | Unset = UNSET,
    description: ListProjectsDescription | Unset = UNSET,
    deleted_at: ListProjectsDeletedAt | Unset = UNSET,
    deleted_by: ListProjectsDeletedBy | Unset = UNSET,
    is_default: ListProjectsIsDefault | Unset = UNSET,
    is_builtin: ListProjectsIsBuiltin | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | ProjectListResponse]:
    """List projects

     List projects the current user has read access to.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListProjectsId | Unset):
        created_at (ListProjectsCreatedAt | Unset):
        updated_at (ListProjectsUpdatedAt | Unset):
        name (ListProjectsName | Unset):
        description (ListProjectsDescription | Unset):
        deleted_at (ListProjectsDeletedAt | Unset):
        deleted_by (ListProjectsDeletedBy | Unset):
        is_default (ListProjectsIsDefault | Unset):
        is_builtin (ListProjectsIsBuiltin | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ProjectListResponse]
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
        deleted_at=deleted_at,
        deleted_by=deleted_by,
        is_default=is_default,
        is_builtin=is_builtin,
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
    id: ListProjectsId | Unset = UNSET,
    created_at: ListProjectsCreatedAt | Unset = UNSET,
    updated_at: ListProjectsUpdatedAt | Unset = UNSET,
    name: ListProjectsName | Unset = UNSET,
    description: ListProjectsDescription | Unset = UNSET,
    deleted_at: ListProjectsDeletedAt | Unset = UNSET,
    deleted_by: ListProjectsDeletedBy | Unset = UNSET,
    is_default: ListProjectsIsDefault | Unset = UNSET,
    is_builtin: ListProjectsIsBuiltin | Unset = UNSET,
) -> ErrorData | ProjectListResponse | None:
    """List projects

     List projects the current user has read access to.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListProjectsId | Unset):
        created_at (ListProjectsCreatedAt | Unset):
        updated_at (ListProjectsUpdatedAt | Unset):
        name (ListProjectsName | Unset):
        description (ListProjectsDescription | Unset):
        deleted_at (ListProjectsDeletedAt | Unset):
        deleted_by (ListProjectsDeletedBy | Unset):
        is_default (ListProjectsIsDefault | Unset):
        is_builtin (ListProjectsIsBuiltin | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ProjectListResponse
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
        deleted_at=deleted_at,
        deleted_by=deleted_by,
        is_default=is_default,
        is_builtin=is_builtin,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListProjectsId | Unset = UNSET,
    created_at: ListProjectsCreatedAt | Unset = UNSET,
    updated_at: ListProjectsUpdatedAt | Unset = UNSET,
    name: ListProjectsName | Unset = UNSET,
    description: ListProjectsDescription | Unset = UNSET,
    deleted_at: ListProjectsDeletedAt | Unset = UNSET,
    deleted_by: ListProjectsDeletedBy | Unset = UNSET,
    is_default: ListProjectsIsDefault | Unset = UNSET,
    is_builtin: ListProjectsIsBuiltin | Unset = UNSET,
) -> Response[ErrorData | ProjectListResponse]:
    """List projects

     List projects the current user has read access to.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListProjectsId | Unset):
        created_at (ListProjectsCreatedAt | Unset):
        updated_at (ListProjectsUpdatedAt | Unset):
        name (ListProjectsName | Unset):
        description (ListProjectsDescription | Unset):
        deleted_at (ListProjectsDeletedAt | Unset):
        deleted_by (ListProjectsDeletedBy | Unset):
        is_default (ListProjectsIsDefault | Unset):
        is_builtin (ListProjectsIsBuiltin | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ProjectListResponse]
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
        deleted_at=deleted_at,
        deleted_by=deleted_by,
        is_default=is_default,
        is_builtin=is_builtin,
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
    id: ListProjectsId | Unset = UNSET,
    created_at: ListProjectsCreatedAt | Unset = UNSET,
    updated_at: ListProjectsUpdatedAt | Unset = UNSET,
    name: ListProjectsName | Unset = UNSET,
    description: ListProjectsDescription | Unset = UNSET,
    deleted_at: ListProjectsDeletedAt | Unset = UNSET,
    deleted_by: ListProjectsDeletedBy | Unset = UNSET,
    is_default: ListProjectsIsDefault | Unset = UNSET,
    is_builtin: ListProjectsIsBuiltin | Unset = UNSET,
) -> ErrorData | ProjectListResponse | None:
    """List projects

     List projects the current user has read access to.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListProjectsId | Unset):
        created_at (ListProjectsCreatedAt | Unset):
        updated_at (ListProjectsUpdatedAt | Unset):
        name (ListProjectsName | Unset):
        description (ListProjectsDescription | Unset):
        deleted_at (ListProjectsDeletedAt | Unset):
        deleted_by (ListProjectsDeletedBy | Unset):
        is_default (ListProjectsIsDefault | Unset):
        is_builtin (ListProjectsIsBuiltin | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ProjectListResponse
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
            deleted_at=deleted_at,
            deleted_by=deleted_by,
            is_default=is_default,
            is_builtin=is_builtin,
        )
    ).parsed
