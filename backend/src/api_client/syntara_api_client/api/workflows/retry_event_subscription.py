from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.subscription_control_request import SubscriptionControlRequest
from ...models.subscription_control_response import SubscriptionControlResponse
from ...types import Response


def _get_kwargs(
    workflow_id: UUID,
    subscription_id: UUID,
    *,
    body: SubscriptionControlRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": f"/workflows/{workflow_id}/event_subscriptions/{subscription_id}/retry",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | SubscriptionControlResponse | None:
    if response.status_code == 200:
        response_200 = SubscriptionControlResponse.from_dict(response.json())

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
) -> Response[ErrorData | SubscriptionControlResponse]:
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
    body: SubscriptionControlRequest,
) -> Response[ErrorData | SubscriptionControlResponse]:
    """Retry event subscription

     Retry runtime setup and prepared scheduling; never replay or reset positions.

    Args:
        workflow_id (UUID):
        subscription_id (UUID):
        body (SubscriptionControlRequest): Compare-and-set against the published projection and
            source generation.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | SubscriptionControlResponse]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        subscription_id=subscription_id,
        body=body,
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
    body: SubscriptionControlRequest,
) -> ErrorData | SubscriptionControlResponse | None:
    """Retry event subscription

     Retry runtime setup and prepared scheduling; never replay or reset positions.

    Args:
        workflow_id (UUID):
        subscription_id (UUID):
        body (SubscriptionControlRequest): Compare-and-set against the published projection and
            source generation.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | SubscriptionControlResponse
    """

    return sync_detailed(
        workflow_id=workflow_id,
        subscription_id=subscription_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    workflow_id: UUID,
    subscription_id: UUID,
    *,
    client: AuthenticatedClient,
    body: SubscriptionControlRequest,
) -> Response[ErrorData | SubscriptionControlResponse]:
    """Retry event subscription

     Retry runtime setup and prepared scheduling; never replay or reset positions.

    Args:
        workflow_id (UUID):
        subscription_id (UUID):
        body (SubscriptionControlRequest): Compare-and-set against the published projection and
            source generation.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | SubscriptionControlResponse]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        subscription_id=subscription_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workflow_id: UUID,
    subscription_id: UUID,
    *,
    client: AuthenticatedClient,
    body: SubscriptionControlRequest,
) -> ErrorData | SubscriptionControlResponse | None:
    """Retry event subscription

     Retry runtime setup and prepared scheduling; never replay or reset positions.

    Args:
        workflow_id (UUID):
        subscription_id (UUID):
        body (SubscriptionControlRequest): Compare-and-set against the published projection and
            source generation.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | SubscriptionControlResponse
    """

    return (
        await asyncio_detailed(
            workflow_id=workflow_id,
            subscription_id=subscription_id,
            client=client,
            body=body,
        )
    ).parsed
