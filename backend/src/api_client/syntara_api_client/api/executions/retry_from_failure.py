from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.execution_read import ExecutionRead
from ...models.retry_failure_request import RetryFailureRequest
from ...types import Response


def _get_kwargs(
    execution_id: UUID,
    *,
    body: RetryFailureRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": f"/executions/{execution_id}/retry_from_failure",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ExecutionRead | None:
    if response.status_code == 201:
        response_201 = ExecutionRead.from_dict(response.json())

        return response_201

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
) -> Response[ErrorData | ExecutionRead]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
    body: RetryFailureRequest,
) -> Response[ErrorData | ExecutionRead]:
    """Retry from failure

     Retry a failed execution from the given failure points, optionally overriding input parameters of
    the starting nodes for this run only. Independently repeats all validation checks, then creates a
    new execution linked to the source and triggers a Temporal run carrying retry context.

    Args:
        execution_id (UUID):
        body (RetryFailureRequest): Request body for POST /executions/{id}/retry_from_failure.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ExecutionRead]
    """

    kwargs = _get_kwargs(
        execution_id=execution_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
    body: RetryFailureRequest,
) -> ErrorData | ExecutionRead | None:
    """Retry from failure

     Retry a failed execution from the given failure points, optionally overriding input parameters of
    the starting nodes for this run only. Independently repeats all validation checks, then creates a
    new execution linked to the source and triggers a Temporal run carrying retry context.

    Args:
        execution_id (UUID):
        body (RetryFailureRequest): Request body for POST /executions/{id}/retry_from_failure.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ExecutionRead
    """

    return sync_detailed(
        execution_id=execution_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
    body: RetryFailureRequest,
) -> Response[ErrorData | ExecutionRead]:
    """Retry from failure

     Retry a failed execution from the given failure points, optionally overriding input parameters of
    the starting nodes for this run only. Independently repeats all validation checks, then creates a
    new execution linked to the source and triggers a Temporal run carrying retry context.

    Args:
        execution_id (UUID):
        body (RetryFailureRequest): Request body for POST /executions/{id}/retry_from_failure.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ExecutionRead]
    """

    kwargs = _get_kwargs(
        execution_id=execution_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
    body: RetryFailureRequest,
) -> ErrorData | ExecutionRead | None:
    """Retry from failure

     Retry a failed execution from the given failure points, optionally overriding input parameters of
    the starting nodes for this run only. Independently repeats all validation checks, then creates a
    new execution linked to the source and triggers a Temporal run carrying retry context.

    Args:
        execution_id (UUID):
        body (RetryFailureRequest): Request body for POST /executions/{id}/retry_from_failure.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ExecutionRead
    """

    return (
        await asyncio_detailed(
            execution_id=execution_id,
            client=client,
            body=body,
        )
    ).parsed
