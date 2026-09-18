from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.form_prompt_list_response import FormPromptListResponse
from ...models.form_prompt_status import FormPromptStatus
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    execution_id: UUID,
    status: FormPromptStatus | None | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if isinstance(additional_params, dict):
        params = additional_params

    json_execution_id = str(execution_id)
    params["execution_id"] = json_execution_id

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    elif isinstance(status, FormPromptStatus):
        json_status = status.value
    else:
        json_status = status
    params["status"] = json_status

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/form_prompts",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | FormPromptListResponse | None:
    if response.status_code == 200:
        response_200 = FormPromptListResponse.from_dict(response.json())

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
) -> Response[ErrorData | FormPromptListResponse]:
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
    execution_id: UUID,
    status: FormPromptStatus | None | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | FormPromptListResponse]:
    """List form prompts

     List form prompts filtered by execution ID. Internal endpoint for expire/cancel activities.

    Args:
        execution_id (UUID):
        status (FormPromptStatus | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | FormPromptListResponse]
    """

    kwargs = _get_kwargs(execution_id=execution_id, status=status, additional_params=additional_params)

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    execution_id: UUID,
    status: FormPromptStatus | None | Unset = UNSET,
) -> ErrorData | FormPromptListResponse | None:
    """List form prompts

     List form prompts filtered by execution ID. Internal endpoint for expire/cancel activities.

    Args:
        execution_id (UUID):
        status (FormPromptStatus | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | FormPromptListResponse
    """

    return sync_detailed(
        client=client,
        execution_id=execution_id,
        status=status,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    execution_id: UUID,
    status: FormPromptStatus | None | Unset = UNSET,
) -> Response[ErrorData | FormPromptListResponse]:
    """List form prompts

     List form prompts filtered by execution ID. Internal endpoint for expire/cancel activities.

    Args:
        execution_id (UUID):
        status (FormPromptStatus | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | FormPromptListResponse]
    """

    kwargs = _get_kwargs(
        execution_id=execution_id,
        status=status,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    execution_id: UUID,
    status: FormPromptStatus | None | Unset = UNSET,
) -> ErrorData | FormPromptListResponse | None:
    """List form prompts

     List form prompts filtered by execution ID. Internal endpoint for expire/cancel activities.

    Args:
        execution_id (UUID):
        status (FormPromptStatus | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | FormPromptListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            execution_id=execution_id,
            status=status,
        )
    ).parsed
