from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.execution_read import ExecutionRead
from ...models.workflow_launch_rejected_problem import WorkflowLaunchRejectedProblem
from ...types import Response


def _get_kwargs(
    execution_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": f"/executions/{execution_id}/retry",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ExecutionRead | WorkflowLaunchRejectedProblem | None:
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
        response_403 = WorkflowLaunchRejectedProblem.from_dict(response.json())

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
) -> Response[ErrorData | ExecutionRead | WorkflowLaunchRejectedProblem]:
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
) -> Response[ErrorData | ExecutionRead | WorkflowLaunchRejectedProblem]:
    """Retry execution

     Retry a completed workflow execution. Creates a new execution using the same workflow version,
    inputs, and trigger as the original.

    Args:
        execution_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ExecutionRead | WorkflowLaunchRejectedProblem]
    """

    kwargs = _get_kwargs(
        execution_id=execution_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
) -> ErrorData | ExecutionRead | WorkflowLaunchRejectedProblem | None:
    """Retry execution

     Retry a completed workflow execution. Creates a new execution using the same workflow version,
    inputs, and trigger as the original.

    Args:
        execution_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ExecutionRead | WorkflowLaunchRejectedProblem
    """

    return sync_detailed(
        execution_id=execution_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[ErrorData | ExecutionRead | WorkflowLaunchRejectedProblem]:
    """Retry execution

     Retry a completed workflow execution. Creates a new execution using the same workflow version,
    inputs, and trigger as the original.

    Args:
        execution_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ExecutionRead | WorkflowLaunchRejectedProblem]
    """

    kwargs = _get_kwargs(
        execution_id=execution_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
) -> ErrorData | ExecutionRead | WorkflowLaunchRejectedProblem | None:
    """Retry execution

     Retry a completed workflow execution. Creates a new execution using the same workflow version,
    inputs, and trigger as the original.

    Args:
        execution_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ExecutionRead | WorkflowLaunchRejectedProblem
    """

    return (
        await asyncio_detailed(
            execution_id=execution_id,
            client=client,
        )
    ).parsed
