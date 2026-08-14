from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.web_socket_ticket_response import WebSocketTicketResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/auth/ws_ticket",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | ErrorData | WebSocketTicketResponse | None:
    if response.status_code == 200:
        response_200 = WebSocketTicketResponse.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = ErrorData.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = cast(Any, None)
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
) -> Response[Any | ErrorData | WebSocketTicketResponse]:
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
) -> Response[Any | ErrorData | WebSocketTicketResponse]:
    """Exchange JWT for a WebSocket connection ticket

     Exchange a valid Bearer JWT for a short-lived, single-use opaque ticket.
    The client then connects to the WebSocket endpoint with ``?ticket=<ticket>``
    instead of passing the raw JWT in the query string, preventing token leakage
    in server/proxy logs and browser history.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ErrorData | WebSocketTicketResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
) -> Any | ErrorData | WebSocketTicketResponse | None:
    """Exchange JWT for a WebSocket connection ticket

     Exchange a valid Bearer JWT for a short-lived, single-use opaque ticket.
    The client then connects to the WebSocket endpoint with ``?ticket=<ticket>``
    instead of passing the raw JWT in the query string, preventing token leakage
    in server/proxy logs and browser history.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ErrorData | WebSocketTicketResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[Any | ErrorData | WebSocketTicketResponse]:
    """Exchange JWT for a WebSocket connection ticket

     Exchange a valid Bearer JWT for a short-lived, single-use opaque ticket.
    The client then connects to the WebSocket endpoint with ``?ticket=<ticket>``
    instead of passing the raw JWT in the query string, preventing token leakage
    in server/proxy logs and browser history.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ErrorData | WebSocketTicketResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
) -> Any | ErrorData | WebSocketTicketResponse | None:
    """Exchange JWT for a WebSocket connection ticket

     Exchange a valid Bearer JWT for a short-lived, single-use opaque ticket.
    The client then connects to the WebSocket endpoint with ``?ticket=<ticket>``
    instead of passing the raw JWT in the query string, preventing token leakage
    in server/proxy logs and browser history.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ErrorData | WebSocketTicketResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
