from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.form_prompt_list_response import FormPromptListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    additional_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if isinstance(additional_params, dict):
        params = additional_params

    params["limit"] = limit

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    json_sort: None | str | Unset
    if isinstance(sort, Unset):
        json_sort = UNSET
    else:
        json_sort = sort
    params["sort"] = json_sort

    params["include_total"] = include_total

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
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | FormPromptListResponse]:
    """List form prompts

     List form prompts with filtering, sorting, and pagination.

    Supports filtering using query parameters with standard operators:
    - status: Filter by form prompt status (status=pending)
    - execution_id: Filter by parent execution ID (execution_id=uuid)
    - prompt_node_id: Filter by node ID (prompt_node_id=form1)

    Uses cursor-based pagination for scalability and consistency.

    Args:
        limit (int | Unset):  Default: 20.
        cursor (None | str | Unset):
        sort (None | str | Unset):
        include_total (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | FormPromptListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit, cursor=cursor, sort=sort, include_total=include_total, additional_params=additional_params
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
) -> ErrorData | FormPromptListResponse | None:
    """List form prompts

     List form prompts with filtering, sorting, and pagination.

    Supports filtering using query parameters with standard operators:
    - status: Filter by form prompt status (status=pending)
    - execution_id: Filter by parent execution ID (execution_id=uuid)
    - prompt_node_id: Filter by node ID (prompt_node_id=form1)

    Uses cursor-based pagination for scalability and consistency.

    Args:
        limit (int | Unset):  Default: 20.
        cursor (None | str | Unset):
        sort (None | str | Unset):
        include_total (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | FormPromptListResponse
    """

    return sync_detailed(
        client=client,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
) -> Response[ErrorData | FormPromptListResponse]:
    """List form prompts

     List form prompts with filtering, sorting, and pagination.

    Supports filtering using query parameters with standard operators:
    - status: Filter by form prompt status (status=pending)
    - execution_id: Filter by parent execution ID (execution_id=uuid)
    - prompt_node_id: Filter by node ID (prompt_node_id=form1)

    Uses cursor-based pagination for scalability and consistency.

    Args:
        limit (int | Unset):  Default: 20.
        cursor (None | str | Unset):
        sort (None | str | Unset):
        include_total (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | FormPromptListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
) -> ErrorData | FormPromptListResponse | None:
    """List form prompts

     List form prompts with filtering, sorting, and pagination.

    Supports filtering using query parameters with standard operators:
    - status: Filter by form prompt status (status=pending)
    - execution_id: Filter by parent execution ID (execution_id=uuid)
    - prompt_node_id: Filter by node ID (prompt_node_id=form1)

    Uses cursor-based pagination for scalability and consistency.

    Args:
        limit (int | Unset):  Default: 20.
        cursor (None | str | Unset):
        sort (None | str | Unset):
        include_total (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | FormPromptListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
        )
    ).parsed
