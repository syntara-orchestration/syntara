from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.integration_read_v2 import IntegrationReadV2
from ...types import Response


def _get_kwargs(
    integration_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/api/v2/integrations/{integration_id}",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | IntegrationReadV2 | None:
    if response.status_code == 200:
        response_200 = IntegrationReadV2.from_dict(response.json())

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
) -> Response[ErrorData | IntegrationReadV2]:
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
) -> Response[ErrorData | IntegrationReadV2]:
    """Get integration

     Get an integration by ID.

    Args:
        integration_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | IntegrationReadV2]
    """

    kwargs = _get_kwargs(
        integration_id=integration_id,
    )

    httpx_client = client.get_httpx_client()
    # Path-level servers select v2 while existing clients may use a v1 base URL.
    api_root = httpx_client.base_url.path.rstrip("/").rsplit("/api/", 1)[0].removesuffix("/api")
    kwargs["url"] = httpx_client.base_url.copy_with(path=f"{api_root}{kwargs['url']}")
    response = httpx_client.request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    integration_id: UUID,
    *,
    client: AuthenticatedClient,
) -> ErrorData | IntegrationReadV2 | None:
    """Get integration

     Get an integration by ID.

    Args:
        integration_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | IntegrationReadV2
    """

    return sync_detailed(
        integration_id=integration_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    integration_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[ErrorData | IntegrationReadV2]:
    """Get integration

     Get an integration by ID.

    Args:
        integration_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | IntegrationReadV2]
    """

    kwargs = _get_kwargs(
        integration_id=integration_id,
    )

    httpx_client = client.get_async_httpx_client()
    # Preserve any deployment prefix while selecting the endpoint's API version.
    api_root = httpx_client.base_url.path.rstrip("/").rsplit("/api/", 1)[0].removesuffix("/api")
    kwargs["url"] = httpx_client.base_url.copy_with(path=f"{api_root}{kwargs['url']}")
    response = await httpx_client.request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    integration_id: UUID,
    *,
    client: AuthenticatedClient,
) -> ErrorData | IntegrationReadV2 | None:
    """Get integration

     Get an integration by ID.

    Args:
        integration_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | IntegrationReadV2
    """

    return (
        await asyncio_detailed(
            integration_id=integration_id,
            client=client,
        )
    ).parsed
