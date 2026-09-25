from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.form_prompt_create_request import FormPromptCreateRequest
from ...models.form_prompt_summary import FormPromptSummary
from ...types import Response


def _get_kwargs(
    *,
    body: FormPromptCreateRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/form_prompts",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | FormPromptSummary | None:
    if response.status_code == 201:
        response_201 = FormPromptSummary.from_dict(response.json())

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
) -> Response[ErrorData | FormPromptSummary]:
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
    body: FormPromptCreateRequest,
) -> Response[ErrorData | FormPromptSummary]:
    """Create form prompt

     Create a new form prompt. Internal service-to-service endpoint for workflow engine.

    Args:
        body (FormPromptCreateRequest): Request payload for creating a form prompt.

            This is an internal schema used by the Workflows component.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | FormPromptSummary]
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
    body: FormPromptCreateRequest,
) -> ErrorData | FormPromptSummary | None:
    """Create form prompt

     Create a new form prompt. Internal service-to-service endpoint for workflow engine.

    Args:
        body (FormPromptCreateRequest): Request payload for creating a form prompt.

            This is an internal schema used by the Workflows component.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | FormPromptSummary
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: FormPromptCreateRequest,
) -> Response[ErrorData | FormPromptSummary]:
    """Create form prompt

     Create a new form prompt. Internal service-to-service endpoint for workflow engine.

    Args:
        body (FormPromptCreateRequest): Request payload for creating a form prompt.

            This is an internal schema used by the Workflows component.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | FormPromptSummary]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: FormPromptCreateRequest,
) -> ErrorData | FormPromptSummary | None:
    """Create form prompt

     Create a new form prompt. Internal service-to-service endpoint for workflow engine.

    Args:
        body (FormPromptCreateRequest): Request payload for creating a form prompt.

            This is an internal schema used by the Workflows component.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | FormPromptSummary
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
