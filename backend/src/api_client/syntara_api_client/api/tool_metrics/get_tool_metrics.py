import datetime
from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.tool_metrics_tool_summary_list_response import ToolMetricsToolSummaryListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    namespaced_name: None | str | Unset = UNSET,
    start_time: datetime.datetime | None | Unset = UNSET,
    end_time: datetime.datetime | None | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if isinstance(additional_params, dict):
        params = additional_params

    json_namespaced_name: None | str | Unset
    if isinstance(namespaced_name, Unset):
        json_namespaced_name = UNSET
    else:
        json_namespaced_name = namespaced_name
    params["namespaced_name"] = json_namespaced_name

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
        "url": "/tool_manager/metrics/tools",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ToolMetricsToolSummaryListResponse | None:
    if response.status_code == 200:
        response_200 = ToolMetricsToolSummaryListResponse.from_dict(response.json())

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
) -> Response[ErrorData | ToolMetricsToolSummaryListResponse]:
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
    namespaced_name: None | str | Unset = UNSET,
    start_time: datetime.datetime | None | Unset = UNSET,
    end_time: datetime.datetime | None | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | ToolMetricsToolSummaryListResponse]:
    """Get tool metrics summary

     Return aggregated per-tool metrics summary.

    Supports filtering by namespaced_name and time range.
    Uses UsageCounter for unfiltered queries (fast path) and SQL aggregation
    for time-filtered queries (flexible path).

    Args:
        namespaced_name (None | str | Unset): Filter by tool namespaced name
        start_time (datetime.datetime | None | Unset): Start of time range (ISO 8601)
        end_time (datetime.datetime | None | Unset): End of time range (ISO 8601)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ToolMetricsToolSummaryListResponse]
    """

    kwargs = _get_kwargs(
        namespaced_name=namespaced_name, start_time=start_time, end_time=end_time, additional_params=additional_params
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    namespaced_name: None | str | Unset = UNSET,
    start_time: datetime.datetime | None | Unset = UNSET,
    end_time: datetime.datetime | None | Unset = UNSET,
) -> ErrorData | ToolMetricsToolSummaryListResponse | None:
    """Get tool metrics summary

     Return aggregated per-tool metrics summary.

    Supports filtering by namespaced_name and time range.
    Uses UsageCounter for unfiltered queries (fast path) and SQL aggregation
    for time-filtered queries (flexible path).

    Args:
        namespaced_name (None | str | Unset): Filter by tool namespaced name
        start_time (datetime.datetime | None | Unset): Start of time range (ISO 8601)
        end_time (datetime.datetime | None | Unset): End of time range (ISO 8601)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ToolMetricsToolSummaryListResponse
    """

    return sync_detailed(
        client=client,
        namespaced_name=namespaced_name,
        start_time=start_time,
        end_time=end_time,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    namespaced_name: None | str | Unset = UNSET,
    start_time: datetime.datetime | None | Unset = UNSET,
    end_time: datetime.datetime | None | Unset = UNSET,
) -> Response[ErrorData | ToolMetricsToolSummaryListResponse]:
    """Get tool metrics summary

     Return aggregated per-tool metrics summary.

    Supports filtering by namespaced_name and time range.
    Uses UsageCounter for unfiltered queries (fast path) and SQL aggregation
    for time-filtered queries (flexible path).

    Args:
        namespaced_name (None | str | Unset): Filter by tool namespaced name
        start_time (datetime.datetime | None | Unset): Start of time range (ISO 8601)
        end_time (datetime.datetime | None | Unset): End of time range (ISO 8601)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ToolMetricsToolSummaryListResponse]
    """

    kwargs = _get_kwargs(
        namespaced_name=namespaced_name,
        start_time=start_time,
        end_time=end_time,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    namespaced_name: None | str | Unset = UNSET,
    start_time: datetime.datetime | None | Unset = UNSET,
    end_time: datetime.datetime | None | Unset = UNSET,
) -> ErrorData | ToolMetricsToolSummaryListResponse | None:
    """Get tool metrics summary

     Return aggregated per-tool metrics summary.

    Supports filtering by namespaced_name and time range.
    Uses UsageCounter for unfiltered queries (fast path) and SQL aggregation
    for time-filtered queries (flexible path).

    Args:
        namespaced_name (None | str | Unset): Filter by tool namespaced name
        start_time (datetime.datetime | None | Unset): Start of time range (ISO 8601)
        end_time (datetime.datetime | None | Unset): End of time range (ISO 8601)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ToolMetricsToolSummaryListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            namespaced_name=namespaced_name,
            start_time=start_time,
            end_time=end_time,
        )
    ).parsed
