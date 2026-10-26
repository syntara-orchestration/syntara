from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.discover_result import DiscoverResult
from ...models.error_data import ErrorData
from ...models.integration_test_connection_v2 import IntegrationTestConnectionV2
from ...types import Response


def _get_kwargs(
    *,
    body: IntegrationTestConnectionV2,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/integrations/discover",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DiscoverResult | ErrorData | None:
    if response.status_code == 200:
        response_200 = DiscoverResult.from_dict(response.json())

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
) -> Response[DiscoverResult | ErrorData]:
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
    body: IntegrationTestConnectionV2,
) -> Response[DiscoverResult | ErrorData]:
    """Discover integration connection

     Test a connection and discover resources without saving an integration.

    Accepts integration configuration and a credential ID, resolves the
    credential, runs the adapter's discover() method, and returns the result
    including discovered tools (with parameters) or models. No integration
    is persisted.

    Args:
        body (IntegrationTestConnectionV2): Schema for testing a connection without saving an
            integration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DiscoverResult | ErrorData]
    """

    kwargs = _get_kwargs(
        body=body,
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
    *,
    client: AuthenticatedClient,
    body: IntegrationTestConnectionV2,
) -> DiscoverResult | ErrorData | None:
    """Discover integration connection

     Test a connection and discover resources without saving an integration.

    Accepts integration configuration and a credential ID, resolves the
    credential, runs the adapter's discover() method, and returns the result
    including discovered tools (with parameters) or models. No integration
    is persisted.

    Args:
        body (IntegrationTestConnectionV2): Schema for testing a connection without saving an
            integration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DiscoverResult | ErrorData
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: IntegrationTestConnectionV2,
) -> Response[DiscoverResult | ErrorData]:
    """Discover integration connection

     Test a connection and discover resources without saving an integration.

    Accepts integration configuration and a credential ID, resolves the
    credential, runs the adapter's discover() method, and returns the result
    including discovered tools (with parameters) or models. No integration
    is persisted.

    Args:
        body (IntegrationTestConnectionV2): Schema for testing a connection without saving an
            integration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DiscoverResult | ErrorData]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    httpx_client = client.get_async_httpx_client()
    # Preserve any deployment prefix while selecting the endpoint's API version.
    api_root = httpx_client.base_url.path.rstrip("/").rsplit("/api/", 1)[0].removesuffix("/api")
    kwargs["url"] = httpx_client.base_url.copy_with(path=f"{api_root}{kwargs['url']}")
    response = await httpx_client.request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: IntegrationTestConnectionV2,
) -> DiscoverResult | ErrorData | None:
    """Discover integration connection

     Test a connection and discover resources without saving an integration.

    Accepts integration configuration and a credential ID, resolves the
    credential, runs the adapter's discover() method, and returns the result
    including discovered tools (with parameters) or models. No integration
    is persisted.

    Args:
        body (IntegrationTestConnectionV2): Schema for testing a connection without saving an
            integration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DiscoverResult | ErrorData
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
