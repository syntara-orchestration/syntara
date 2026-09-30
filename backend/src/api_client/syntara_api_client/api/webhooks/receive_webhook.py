from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.webhook_response import WebhookResponse
from ...models.workflow_launch_rejected_problem import WorkflowLaunchRejectedProblem
from ...types import Response


def _get_kwargs(
    webhook_path: str,
    *,
    body: Any,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": f"/webhooks/{webhook_path}",
    }

    _kwargs["json"] = body

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ErrorData | WorkflowLaunchRejectedProblem | WebhookResponse | None:
    if response.status_code == 202:
        response_202 = WebhookResponse.from_dict(response.json())

        return response_202

    if response.status_code == 400:
        response_400 = ErrorData.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = ErrorData.from_dict(response.json())

        return response_401

    if response.status_code == 403:

        def _parse_response_403(data: object) -> ErrorData | WorkflowLaunchRejectedProblem:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_403_type_0 = ErrorData.from_dict(data)

                return response_403_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            response_403_type_1 = WorkflowLaunchRejectedProblem.from_dict(data)

            return response_403_type_1

        response_403 = _parse_response_403(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = ErrorData.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = ErrorData.from_dict(response.json())

        return response_409

    if response.status_code == 413:
        response_413 = ErrorData.from_dict(response.json())

        return response_413

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
) -> Response[ErrorData | ErrorData | WorkflowLaunchRejectedProblem | WebhookResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    webhook_path: str,
    *,
    client: AuthenticatedClient,
    body: Any,
) -> Response[ErrorData | ErrorData | WorkflowLaunchRejectedProblem | WebhookResponse]:
    """Receive webhook event

     Receive a webhook event from an external system and trigger the matching workflow. Requires a
    service account Bearer token. Only POST method is supported; other methods receive 405 Method Not
    Allowed.

    Args:
        webhook_path (str):
        body (Any):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ErrorData | WorkflowLaunchRejectedProblem | WebhookResponse]
    """

    kwargs = _get_kwargs(
        webhook_path=webhook_path,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    webhook_path: str,
    *,
    client: AuthenticatedClient,
    body: Any,
) -> ErrorData | ErrorData | WorkflowLaunchRejectedProblem | WebhookResponse | None:
    """Receive webhook event

     Receive a webhook event from an external system and trigger the matching workflow. Requires a
    service account Bearer token. Only POST method is supported; other methods receive 405 Method Not
    Allowed.

    Args:
        webhook_path (str):
        body (Any):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ErrorData | WorkflowLaunchRejectedProblem | WebhookResponse
    """

    return sync_detailed(
        webhook_path=webhook_path,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    webhook_path: str,
    *,
    client: AuthenticatedClient,
    body: Any,
) -> Response[ErrorData | ErrorData | WorkflowLaunchRejectedProblem | WebhookResponse]:
    """Receive webhook event

     Receive a webhook event from an external system and trigger the matching workflow. Requires a
    service account Bearer token. Only POST method is supported; other methods receive 405 Method Not
    Allowed.

    Args:
        webhook_path (str):
        body (Any):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ErrorData | WorkflowLaunchRejectedProblem | WebhookResponse]
    """

    kwargs = _get_kwargs(
        webhook_path=webhook_path,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    webhook_path: str,
    *,
    client: AuthenticatedClient,
    body: Any,
) -> ErrorData | ErrorData | WorkflowLaunchRejectedProblem | WebhookResponse | None:
    """Receive webhook event

     Receive a webhook event from an external system and trigger the matching workflow. Requires a
    service account Bearer token. Only POST method is supported; other methods receive 405 Method Not
    Allowed.

    Args:
        webhook_path (str):
        body (Any):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ErrorData | WorkflowLaunchRejectedProblem | WebhookResponse
    """

    return (
        await asyncio_detailed(
            webhook_path=webhook_path,
            client=client,
            body=body,
        )
    ).parsed
