from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.retry_from_failure_validation_response import RetryFromFailureValidationResponse
from ...types import Response


def _get_kwargs(
    execution_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/executions/{execution_id}/retry_from_failure_preview",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | RetryFromFailureValidationResponse | None:
    if response.status_code == 200:
        response_200 = RetryFromFailureValidationResponse.from_dict(response.json())

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
) -> Response[ErrorData | RetryFromFailureValidationResponse]:
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
) -> Response[ErrorData | RetryFromFailureValidationResponse]:
    """Preview retry from failure

     Report whether an execution can be retried from its failure points, and what would re-run. Returns
    the eligible retry points, the re-run step count for each of them, and the deduplicated total across
    all of them. Purely informational: the failure-point selection and any input parameter overrides are
    supplied to the retry endpoint, which re-validates them independently and rejects anything unusable.
    Never mutates any state.

    Args:
        execution_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | RetryFromFailureValidationResponse]
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
) -> ErrorData | RetryFromFailureValidationResponse | None:
    """Preview retry from failure

     Report whether an execution can be retried from its failure points, and what would re-run. Returns
    the eligible retry points, the re-run step count for each of them, and the deduplicated total across
    all of them. Purely informational: the failure-point selection and any input parameter overrides are
    supplied to the retry endpoint, which re-validates them independently and rejects anything unusable.
    Never mutates any state.

    Args:
        execution_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | RetryFromFailureValidationResponse
    """

    return sync_detailed(
        execution_id=execution_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[ErrorData | RetryFromFailureValidationResponse]:
    """Preview retry from failure

     Report whether an execution can be retried from its failure points, and what would re-run. Returns
    the eligible retry points, the re-run step count for each of them, and the deduplicated total across
    all of them. Purely informational: the failure-point selection and any input parameter overrides are
    supplied to the retry endpoint, which re-validates them independently and rejects anything unusable.
    Never mutates any state.

    Args:
        execution_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | RetryFromFailureValidationResponse]
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
) -> ErrorData | RetryFromFailureValidationResponse | None:
    """Preview retry from failure

     Report whether an execution can be retried from its failure points, and what would re-run. Returns
    the eligible retry points, the re-run step count for each of them, and the deduplicated total across
    all of them. Purely informational: the failure-point selection and any input parameter overrides are
    supplied to the retry endpoint, which re-validates them independently and rejects anything unusable.
    Never mutates any state.

    Args:
        execution_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | RetryFromFailureValidationResponse
    """

    return (
        await asyncio_detailed(
            execution_id=execution_id,
            client=client,
        )
    ).parsed
