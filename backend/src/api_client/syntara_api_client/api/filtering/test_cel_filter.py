from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.filter_result import FilterResult
from ...models.filter_test_request import FilterTestRequest
from ...models.filter_validation_problem import FilterValidationProblem
from ...types import Response


def _get_kwargs(
    *,
    body: FilterTestRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/filtering/test",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | FilterResult | FilterValidationProblem | None:
    if response.status_code == 200:
        response_200 = FilterResult.from_dict(response.json())

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
        response_422 = FilterValidationProblem.from_dict(response.json())

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
) -> Response[ErrorData | FilterResult | FilterValidationProblem]:
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
    body: FilterTestRequest,
) -> Response[ErrorData | FilterResult | FilterValidationProblem]:
    """Test a CEL filter expression

     Evaluate caller-supplied JSON with the shared CEL evaluator.

    Authentication is required; no stored resources are read or changed.
    Invalid CEL returns 422. Evaluation returns match, no_match or evaluation_error.

    Args:
        body (FilterTestRequest): An optional CEL expression and required JSON bound directly as
            input.

            Omitted, empty and whitespace-only expressions mean no filter. No Kafka
            decoding, input restructuring or payload-schema validation is performed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | FilterResult | FilterValidationProblem]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: FilterTestRequest,
) -> ErrorData | FilterResult | FilterValidationProblem | None:
    """Test a CEL filter expression

     Evaluate caller-supplied JSON with the shared CEL evaluator.

    Authentication is required; no stored resources are read or changed.
    Invalid CEL returns 422. Evaluation returns match, no_match or evaluation_error.

    Args:
        body (FilterTestRequest): An optional CEL expression and required JSON bound directly as
            input.

            Omitted, empty and whitespace-only expressions mean no filter. No Kafka
            decoding, input restructuring or payload-schema validation is performed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | FilterResult | FilterValidationProblem
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: FilterTestRequest,
) -> Response[ErrorData | FilterResult | FilterValidationProblem]:
    """Test a CEL filter expression

     Evaluate caller-supplied JSON with the shared CEL evaluator.

    Authentication is required; no stored resources are read or changed.
    Invalid CEL returns 422. Evaluation returns match, no_match or evaluation_error.

    Args:
        body (FilterTestRequest): An optional CEL expression and required JSON bound directly as
            input.

            Omitted, empty and whitespace-only expressions mean no filter. No Kafka
            decoding, input restructuring or payload-schema validation is performed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | FilterResult | FilterValidationProblem]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: FilterTestRequest,
) -> ErrorData | FilterResult | FilterValidationProblem | None:
    """Test a CEL filter expression

     Evaluate caller-supplied JSON with the shared CEL evaluator.

    Authentication is required; no stored resources are read or changed.
    Invalid CEL returns 422. Evaluation returns match, no_match or evaluation_error.

    Args:
        body (FilterTestRequest): An optional CEL expression and required JSON bound directly as
            input.

            Omitted, empty and whitespace-only expressions mean no filter. No Kafka
            decoding, input restructuring or payload-schema validation is performed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | FilterResult | FilterValidationProblem
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
