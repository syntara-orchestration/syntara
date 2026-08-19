from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.list_service_accounts_created_at import ListServiceAccountsCreatedAt
from ...models.list_service_accounts_created_by import ListServiceAccountsCreatedBy
from ...models.list_service_accounts_description import ListServiceAccountsDescription
from ...models.list_service_accounts_id import ListServiceAccountsId
from ...models.list_service_accounts_last_authenticated_at import ListServiceAccountsLastAuthenticatedAt
from ...models.list_service_accounts_name import ListServiceAccountsName
from ...models.list_service_accounts_project_id import ListServiceAccountsProjectId
from ...models.list_service_accounts_status import ListServiceAccountsStatus
from ...models.list_service_accounts_updated_at import ListServiceAccountsUpdatedAt
from ...models.list_service_accounts_updated_by import ListServiceAccountsUpdatedBy
from ...models.service_account_list_response import ServiceAccountListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListServiceAccountsId | Unset = UNSET,
    created_at: ListServiceAccountsCreatedAt | Unset = UNSET,
    updated_at: ListServiceAccountsUpdatedAt | Unset = UNSET,
    name: ListServiceAccountsName | Unset = UNSET,
    description: ListServiceAccountsDescription | Unset = UNSET,
    created_by: ListServiceAccountsCreatedBy | Unset = UNSET,
    updated_by: ListServiceAccountsUpdatedBy | Unset = UNSET,
    status: ListServiceAccountsStatus | Unset = UNSET,
    project_id: ListServiceAccountsProjectId | Unset = UNSET,
    last_authenticated_at: ListServiceAccountsLastAuthenticatedAt | Unset = UNSET,
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

    json_updated_by: dict[str, Any] | Unset = UNSET
    if not isinstance(updated_by, Unset):
        json_updated_by = updated_by.to_dict()
    if not isinstance(json_updated_by, Unset):
        params.update(json_updated_by)

    json_status: dict[str, Any] | Unset = UNSET
    if not isinstance(status, Unset):
        json_status = status.to_dict()
    if not isinstance(json_status, Unset):
        params.update(json_status)

    json_project_id: dict[str, Any] | Unset = UNSET
    if not isinstance(project_id, Unset):
        json_project_id = project_id.to_dict()
    if not isinstance(json_project_id, Unset):
        params.update(json_project_id)

    json_last_authenticated_at: dict[str, Any] | Unset = UNSET
    if not isinstance(last_authenticated_at, Unset):
        json_last_authenticated_at = last_authenticated_at.to_dict()
    if not isinstance(json_last_authenticated_at, Unset):
        params.update(json_last_authenticated_at)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/service_accounts",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ServiceAccountListResponse | None:
    if response.status_code == 200:
        response_200 = ServiceAccountListResponse.from_dict(response.json())

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
) -> Response[ErrorData | ServiceAccountListResponse]:
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
    id: ListServiceAccountsId | Unset = UNSET,
    created_at: ListServiceAccountsCreatedAt | Unset = UNSET,
    updated_at: ListServiceAccountsUpdatedAt | Unset = UNSET,
    name: ListServiceAccountsName | Unset = UNSET,
    description: ListServiceAccountsDescription | Unset = UNSET,
    created_by: ListServiceAccountsCreatedBy | Unset = UNSET,
    updated_by: ListServiceAccountsUpdatedBy | Unset = UNSET,
    status: ListServiceAccountsStatus | Unset = UNSET,
    project_id: ListServiceAccountsProjectId | Unset = UNSET,
    last_authenticated_at: ListServiceAccountsLastAuthenticatedAt | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | ServiceAccountListResponse]:
    """List service accounts

     List service accounts with project-scoped visibility and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListServiceAccountsId | Unset):
        created_at (ListServiceAccountsCreatedAt | Unset):
        updated_at (ListServiceAccountsUpdatedAt | Unset):
        name (ListServiceAccountsName | Unset):
        description (ListServiceAccountsDescription | Unset):
        created_by (ListServiceAccountsCreatedBy | Unset):
        updated_by (ListServiceAccountsUpdatedBy | Unset):
        status (ListServiceAccountsStatus | Unset):
        project_id (ListServiceAccountsProjectId | Unset):
        last_authenticated_at (ListServiceAccountsLastAuthenticatedAt | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ServiceAccountListResponse]
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
        updated_by=updated_by,
        status=status,
        project_id=project_id,
        last_authenticated_at=last_authenticated_at,
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
    id: ListServiceAccountsId | Unset = UNSET,
    created_at: ListServiceAccountsCreatedAt | Unset = UNSET,
    updated_at: ListServiceAccountsUpdatedAt | Unset = UNSET,
    name: ListServiceAccountsName | Unset = UNSET,
    description: ListServiceAccountsDescription | Unset = UNSET,
    created_by: ListServiceAccountsCreatedBy | Unset = UNSET,
    updated_by: ListServiceAccountsUpdatedBy | Unset = UNSET,
    status: ListServiceAccountsStatus | Unset = UNSET,
    project_id: ListServiceAccountsProjectId | Unset = UNSET,
    last_authenticated_at: ListServiceAccountsLastAuthenticatedAt | Unset = UNSET,
) -> ErrorData | ServiceAccountListResponse | None:
    """List service accounts

     List service accounts with project-scoped visibility and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListServiceAccountsId | Unset):
        created_at (ListServiceAccountsCreatedAt | Unset):
        updated_at (ListServiceAccountsUpdatedAt | Unset):
        name (ListServiceAccountsName | Unset):
        description (ListServiceAccountsDescription | Unset):
        created_by (ListServiceAccountsCreatedBy | Unset):
        updated_by (ListServiceAccountsUpdatedBy | Unset):
        status (ListServiceAccountsStatus | Unset):
        project_id (ListServiceAccountsProjectId | Unset):
        last_authenticated_at (ListServiceAccountsLastAuthenticatedAt | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ServiceAccountListResponse
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
        updated_by=updated_by,
        status=status,
        project_id=project_id,
        last_authenticated_at=last_authenticated_at,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListServiceAccountsId | Unset = UNSET,
    created_at: ListServiceAccountsCreatedAt | Unset = UNSET,
    updated_at: ListServiceAccountsUpdatedAt | Unset = UNSET,
    name: ListServiceAccountsName | Unset = UNSET,
    description: ListServiceAccountsDescription | Unset = UNSET,
    created_by: ListServiceAccountsCreatedBy | Unset = UNSET,
    updated_by: ListServiceAccountsUpdatedBy | Unset = UNSET,
    status: ListServiceAccountsStatus | Unset = UNSET,
    project_id: ListServiceAccountsProjectId | Unset = UNSET,
    last_authenticated_at: ListServiceAccountsLastAuthenticatedAt | Unset = UNSET,
) -> Response[ErrorData | ServiceAccountListResponse]:
    """List service accounts

     List service accounts with project-scoped visibility and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListServiceAccountsId | Unset):
        created_at (ListServiceAccountsCreatedAt | Unset):
        updated_at (ListServiceAccountsUpdatedAt | Unset):
        name (ListServiceAccountsName | Unset):
        description (ListServiceAccountsDescription | Unset):
        created_by (ListServiceAccountsCreatedBy | Unset):
        updated_by (ListServiceAccountsUpdatedBy | Unset):
        status (ListServiceAccountsStatus | Unset):
        project_id (ListServiceAccountsProjectId | Unset):
        last_authenticated_at (ListServiceAccountsLastAuthenticatedAt | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ServiceAccountListResponse]
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
        updated_by=updated_by,
        status=status,
        project_id=project_id,
        last_authenticated_at=last_authenticated_at,
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
    id: ListServiceAccountsId | Unset = UNSET,
    created_at: ListServiceAccountsCreatedAt | Unset = UNSET,
    updated_at: ListServiceAccountsUpdatedAt | Unset = UNSET,
    name: ListServiceAccountsName | Unset = UNSET,
    description: ListServiceAccountsDescription | Unset = UNSET,
    created_by: ListServiceAccountsCreatedBy | Unset = UNSET,
    updated_by: ListServiceAccountsUpdatedBy | Unset = UNSET,
    status: ListServiceAccountsStatus | Unset = UNSET,
    project_id: ListServiceAccountsProjectId | Unset = UNSET,
    last_authenticated_at: ListServiceAccountsLastAuthenticatedAt | Unset = UNSET,
) -> ErrorData | ServiceAccountListResponse | None:
    """List service accounts

     List service accounts with project-scoped visibility and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListServiceAccountsId | Unset):
        created_at (ListServiceAccountsCreatedAt | Unset):
        updated_at (ListServiceAccountsUpdatedAt | Unset):
        name (ListServiceAccountsName | Unset):
        description (ListServiceAccountsDescription | Unset):
        created_by (ListServiceAccountsCreatedBy | Unset):
        updated_by (ListServiceAccountsUpdatedBy | Unset):
        status (ListServiceAccountsStatus | Unset):
        project_id (ListServiceAccountsProjectId | Unset):
        last_authenticated_at (ListServiceAccountsLastAuthenticatedAt | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ServiceAccountListResponse
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
            updated_by=updated_by,
            status=status,
            project_id=project_id,
            last_authenticated_at=last_authenticated_at,
        )
    ).parsed
