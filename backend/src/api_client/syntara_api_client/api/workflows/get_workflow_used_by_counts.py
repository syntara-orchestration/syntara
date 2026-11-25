from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.workflow_used_by_counts_response import WorkflowUsedByCountsResponse
from ...types import UNSET, Response


def _get_kwargs(*, workflow_ids: list[UUID], additional_params: dict[str, Any] | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if isinstance(additional_params, dict):
        params = additional_params

    json_workflow_ids = []
    for workflow_ids_item_data in workflow_ids:
        workflow_ids_item = str(workflow_ids_item_data)
        json_workflow_ids.append(workflow_ids_item)

    params["workflow_ids"] = json_workflow_ids

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/workflows/used_by_counts",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | WorkflowUsedByCountsResponse | None:
    if response.status_code == 200:
        response_200 = WorkflowUsedByCountsResponse.from_dict(response.json())

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
) -> Response[ErrorData | WorkflowUsedByCountsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    *, client: AuthenticatedClient, workflow_ids: list[UUID], additional_params: dict[str, Any] | None = None
) -> Response[ErrorData | WorkflowUsedByCountsResponse]:
    """Batch Used-By totals for multiple workflows

     Return the Used-By total for each requested workflow the caller may read.

    Totals count distinct published parents across all projects (matching the Used-By badge), so a
    workflow list can show per-row counts with one request instead of one call per row.

    Args:
        workflow_ids (list[UUID]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | WorkflowUsedByCountsResponse]
    """

    kwargs = _get_kwargs(workflow_ids=workflow_ids, additional_params=additional_params)

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    workflow_ids: list[UUID],
) -> ErrorData | WorkflowUsedByCountsResponse | None:
    """Batch Used-By totals for multiple workflows

     Return the Used-By total for each requested workflow the caller may read.

    Totals count distinct published parents across all projects (matching the Used-By badge), so a
    workflow list can show per-row counts with one request instead of one call per row.

    Args:
        workflow_ids (list[UUID]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | WorkflowUsedByCountsResponse
    """

    return sync_detailed(
        client=client,
        workflow_ids=workflow_ids,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    workflow_ids: list[UUID],
) -> Response[ErrorData | WorkflowUsedByCountsResponse]:
    """Batch Used-By totals for multiple workflows

     Return the Used-By total for each requested workflow the caller may read.

    Totals count distinct published parents across all projects (matching the Used-By badge), so a
    workflow list can show per-row counts with one request instead of one call per row.

    Args:
        workflow_ids (list[UUID]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | WorkflowUsedByCountsResponse]
    """

    kwargs = _get_kwargs(
        workflow_ids=workflow_ids,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    workflow_ids: list[UUID],
) -> ErrorData | WorkflowUsedByCountsResponse | None:
    """Batch Used-By totals for multiple workflows

     Return the Used-By total for each requested workflow the caller may read.

    Totals count distinct published parents across all projects (matching the Used-By badge), so a
    workflow list can show per-row counts with one request instead of one call per row.

    Args:
        workflow_ids (list[UUID]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | WorkflowUsedByCountsResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            workflow_ids=workflow_ids,
        )
    ).parsed
