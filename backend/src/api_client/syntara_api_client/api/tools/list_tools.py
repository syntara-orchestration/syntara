from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.list_tools_created_at import ListToolsCreatedAt
from ...models.list_tools_created_by import ListToolsCreatedBy
from ...models.list_tools_description import ListToolsDescription
from ...models.list_tools_enabled import ListToolsEnabled
from ...models.list_tools_id import ListToolsId
from ...models.list_tools_integration_id import ListToolsIntegrationId
from ...models.list_tools_name import ListToolsName
from ...models.list_tools_namespaced_name import ListToolsNamespacedName
from ...models.list_tools_status import ListToolsStatus
from ...models.list_tools_updated_at import ListToolsUpdatedAt
from ...models.list_tools_updated_by import ListToolsUpdatedBy
from ...models.tool_list_response import ToolListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListToolsId | Unset = UNSET,
    created_at: ListToolsCreatedAt | Unset = UNSET,
    updated_at: ListToolsUpdatedAt | Unset = UNSET,
    name: ListToolsName | Unset = UNSET,
    description: ListToolsDescription | Unset = UNSET,
    created_by: ListToolsCreatedBy | Unset = UNSET,
    updated_by: ListToolsUpdatedBy | Unset = UNSET,
    enabled: ListToolsEnabled | Unset = UNSET,
    status: ListToolsStatus | Unset = UNSET,
    integration_id: ListToolsIntegrationId | Unset = UNSET,
    namespaced_name: ListToolsNamespacedName | Unset = UNSET,
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

    json_enabled: dict[str, Any] | Unset = UNSET
    if not isinstance(enabled, Unset):
        json_enabled = enabled.to_dict()
    if not isinstance(json_enabled, Unset):
        params.update(json_enabled)

    json_status: dict[str, Any] | Unset = UNSET
    if not isinstance(status, Unset):
        json_status = status.to_dict()
    if not isinstance(json_status, Unset):
        params.update(json_status)

    json_integration_id: dict[str, Any] | Unset = UNSET
    if not isinstance(integration_id, Unset):
        json_integration_id = integration_id.to_dict()
    if not isinstance(json_integration_id, Unset):
        params.update(json_integration_id)

    json_namespaced_name: dict[str, Any] | Unset = UNSET
    if not isinstance(namespaced_name, Unset):
        json_namespaced_name = namespaced_name.to_dict()
    if not isinstance(json_namespaced_name, Unset):
        params.update(json_namespaced_name)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/tools",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ToolListResponse | None:
    if response.status_code == 200:
        response_200 = ToolListResponse.from_dict(response.json())

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
) -> Response[ErrorData | ToolListResponse]:
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
    id: ListToolsId | Unset = UNSET,
    created_at: ListToolsCreatedAt | Unset = UNSET,
    updated_at: ListToolsUpdatedAt | Unset = UNSET,
    name: ListToolsName | Unset = UNSET,
    description: ListToolsDescription | Unset = UNSET,
    created_by: ListToolsCreatedBy | Unset = UNSET,
    updated_by: ListToolsUpdatedBy | Unset = UNSET,
    enabled: ListToolsEnabled | Unset = UNSET,
    status: ListToolsStatus | Unset = UNSET,
    integration_id: ListToolsIntegrationId | Unset = UNSET,
    namespaced_name: ListToolsNamespacedName | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | ToolListResponse]:
    """List Tools

     List tools with filtering, sorting, and pagination.

    Tools are filtered by the caller's integration visibility — only tools
    belonging to visible integrations are returned.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListToolsId | Unset):
        created_at (ListToolsCreatedAt | Unset):
        updated_at (ListToolsUpdatedAt | Unset):
        name (ListToolsName | Unset):
        description (ListToolsDescription | Unset):
        created_by (ListToolsCreatedBy | Unset):
        updated_by (ListToolsUpdatedBy | Unset):
        enabled (ListToolsEnabled | Unset):
        status (ListToolsStatus | Unset):
        integration_id (ListToolsIntegrationId | Unset):
        namespaced_name (ListToolsNamespacedName | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ToolListResponse]
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
        enabled=enabled,
        status=status,
        integration_id=integration_id,
        namespaced_name=namespaced_name,
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
    id: ListToolsId | Unset = UNSET,
    created_at: ListToolsCreatedAt | Unset = UNSET,
    updated_at: ListToolsUpdatedAt | Unset = UNSET,
    name: ListToolsName | Unset = UNSET,
    description: ListToolsDescription | Unset = UNSET,
    created_by: ListToolsCreatedBy | Unset = UNSET,
    updated_by: ListToolsUpdatedBy | Unset = UNSET,
    enabled: ListToolsEnabled | Unset = UNSET,
    status: ListToolsStatus | Unset = UNSET,
    integration_id: ListToolsIntegrationId | Unset = UNSET,
    namespaced_name: ListToolsNamespacedName | Unset = UNSET,
) -> ErrorData | ToolListResponse | None:
    """List Tools

     List tools with filtering, sorting, and pagination.

    Tools are filtered by the caller's integration visibility — only tools
    belonging to visible integrations are returned.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListToolsId | Unset):
        created_at (ListToolsCreatedAt | Unset):
        updated_at (ListToolsUpdatedAt | Unset):
        name (ListToolsName | Unset):
        description (ListToolsDescription | Unset):
        created_by (ListToolsCreatedBy | Unset):
        updated_by (ListToolsUpdatedBy | Unset):
        enabled (ListToolsEnabled | Unset):
        status (ListToolsStatus | Unset):
        integration_id (ListToolsIntegrationId | Unset):
        namespaced_name (ListToolsNamespacedName | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ToolListResponse
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
        enabled=enabled,
        status=status,
        integration_id=integration_id,
        namespaced_name=namespaced_name,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListToolsId | Unset = UNSET,
    created_at: ListToolsCreatedAt | Unset = UNSET,
    updated_at: ListToolsUpdatedAt | Unset = UNSET,
    name: ListToolsName | Unset = UNSET,
    description: ListToolsDescription | Unset = UNSET,
    created_by: ListToolsCreatedBy | Unset = UNSET,
    updated_by: ListToolsUpdatedBy | Unset = UNSET,
    enabled: ListToolsEnabled | Unset = UNSET,
    status: ListToolsStatus | Unset = UNSET,
    integration_id: ListToolsIntegrationId | Unset = UNSET,
    namespaced_name: ListToolsNamespacedName | Unset = UNSET,
) -> Response[ErrorData | ToolListResponse]:
    """List Tools

     List tools with filtering, sorting, and pagination.

    Tools are filtered by the caller's integration visibility — only tools
    belonging to visible integrations are returned.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListToolsId | Unset):
        created_at (ListToolsCreatedAt | Unset):
        updated_at (ListToolsUpdatedAt | Unset):
        name (ListToolsName | Unset):
        description (ListToolsDescription | Unset):
        created_by (ListToolsCreatedBy | Unset):
        updated_by (ListToolsUpdatedBy | Unset):
        enabled (ListToolsEnabled | Unset):
        status (ListToolsStatus | Unset):
        integration_id (ListToolsIntegrationId | Unset):
        namespaced_name (ListToolsNamespacedName | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ToolListResponse]
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
        enabled=enabled,
        status=status,
        integration_id=integration_id,
        namespaced_name=namespaced_name,
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
    id: ListToolsId | Unset = UNSET,
    created_at: ListToolsCreatedAt | Unset = UNSET,
    updated_at: ListToolsUpdatedAt | Unset = UNSET,
    name: ListToolsName | Unset = UNSET,
    description: ListToolsDescription | Unset = UNSET,
    created_by: ListToolsCreatedBy | Unset = UNSET,
    updated_by: ListToolsUpdatedBy | Unset = UNSET,
    enabled: ListToolsEnabled | Unset = UNSET,
    status: ListToolsStatus | Unset = UNSET,
    integration_id: ListToolsIntegrationId | Unset = UNSET,
    namespaced_name: ListToolsNamespacedName | Unset = UNSET,
) -> ErrorData | ToolListResponse | None:
    """List Tools

     List tools with filtering, sorting, and pagination.

    Tools are filtered by the caller's integration visibility — only tools
    belonging to visible integrations are returned.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListToolsId | Unset):
        created_at (ListToolsCreatedAt | Unset):
        updated_at (ListToolsUpdatedAt | Unset):
        name (ListToolsName | Unset):
        description (ListToolsDescription | Unset):
        created_by (ListToolsCreatedBy | Unset):
        updated_by (ListToolsUpdatedBy | Unset):
        enabled (ListToolsEnabled | Unset):
        status (ListToolsStatus | Unset):
        integration_id (ListToolsIntegrationId | Unset):
        namespaced_name (ListToolsNamespacedName | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ToolListResponse
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
            enabled=enabled,
            status=status,
            integration_id=integration_id,
            namespaced_name=namespaced_name,
        )
    ).parsed
