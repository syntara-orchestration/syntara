from http import HTTPStatus
from typing import Any, cast
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...types import UNSET, Response, Unset


def _get_kwargs(
    workflow_id: UUID, *, confirm: bool | Unset = False, additional_params: dict[str, Any] | None = None
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if isinstance(additional_params, dict):
        params = additional_params

    params["confirm"] = confirm

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": f"/workflows/{workflow_id}",
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | ErrorData | None:
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any | ErrorData]:
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
    *,
    client: AuthenticatedClient,
    confirm: bool | Unset = False,
    additional_params: dict[str, Any] | None = None,
) -> Response[Any | ErrorData]:
    """Delete workflow

     Permanently delete a workflow and cascade-delete all its versions and executions.

    If the workflow is referenced by published parents, deletion requires ``confirm=true``;
    otherwise it returns 409 with the count of referencing parents (no parent details).

    Args:
        workflow_id (UUID):
        confirm (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ErrorData]
    """

    kwargs = _get_kwargs(workflow_id=workflow_id, confirm=confirm, additional_params=additional_params)

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    workflow_id: UUID,
    *,
    client: AuthenticatedClient,
    confirm: bool | Unset = False,
) -> Any | ErrorData | None:
    """Delete workflow

     Permanently delete a workflow and cascade-delete all its versions and executions.

    If the workflow is referenced by published parents, deletion requires ``confirm=true``;
    otherwise it returns 409 with the count of referencing parents (no parent details).

    Args:
        workflow_id (UUID):
        confirm (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ErrorData
    """

    return sync_detailed(
        workflow_id=workflow_id,
        client=client,
        confirm=confirm,
    ).parsed


async def asyncio_detailed(
    workflow_id: UUID,
    *,
    client: AuthenticatedClient,
    confirm: bool | Unset = False,
) -> Response[Any | ErrorData]:
    """Delete workflow

     Permanently delete a workflow and cascade-delete all its versions and executions.

    If the workflow is referenced by published parents, deletion requires ``confirm=true``;
    otherwise it returns 409 with the count of referencing parents (no parent details).

    Args:
        workflow_id (UUID):
        confirm (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ErrorData]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        confirm=confirm,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workflow_id: UUID,
    *,
    client: AuthenticatedClient,
    confirm: bool | Unset = False,
) -> Any | ErrorData | None:
    """Delete workflow

     Permanently delete a workflow and cascade-delete all its versions and executions.

    If the workflow is referenced by published parents, deletion requires ``confirm=true``;
    otherwise it returns 409 with the count of referencing parents (no parent details).

    Args:
        workflow_id (UUID):
        confirm (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ErrorData
    """

    return (
        await asyncio_detailed(
            workflow_id=workflow_id,
            client=client,
            confirm=confirm,
        )
    ).parsed
