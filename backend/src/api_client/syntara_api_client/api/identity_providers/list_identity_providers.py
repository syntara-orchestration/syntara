from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.identity_provider_list_response import IdentityProviderListResponse
from ...models.list_identity_providers_created_at import ListIdentityProvidersCreatedAt
from ...models.list_identity_providers_description import ListIdentityProvidersDescription
from ...models.list_identity_providers_enabled import ListIdentityProvidersEnabled
from ...models.list_identity_providers_id import ListIdentityProvidersId
from ...models.list_identity_providers_name import ListIdentityProvidersName
from ...models.list_identity_providers_updated_at import ListIdentityProvidersUpdatedAt
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListIdentityProvidersId | Unset = UNSET,
    created_at: ListIdentityProvidersCreatedAt | Unset = UNSET,
    updated_at: ListIdentityProvidersUpdatedAt | Unset = UNSET,
    name: ListIdentityProvidersName | Unset = UNSET,
    description: ListIdentityProvidersDescription | Unset = UNSET,
    enabled: ListIdentityProvidersEnabled | Unset = UNSET,
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

    json_enabled: dict[str, Any] | Unset = UNSET
    if not isinstance(enabled, Unset):
        json_enabled = enabled.to_dict()
    if not isinstance(json_enabled, Unset):
        params.update(json_enabled)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/identity_providers",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | IdentityProviderListResponse | None:
    if response.status_code == 200:
        response_200 = IdentityProviderListResponse.from_dict(response.json())

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
) -> Response[ErrorData | IdentityProviderListResponse]:
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
    id: ListIdentityProvidersId | Unset = UNSET,
    created_at: ListIdentityProvidersCreatedAt | Unset = UNSET,
    updated_at: ListIdentityProvidersUpdatedAt | Unset = UNSET,
    name: ListIdentityProvidersName | Unset = UNSET,
    description: ListIdentityProvidersDescription | Unset = UNSET,
    enabled: ListIdentityProvidersEnabled | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | IdentityProviderListResponse]:
    """List identity providers

     List identity providers with filtering, sorting, and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListIdentityProvidersId | Unset):
        created_at (ListIdentityProvidersCreatedAt | Unset):
        updated_at (ListIdentityProvidersUpdatedAt | Unset):
        name (ListIdentityProvidersName | Unset):
        description (ListIdentityProvidersDescription | Unset):
        enabled (ListIdentityProvidersEnabled | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | IdentityProviderListResponse]
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
        enabled=enabled,
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
    id: ListIdentityProvidersId | Unset = UNSET,
    created_at: ListIdentityProvidersCreatedAt | Unset = UNSET,
    updated_at: ListIdentityProvidersUpdatedAt | Unset = UNSET,
    name: ListIdentityProvidersName | Unset = UNSET,
    description: ListIdentityProvidersDescription | Unset = UNSET,
    enabled: ListIdentityProvidersEnabled | Unset = UNSET,
) -> ErrorData | IdentityProviderListResponse | None:
    """List identity providers

     List identity providers with filtering, sorting, and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListIdentityProvidersId | Unset):
        created_at (ListIdentityProvidersCreatedAt | Unset):
        updated_at (ListIdentityProvidersUpdatedAt | Unset):
        name (ListIdentityProvidersName | Unset):
        description (ListIdentityProvidersDescription | Unset):
        enabled (ListIdentityProvidersEnabled | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | IdentityProviderListResponse
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
        enabled=enabled,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListIdentityProvidersId | Unset = UNSET,
    created_at: ListIdentityProvidersCreatedAt | Unset = UNSET,
    updated_at: ListIdentityProvidersUpdatedAt | Unset = UNSET,
    name: ListIdentityProvidersName | Unset = UNSET,
    description: ListIdentityProvidersDescription | Unset = UNSET,
    enabled: ListIdentityProvidersEnabled | Unset = UNSET,
) -> Response[ErrorData | IdentityProviderListResponse]:
    """List identity providers

     List identity providers with filtering, sorting, and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListIdentityProvidersId | Unset):
        created_at (ListIdentityProvidersCreatedAt | Unset):
        updated_at (ListIdentityProvidersUpdatedAt | Unset):
        name (ListIdentityProvidersName | Unset):
        description (ListIdentityProvidersDescription | Unset):
        enabled (ListIdentityProvidersEnabled | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | IdentityProviderListResponse]
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
        enabled=enabled,
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
    id: ListIdentityProvidersId | Unset = UNSET,
    created_at: ListIdentityProvidersCreatedAt | Unset = UNSET,
    updated_at: ListIdentityProvidersUpdatedAt | Unset = UNSET,
    name: ListIdentityProvidersName | Unset = UNSET,
    description: ListIdentityProvidersDescription | Unset = UNSET,
    enabled: ListIdentityProvidersEnabled | Unset = UNSET,
) -> ErrorData | IdentityProviderListResponse | None:
    """List identity providers

     List identity providers with filtering, sorting, and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListIdentityProvidersId | Unset):
        created_at (ListIdentityProvidersCreatedAt | Unset):
        updated_at (ListIdentityProvidersUpdatedAt | Unset):
        name (ListIdentityProvidersName | Unset):
        description (ListIdentityProvidersDescription | Unset):
        enabled (ListIdentityProvidersEnabled | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | IdentityProviderListResponse
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
            enabled=enabled,
        )
    ).parsed
