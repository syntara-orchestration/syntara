from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.retry_from_failure_validation_response import RetryFromFailureValidationResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    execution_id: UUID, *, retry_point_ids: list[str] | Unset = UNSET, additional_params: dict[str, Any] | None = None
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if isinstance(additional_params, dict):
        params = additional_params

    json_retry_point_ids: list[str] | Unset = UNSET
    if not isinstance(retry_point_ids, Unset):
        json_retry_point_ids = retry_point_ids

    params["retry_point_ids"] = json_retry_point_ids

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/executions/{execution_id}/retry_from_failure_preview",
        "params": params,
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
    retry_point_ids: list[str] | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | RetryFromFailureValidationResponse]:
    """Preview retry from failure

     Report whether an execution can be retried from its failure points, and what would re-run.
    Optionally accepts repeated retry_point_ids query parameters to preview a selected subset; omitting
    them previews all currently failed points. Returns the eligible retry points, per-point re-run
    counts, the deduplicated total for the requested scope, and the number of completed activity results
    that will be retained. Purely informational: the retry endpoint independently re-validates the same
    selection and rejects anything unusable. Never mutates any state.

    Args:
        execution_id (UUID):
        retry_point_ids (list[str] | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | RetryFromFailureValidationResponse]
    """

    kwargs = _get_kwargs(
        execution_id=execution_id, retry_point_ids=retry_point_ids, additional_params=additional_params
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
    retry_point_ids: list[str] | Unset = UNSET,
) -> ErrorData | RetryFromFailureValidationResponse | None:
    """Preview retry from failure

     Report whether an execution can be retried from its failure points, and what would re-run.
    Optionally accepts repeated retry_point_ids query parameters to preview a selected subset; omitting
    them previews all currently failed points. Returns the eligible retry points, per-point re-run
    counts, the deduplicated total for the requested scope, and the number of completed activity results
    that will be retained. Purely informational: the retry endpoint independently re-validates the same
    selection and rejects anything unusable. Never mutates any state.

    Args:
        execution_id (UUID):
        retry_point_ids (list[str] | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | RetryFromFailureValidationResponse
    """

    return sync_detailed(
        execution_id=execution_id,
        client=client,
        retry_point_ids=retry_point_ids,
    ).parsed


async def asyncio_detailed(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
    retry_point_ids: list[str] | Unset = UNSET,
) -> Response[ErrorData | RetryFromFailureValidationResponse]:
    """Preview retry from failure

     Report whether an execution can be retried from its failure points, and what would re-run.
    Optionally accepts repeated retry_point_ids query parameters to preview a selected subset; omitting
    them previews all currently failed points. Returns the eligible retry points, per-point re-run
    counts, the deduplicated total for the requested scope, and the number of completed activity results
    that will be retained. Purely informational: the retry endpoint independently re-validates the same
    selection and rejects anything unusable. Never mutates any state.

    Args:
        execution_id (UUID):
        retry_point_ids (list[str] | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | RetryFromFailureValidationResponse]
    """

    kwargs = _get_kwargs(
        execution_id=execution_id,
        retry_point_ids=retry_point_ids,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
    retry_point_ids: list[str] | Unset = UNSET,
) -> ErrorData | RetryFromFailureValidationResponse | None:
    """Preview retry from failure

     Report whether an execution can be retried from its failure points, and what would re-run.
    Optionally accepts repeated retry_point_ids query parameters to preview a selected subset; omitting
    them previews all currently failed points. Returns the eligible retry points, per-point re-run
    counts, the deduplicated total for the requested scope, and the number of completed activity results
    that will be retained. Purely informational: the retry endpoint independently re-validates the same
    selection and rejects anything unusable. Never mutates any state.

    Args:
        execution_id (UUID):
        retry_point_ids (list[str] | Unset):

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
            retry_point_ids=retry_point_ids,
        )
    ).parsed
