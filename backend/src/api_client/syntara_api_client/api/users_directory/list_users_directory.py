from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.list_users_directory_auth_type import ListUsersDirectoryAuthType
from ...models.list_users_directory_created_at import ListUsersDirectoryCreatedAt
from ...models.list_users_directory_email import ListUsersDirectoryEmail
from ...models.list_users_directory_first_name import ListUsersDirectoryFirstName
from ...models.list_users_directory_id import ListUsersDirectoryId
from ...models.list_users_directory_is_enabled import ListUsersDirectoryIsEnabled
from ...models.list_users_directory_last_name import ListUsersDirectoryLastName
from ...models.list_users_directory_updated_at import ListUsersDirectoryUpdatedAt
from ...models.list_users_directory_username import ListUsersDirectoryUsername
from ...models.resources_response_user_directory_entry import ResourcesResponseUserDirectoryEntry
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListUsersDirectoryId | Unset = UNSET,
    created_at: ListUsersDirectoryCreatedAt | Unset = UNSET,
    updated_at: ListUsersDirectoryUpdatedAt | Unset = UNSET,
    username: ListUsersDirectoryUsername | Unset = UNSET,
    email: ListUsersDirectoryEmail | Unset = UNSET,
    first_name: ListUsersDirectoryFirstName | Unset = UNSET,
    last_name: ListUsersDirectoryLastName | Unset = UNSET,
    is_enabled: ListUsersDirectoryIsEnabled | Unset = UNSET,
    auth_type: ListUsersDirectoryAuthType | Unset = UNSET,
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

    json_username: dict[str, Any] | Unset = UNSET
    if not isinstance(username, Unset):
        json_username = username.to_dict()
    if not isinstance(json_username, Unset):
        params.update(json_username)

    json_email: dict[str, Any] | Unset = UNSET
    if not isinstance(email, Unset):
        json_email = email.to_dict()
    if not isinstance(json_email, Unset):
        params.update(json_email)

    json_first_name: dict[str, Any] | Unset = UNSET
    if not isinstance(first_name, Unset):
        json_first_name = first_name.to_dict()
    if not isinstance(json_first_name, Unset):
        params.update(json_first_name)

    json_last_name: dict[str, Any] | Unset = UNSET
    if not isinstance(last_name, Unset):
        json_last_name = last_name.to_dict()
    if not isinstance(json_last_name, Unset):
        params.update(json_last_name)

    json_is_enabled: dict[str, Any] | Unset = UNSET
    if not isinstance(is_enabled, Unset):
        json_is_enabled = is_enabled.to_dict()
    if not isinstance(json_is_enabled, Unset):
        params.update(json_is_enabled)

    json_auth_type: dict[str, Any] | Unset = UNSET
    if not isinstance(auth_type, Unset):
        json_auth_type = auth_type.to_dict()
    if not isinstance(json_auth_type, Unset):
        params.update(json_auth_type)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/users/directory",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ResourcesResponseUserDirectoryEntry | None:
    if response.status_code == 200:
        response_200 = ResourcesResponseUserDirectoryEntry.from_dict(response.json())

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
) -> Response[ErrorData | ResourcesResponseUserDirectoryEntry]:
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
    id: ListUsersDirectoryId | Unset = UNSET,
    created_at: ListUsersDirectoryCreatedAt | Unset = UNSET,
    updated_at: ListUsersDirectoryUpdatedAt | Unset = UNSET,
    username: ListUsersDirectoryUsername | Unset = UNSET,
    email: ListUsersDirectoryEmail | Unset = UNSET,
    first_name: ListUsersDirectoryFirstName | Unset = UNSET,
    last_name: ListUsersDirectoryLastName | Unset = UNSET,
    is_enabled: ListUsersDirectoryIsEnabled | Unset = UNSET,
    auth_type: ListUsersDirectoryAuthType | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | ResourcesResponseUserDirectoryEntry]:
    """List users directory

     Return a lightweight directory of users (id + username only).

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListUsersDirectoryId | Unset):
        created_at (ListUsersDirectoryCreatedAt | Unset):
        updated_at (ListUsersDirectoryUpdatedAt | Unset):
        username (ListUsersDirectoryUsername | Unset):
        email (ListUsersDirectoryEmail | Unset):
        first_name (ListUsersDirectoryFirstName | Unset):
        last_name (ListUsersDirectoryLastName | Unset):
        is_enabled (ListUsersDirectoryIsEnabled | Unset):
        auth_type (ListUsersDirectoryAuthType | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ResourcesResponseUserDirectoryEntry]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        is_enabled=is_enabled,
        auth_type=auth_type,
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
    id: ListUsersDirectoryId | Unset = UNSET,
    created_at: ListUsersDirectoryCreatedAt | Unset = UNSET,
    updated_at: ListUsersDirectoryUpdatedAt | Unset = UNSET,
    username: ListUsersDirectoryUsername | Unset = UNSET,
    email: ListUsersDirectoryEmail | Unset = UNSET,
    first_name: ListUsersDirectoryFirstName | Unset = UNSET,
    last_name: ListUsersDirectoryLastName | Unset = UNSET,
    is_enabled: ListUsersDirectoryIsEnabled | Unset = UNSET,
    auth_type: ListUsersDirectoryAuthType | Unset = UNSET,
) -> ErrorData | ResourcesResponseUserDirectoryEntry | None:
    """List users directory

     Return a lightweight directory of users (id + username only).

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListUsersDirectoryId | Unset):
        created_at (ListUsersDirectoryCreatedAt | Unset):
        updated_at (ListUsersDirectoryUpdatedAt | Unset):
        username (ListUsersDirectoryUsername | Unset):
        email (ListUsersDirectoryEmail | Unset):
        first_name (ListUsersDirectoryFirstName | Unset):
        last_name (ListUsersDirectoryLastName | Unset):
        is_enabled (ListUsersDirectoryIsEnabled | Unset):
        auth_type (ListUsersDirectoryAuthType | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ResourcesResponseUserDirectoryEntry
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
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        is_enabled=is_enabled,
        auth_type=auth_type,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListUsersDirectoryId | Unset = UNSET,
    created_at: ListUsersDirectoryCreatedAt | Unset = UNSET,
    updated_at: ListUsersDirectoryUpdatedAt | Unset = UNSET,
    username: ListUsersDirectoryUsername | Unset = UNSET,
    email: ListUsersDirectoryEmail | Unset = UNSET,
    first_name: ListUsersDirectoryFirstName | Unset = UNSET,
    last_name: ListUsersDirectoryLastName | Unset = UNSET,
    is_enabled: ListUsersDirectoryIsEnabled | Unset = UNSET,
    auth_type: ListUsersDirectoryAuthType | Unset = UNSET,
) -> Response[ErrorData | ResourcesResponseUserDirectoryEntry]:
    """List users directory

     Return a lightweight directory of users (id + username only).

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListUsersDirectoryId | Unset):
        created_at (ListUsersDirectoryCreatedAt | Unset):
        updated_at (ListUsersDirectoryUpdatedAt | Unset):
        username (ListUsersDirectoryUsername | Unset):
        email (ListUsersDirectoryEmail | Unset):
        first_name (ListUsersDirectoryFirstName | Unset):
        last_name (ListUsersDirectoryLastName | Unset):
        is_enabled (ListUsersDirectoryIsEnabled | Unset):
        auth_type (ListUsersDirectoryAuthType | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ResourcesResponseUserDirectoryEntry]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        is_enabled=is_enabled,
        auth_type=auth_type,
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
    id: ListUsersDirectoryId | Unset = UNSET,
    created_at: ListUsersDirectoryCreatedAt | Unset = UNSET,
    updated_at: ListUsersDirectoryUpdatedAt | Unset = UNSET,
    username: ListUsersDirectoryUsername | Unset = UNSET,
    email: ListUsersDirectoryEmail | Unset = UNSET,
    first_name: ListUsersDirectoryFirstName | Unset = UNSET,
    last_name: ListUsersDirectoryLastName | Unset = UNSET,
    is_enabled: ListUsersDirectoryIsEnabled | Unset = UNSET,
    auth_type: ListUsersDirectoryAuthType | Unset = UNSET,
) -> ErrorData | ResourcesResponseUserDirectoryEntry | None:
    """List users directory

     Return a lightweight directory of users (id + username only).

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListUsersDirectoryId | Unset):
        created_at (ListUsersDirectoryCreatedAt | Unset):
        updated_at (ListUsersDirectoryUpdatedAt | Unset):
        username (ListUsersDirectoryUsername | Unset):
        email (ListUsersDirectoryEmail | Unset):
        first_name (ListUsersDirectoryFirstName | Unset):
        last_name (ListUsersDirectoryLastName | Unset):
        is_enabled (ListUsersDirectoryIsEnabled | Unset):
        auth_type (ListUsersDirectoryAuthType | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ResourcesResponseUserDirectoryEntry
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
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_enabled=is_enabled,
            auth_type=auth_type,
        )
    ).parsed
