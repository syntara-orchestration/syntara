from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.list_integration_tools_created_at import ListIntegrationToolsCreatedAt
from ...models.list_integration_tools_created_by import ListIntegrationToolsCreatedBy
from ...models.list_integration_tools_description import ListIntegrationToolsDescription
from ...models.list_integration_tools_enabled import ListIntegrationToolsEnabled
from ...models.list_integration_tools_id import ListIntegrationToolsId
from ...models.list_integration_tools_name import ListIntegrationToolsName
from ...models.list_integration_tools_namespaced_name import ListIntegrationToolsNamespacedName
from ...models.list_integration_tools_status import ListIntegrationToolsStatus
from ...models.list_integration_tools_updated_at import ListIntegrationToolsUpdatedAt
from ...models.list_integration_tools_updated_by import ListIntegrationToolsUpdatedBy
from ...models.tool_list_response import ToolListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    integration_id: UUID,
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListIntegrationToolsId | Unset = UNSET,
    created_at: ListIntegrationToolsCreatedAt | Unset = UNSET,
    updated_at: ListIntegrationToolsUpdatedAt | Unset = UNSET,
    name: ListIntegrationToolsName | Unset = UNSET,
    description: ListIntegrationToolsDescription | Unset = UNSET,
    created_by: ListIntegrationToolsCreatedBy | Unset = UNSET,
    updated_by: ListIntegrationToolsUpdatedBy | Unset = UNSET,
    enabled: ListIntegrationToolsEnabled | Unset = UNSET,
    status: ListIntegrationToolsStatus | Unset = UNSET,
    namespaced_name: ListIntegrationToolsNamespacedName | Unset = UNSET,
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

    json_namespaced_name: dict[str, Any] | Unset = UNSET
    if not isinstance(namespaced_name, Unset):
        json_namespaced_name = namespaced_name.to_dict()
    if not isinstance(json_namespaced_name, Unset):
        params.update(json_namespaced_name)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/integrations/{integration_id}/tools",
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
    integration_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListIntegrationToolsId | Unset = UNSET,
    created_at: ListIntegrationToolsCreatedAt | Unset = UNSET,
    updated_at: ListIntegrationToolsUpdatedAt | Unset = UNSET,
    name: ListIntegrationToolsName | Unset = UNSET,
    description: ListIntegrationToolsDescription | Unset = UNSET,
    created_by: ListIntegrationToolsCreatedBy | Unset = UNSET,
    updated_by: ListIntegrationToolsUpdatedBy | Unset = UNSET,
    enabled: ListIntegrationToolsEnabled | Unset = UNSET,
    status: ListIntegrationToolsStatus | Unset = UNSET,
    namespaced_name: ListIntegrationToolsNamespacedName | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | ToolListResponse]:
    """List Integration Tools

     List tools for an integration with filtering, sorting, and pagination.

    Args:
        integration_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListIntegrationToolsId | Unset):
        created_at (ListIntegrationToolsCreatedAt | Unset):
        updated_at (ListIntegrationToolsUpdatedAt | Unset):
        name (ListIntegrationToolsName | Unset):
        description (ListIntegrationToolsDescription | Unset):
        created_by (ListIntegrationToolsCreatedBy | Unset):
        updated_by (ListIntegrationToolsUpdatedBy | Unset):
        enabled (ListIntegrationToolsEnabled | Unset):
        status (ListIntegrationToolsStatus | Unset):
        namespaced_name (ListIntegrationToolsNamespacedName | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ToolListResponse]
    """

    kwargs = _get_kwargs(
        integration_id=integration_id,
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
        namespaced_name=namespaced_name,
        additional_params=additional_params,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    integration_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListIntegrationToolsId | Unset = UNSET,
    created_at: ListIntegrationToolsCreatedAt | Unset = UNSET,
    updated_at: ListIntegrationToolsUpdatedAt | Unset = UNSET,
    name: ListIntegrationToolsName | Unset = UNSET,
    description: ListIntegrationToolsDescription | Unset = UNSET,
    created_by: ListIntegrationToolsCreatedBy | Unset = UNSET,
    updated_by: ListIntegrationToolsUpdatedBy | Unset = UNSET,
    enabled: ListIntegrationToolsEnabled | Unset = UNSET,
    status: ListIntegrationToolsStatus | Unset = UNSET,
    namespaced_name: ListIntegrationToolsNamespacedName | Unset = UNSET,
) -> ErrorData | ToolListResponse | None:
    """List Integration Tools

     List tools for an integration with filtering, sorting, and pagination.

    Args:
        integration_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListIntegrationToolsId | Unset):
        created_at (ListIntegrationToolsCreatedAt | Unset):
        updated_at (ListIntegrationToolsUpdatedAt | Unset):
        name (ListIntegrationToolsName | Unset):
        description (ListIntegrationToolsDescription | Unset):
        created_by (ListIntegrationToolsCreatedBy | Unset):
        updated_by (ListIntegrationToolsUpdatedBy | Unset):
        enabled (ListIntegrationToolsEnabled | Unset):
        status (ListIntegrationToolsStatus | Unset):
        namespaced_name (ListIntegrationToolsNamespacedName | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ToolListResponse
    """

    return sync_detailed(
        integration_id=integration_id,
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
        namespaced_name=namespaced_name,
    ).parsed


async def asyncio_detailed(
    integration_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListIntegrationToolsId | Unset = UNSET,
    created_at: ListIntegrationToolsCreatedAt | Unset = UNSET,
    updated_at: ListIntegrationToolsUpdatedAt | Unset = UNSET,
    name: ListIntegrationToolsName | Unset = UNSET,
    description: ListIntegrationToolsDescription | Unset = UNSET,
    created_by: ListIntegrationToolsCreatedBy | Unset = UNSET,
    updated_by: ListIntegrationToolsUpdatedBy | Unset = UNSET,
    enabled: ListIntegrationToolsEnabled | Unset = UNSET,
    status: ListIntegrationToolsStatus | Unset = UNSET,
    namespaced_name: ListIntegrationToolsNamespacedName | Unset = UNSET,
) -> Response[ErrorData | ToolListResponse]:
    """List Integration Tools

     List tools for an integration with filtering, sorting, and pagination.

    Args:
        integration_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListIntegrationToolsId | Unset):
        created_at (ListIntegrationToolsCreatedAt | Unset):
        updated_at (ListIntegrationToolsUpdatedAt | Unset):
        name (ListIntegrationToolsName | Unset):
        description (ListIntegrationToolsDescription | Unset):
        created_by (ListIntegrationToolsCreatedBy | Unset):
        updated_by (ListIntegrationToolsUpdatedBy | Unset):
        enabled (ListIntegrationToolsEnabled | Unset):
        status (ListIntegrationToolsStatus | Unset):
        namespaced_name (ListIntegrationToolsNamespacedName | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ToolListResponse]
    """

    kwargs = _get_kwargs(
        integration_id=integration_id,
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
        namespaced_name=namespaced_name,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    integration_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListIntegrationToolsId | Unset = UNSET,
    created_at: ListIntegrationToolsCreatedAt | Unset = UNSET,
    updated_at: ListIntegrationToolsUpdatedAt | Unset = UNSET,
    name: ListIntegrationToolsName | Unset = UNSET,
    description: ListIntegrationToolsDescription | Unset = UNSET,
    created_by: ListIntegrationToolsCreatedBy | Unset = UNSET,
    updated_by: ListIntegrationToolsUpdatedBy | Unset = UNSET,
    enabled: ListIntegrationToolsEnabled | Unset = UNSET,
    status: ListIntegrationToolsStatus | Unset = UNSET,
    namespaced_name: ListIntegrationToolsNamespacedName | Unset = UNSET,
) -> ErrorData | ToolListResponse | None:
    """List Integration Tools

     List tools for an integration with filtering, sorting, and pagination.

    Args:
        integration_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListIntegrationToolsId | Unset):
        created_at (ListIntegrationToolsCreatedAt | Unset):
        updated_at (ListIntegrationToolsUpdatedAt | Unset):
        name (ListIntegrationToolsName | Unset):
        description (ListIntegrationToolsDescription | Unset):
        created_by (ListIntegrationToolsCreatedBy | Unset):
        updated_by (ListIntegrationToolsUpdatedBy | Unset):
        enabled (ListIntegrationToolsEnabled | Unset):
        status (ListIntegrationToolsStatus | Unset):
        namespaced_name (ListIntegrationToolsNamespacedName | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ToolListResponse
    """

    return (
        await asyncio_detailed(
            integration_id=integration_id,
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
            namespaced_name=namespaced_name,
        )
    ).parsed
