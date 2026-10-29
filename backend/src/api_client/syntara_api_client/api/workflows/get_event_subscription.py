from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.event_subscription_read import EventSubscriptionRead
from ...types import Response


def _get_kwargs(
    workflow_id: UUID,
    subscription_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/workflows/{workflow_id}/event_subscriptions/{subscription_id}",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | EventSubscriptionRead | None:
    if response.status_code == 200:
        response_200 = EventSubscriptionRead.from_dict(response.json())

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
) -> Response[ErrorData | EventSubscriptionRead]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    workflow_id: UUID,
    subscription_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[ErrorData | EventSubscriptionRead]:
    """Get workflow event subscription

     Read subscription lifecycle and recovery state within its workflow/project.

    Args:
        workflow_id (UUID):
        subscription_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | EventSubscriptionRead]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        subscription_id=subscription_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    workflow_id: UUID,
    subscription_id: UUID,
    *,
    client: AuthenticatedClient,
) -> ErrorData | EventSubscriptionRead | None:
    """Get workflow event subscription

     Read subscription lifecycle and recovery state within its workflow/project.

    Args:
        workflow_id (UUID):
        subscription_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | EventSubscriptionRead
    """

    return sync_detailed(
        workflow_id=workflow_id,
        subscription_id=subscription_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    workflow_id: UUID,
    subscription_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[ErrorData | EventSubscriptionRead]:
    """Get workflow event subscription

     Read subscription lifecycle and recovery state within its workflow/project.

    Args:
        workflow_id (UUID):
        subscription_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | EventSubscriptionRead]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        subscription_id=subscription_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workflow_id: UUID,
    subscription_id: UUID,
    *,
    client: AuthenticatedClient,
) -> ErrorData | EventSubscriptionRead | None:
    """Get workflow event subscription

     Read subscription lifecycle and recovery state within its workflow/project.

    Args:
        workflow_id (UUID):
        subscription_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | EventSubscriptionRead
    """

    return (
        await asyncio_detailed(
            workflow_id=workflow_id,
            subscription_id=subscription_id,
            client=client,
        )
    ).parsed
