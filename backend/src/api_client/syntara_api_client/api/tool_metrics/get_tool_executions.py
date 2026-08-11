import datetime
from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.tool_execution_list_response import ToolExecutionListResponse
from ...models.tool_execution_status import ToolExecutionStatus
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    namespaced_name: None | str | Unset = UNSET,
    status: None | ToolExecutionStatus | Unset = UNSET,
    start_time: datetime.datetime | None | Unset = UNSET,
    end_time: datetime.datetime | None | Unset = UNSET,
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

    json_namespaced_name: None | str | Unset
    if isinstance(namespaced_name, Unset):
        json_namespaced_name = UNSET
    else:
        json_namespaced_name = namespaced_name
    params["namespaced_name"] = json_namespaced_name

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    elif isinstance(status, ToolExecutionStatus):
        json_status = status.value
    else:
        json_status = status
    params["status"] = json_status

    json_start_time: None | str | Unset
    if isinstance(start_time, Unset):
        json_start_time = UNSET
    elif isinstance(start_time, datetime.datetime):
        json_start_time = start_time.isoformat()
    else:
        json_start_time = start_time
    params["start_time"] = json_start_time

    json_end_time: None | str | Unset
    if isinstance(end_time, Unset):
        json_end_time = UNSET
    elif isinstance(end_time, datetime.datetime):
        json_end_time = end_time.isoformat()
    else:
        json_end_time = end_time
    params["end_time"] = json_end_time

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/tool_manager/metrics/executions",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ToolExecutionListResponse | None:
    if response.status_code == 200:
        response_200 = ToolExecutionListResponse.from_dict(response.json())

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
) -> Response[ErrorData | ToolExecutionListResponse]:
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
    namespaced_name: None | str | Unset = UNSET,
    status: None | ToolExecutionStatus | Unset = UNSET,
    start_time: datetime.datetime | None | Unset = UNSET,
    end_time: datetime.datetime | None | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | ToolExecutionListResponse]:
    """List tool executions

     Return paginated tool execution history.

    Supports filtering by namespaced_name, status, and time range.
    Uses cursor-based pagination consistent with other Nexus list endpoints.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        namespaced_name (None | str | Unset): Filter by tool namespaced name
        status (None | ToolExecutionStatus | Unset): Filter by execution status
        start_time (datetime.datetime | None | Unset): Start of time range (ISO 8601)
        end_time (datetime.datetime | None | Unset): End of time range (ISO 8601)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ToolExecutionListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        namespaced_name=namespaced_name,
        status=status,
        start_time=start_time,
        end_time=end_time,
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
    namespaced_name: None | str | Unset = UNSET,
    status: None | ToolExecutionStatus | Unset = UNSET,
    start_time: datetime.datetime | None | Unset = UNSET,
    end_time: datetime.datetime | None | Unset = UNSET,
) -> ErrorData | ToolExecutionListResponse | None:
    """List tool executions

     Return paginated tool execution history.

    Supports filtering by namespaced_name, status, and time range.
    Uses cursor-based pagination consistent with other Nexus list endpoints.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        namespaced_name (None | str | Unset): Filter by tool namespaced name
        status (None | ToolExecutionStatus | Unset): Filter by execution status
        start_time (datetime.datetime | None | Unset): Start of time range (ISO 8601)
        end_time (datetime.datetime | None | Unset): End of time range (ISO 8601)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ToolExecutionListResponse
    """

    return sync_detailed(
        client=client,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        namespaced_name=namespaced_name,
        status=status,
        start_time=start_time,
        end_time=end_time,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    namespaced_name: None | str | Unset = UNSET,
    status: None | ToolExecutionStatus | Unset = UNSET,
    start_time: datetime.datetime | None | Unset = UNSET,
    end_time: datetime.datetime | None | Unset = UNSET,
) -> Response[ErrorData | ToolExecutionListResponse]:
    """List tool executions

     Return paginated tool execution history.

    Supports filtering by namespaced_name, status, and time range.
    Uses cursor-based pagination consistent with other Nexus list endpoints.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        namespaced_name (None | str | Unset): Filter by tool namespaced name
        status (None | ToolExecutionStatus | Unset): Filter by execution status
        start_time (datetime.datetime | None | Unset): Start of time range (ISO 8601)
        end_time (datetime.datetime | None | Unset): End of time range (ISO 8601)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ToolExecutionListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        namespaced_name=namespaced_name,
        status=status,
        start_time=start_time,
        end_time=end_time,
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
    namespaced_name: None | str | Unset = UNSET,
    status: None | ToolExecutionStatus | Unset = UNSET,
    start_time: datetime.datetime | None | Unset = UNSET,
    end_time: datetime.datetime | None | Unset = UNSET,
) -> ErrorData | ToolExecutionListResponse | None:
    """List tool executions

     Return paginated tool execution history.

    Supports filtering by namespaced_name, status, and time range.
    Uses cursor-based pagination consistent with other Nexus list endpoints.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        namespaced_name (None | str | Unset): Filter by tool namespaced name
        status (None | ToolExecutionStatus | Unset): Filter by execution status
        start_time (datetime.datetime | None | Unset): Start of time range (ISO 8601)
        end_time (datetime.datetime | None | Unset): End of time range (ISO 8601)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ToolExecutionListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
            namespaced_name=namespaced_name,
            status=status,
            start_time=start_time,
            end_time=end_time,
        )
    ).parsed
