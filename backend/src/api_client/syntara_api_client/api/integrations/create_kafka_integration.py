from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.kafka_integration_create import KafkaIntegrationCreate
from ...models.kafka_integration_read import KafkaIntegrationRead
from ...types import Response


def _get_kwargs(
    *,
    body: KafkaIntegrationCreate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/kafka_integrations",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | KafkaIntegrationRead | None:
    if response.status_code == 201:
        response_201 = KafkaIntegrationRead.from_dict(response.json())

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
) -> Response[ErrorData | KafkaIntegrationRead]:
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
    body: KafkaIntegrationCreate,
) -> Response[ErrorData | KafkaIntegrationRead]:
    """Create Kafka Integration

     Create a Kafka connection using the shared integration service.

    Args:
        body (KafkaIntegrationCreate): Create a Kafka connection without extending the original
            integration union.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | KafkaIntegrationRead]
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
    body: KafkaIntegrationCreate,
) -> ErrorData | KafkaIntegrationRead | None:
    """Create Kafka Integration

     Create a Kafka connection using the shared integration service.

    Args:
        body (KafkaIntegrationCreate): Create a Kafka connection without extending the original
            integration union.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | KafkaIntegrationRead
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: KafkaIntegrationCreate,
) -> Response[ErrorData | KafkaIntegrationRead]:
    """Create Kafka Integration

     Create a Kafka connection using the shared integration service.

    Args:
        body (KafkaIntegrationCreate): Create a Kafka connection without extending the original
            integration union.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | KafkaIntegrationRead]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: KafkaIntegrationCreate,
) -> ErrorData | KafkaIntegrationRead | None:
    """Create Kafka Integration

     Create a Kafka connection using the shared integration service.

    Args:
        body (KafkaIntegrationCreate): Create a Kafka connection without extending the original
            integration union.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | KafkaIntegrationRead
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
