from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.list_roles_created_at import ListRolesCreatedAt
from ...models.list_roles_description import ListRolesDescription
from ...models.list_roles_id import ListRolesId
from ...models.list_roles_is_builtin import ListRolesIsBuiltin
from ...models.list_roles_name import ListRolesName
from ...models.list_roles_project_id import ListRolesProjectId
from ...models.list_roles_scope import ListRolesScope
from ...models.list_roles_updated_at import ListRolesUpdatedAt
from ...models.role_list_response import RoleListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListRolesId | Unset = UNSET,
    created_at: ListRolesCreatedAt | Unset = UNSET,
    updated_at: ListRolesUpdatedAt | Unset = UNSET,
    name: ListRolesName | Unset = UNSET,
    description: ListRolesDescription | Unset = UNSET,
    is_builtin: ListRolesIsBuiltin | Unset = UNSET,
    project_id: ListRolesProjectId | Unset = UNSET,
    scope: ListRolesScope | Unset = UNSET,
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

    json_is_builtin: dict[str, Any] | Unset = UNSET
    if not isinstance(is_builtin, Unset):
        json_is_builtin = is_builtin.to_dict()
    if not isinstance(json_is_builtin, Unset):
        params.update(json_is_builtin)

    json_project_id: dict[str, Any] | Unset = UNSET
    if not isinstance(project_id, Unset):
        json_project_id = project_id.to_dict()
    if not isinstance(json_project_id, Unset):
        params.update(json_project_id)

    json_scope: dict[str, Any] | Unset = UNSET
    if not isinstance(scope, Unset):
        json_scope = scope.to_dict()
    if not isinstance(json_scope, Unset):
        params.update(json_scope)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/roles",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | RoleListResponse | None:
    if response.status_code == 200:
        response_200 = RoleListResponse.from_dict(response.json())

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
) -> Response[ErrorData | RoleListResponse]:
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
    id: ListRolesId | Unset = UNSET,
    created_at: ListRolesCreatedAt | Unset = UNSET,
    updated_at: ListRolesUpdatedAt | Unset = UNSET,
    name: ListRolesName | Unset = UNSET,
    description: ListRolesDescription | Unset = UNSET,
    is_builtin: ListRolesIsBuiltin | Unset = UNSET,
    project_id: ListRolesProjectId | Unset = UNSET,
    scope: ListRolesScope | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | RoleListResponse]:
    """List roles

     List roles with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListRolesId | Unset):
        created_at (ListRolesCreatedAt | Unset):
        updated_at (ListRolesUpdatedAt | Unset):
        name (ListRolesName | Unset):
        description (ListRolesDescription | Unset):
        is_builtin (ListRolesIsBuiltin | Unset):
        project_id (ListRolesProjectId | Unset):
        scope (ListRolesScope | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | RoleListResponse]
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
        is_builtin=is_builtin,
        project_id=project_id,
        scope=scope,
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
    id: ListRolesId | Unset = UNSET,
    created_at: ListRolesCreatedAt | Unset = UNSET,
    updated_at: ListRolesUpdatedAt | Unset = UNSET,
    name: ListRolesName | Unset = UNSET,
    description: ListRolesDescription | Unset = UNSET,
    is_builtin: ListRolesIsBuiltin | Unset = UNSET,
    project_id: ListRolesProjectId | Unset = UNSET,
    scope: ListRolesScope | Unset = UNSET,
) -> ErrorData | RoleListResponse | None:
    """List roles

     List roles with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListRolesId | Unset):
        created_at (ListRolesCreatedAt | Unset):
        updated_at (ListRolesUpdatedAt | Unset):
        name (ListRolesName | Unset):
        description (ListRolesDescription | Unset):
        is_builtin (ListRolesIsBuiltin | Unset):
        project_id (ListRolesProjectId | Unset):
        scope (ListRolesScope | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | RoleListResponse
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
        is_builtin=is_builtin,
        project_id=project_id,
        scope=scope,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListRolesId | Unset = UNSET,
    created_at: ListRolesCreatedAt | Unset = UNSET,
    updated_at: ListRolesUpdatedAt | Unset = UNSET,
    name: ListRolesName | Unset = UNSET,
    description: ListRolesDescription | Unset = UNSET,
    is_builtin: ListRolesIsBuiltin | Unset = UNSET,
    project_id: ListRolesProjectId | Unset = UNSET,
    scope: ListRolesScope | Unset = UNSET,
) -> Response[ErrorData | RoleListResponse]:
    """List roles

     List roles with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListRolesId | Unset):
        created_at (ListRolesCreatedAt | Unset):
        updated_at (ListRolesUpdatedAt | Unset):
        name (ListRolesName | Unset):
        description (ListRolesDescription | Unset):
        is_builtin (ListRolesIsBuiltin | Unset):
        project_id (ListRolesProjectId | Unset):
        scope (ListRolesScope | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | RoleListResponse]
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
        is_builtin=is_builtin,
        project_id=project_id,
        scope=scope,
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
    id: ListRolesId | Unset = UNSET,
    created_at: ListRolesCreatedAt | Unset = UNSET,
    updated_at: ListRolesUpdatedAt | Unset = UNSET,
    name: ListRolesName | Unset = UNSET,
    description: ListRolesDescription | Unset = UNSET,
    is_builtin: ListRolesIsBuiltin | Unset = UNSET,
    project_id: ListRolesProjectId | Unset = UNSET,
    scope: ListRolesScope | Unset = UNSET,
) -> ErrorData | RoleListResponse | None:
    """List roles

     List roles with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListRolesId | Unset):
        created_at (ListRolesCreatedAt | Unset):
        updated_at (ListRolesUpdatedAt | Unset):
        name (ListRolesName | Unset):
        description (ListRolesDescription | Unset):
        is_builtin (ListRolesIsBuiltin | Unset):
        project_id (ListRolesProjectId | Unset):
        scope (ListRolesScope | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | RoleListResponse
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
            is_builtin=is_builtin,
            project_id=project_id,
            scope=scope,
        )
    ).parsed
