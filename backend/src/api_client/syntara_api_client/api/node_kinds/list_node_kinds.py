from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.step_type_permission_read import StepTypePermissionRead
from ...types import UNSET, Response


def _get_kwargs(*, project_id: UUID, additional_params: dict[str, Any] | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if isinstance(additional_params, dict):
        params = additional_params

    json_project_id = str(project_id)
    params["project_id"] = json_project_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/node_kinds",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | list[StepTypePermissionRead] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = StepTypePermissionRead.from_dict(response_200_item_data)

            response_200.append(response_200_item)

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
) -> Response[ErrorData | list[StepTypePermissionRead]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    *, client: AuthenticatedClient, project_id: UUID, additional_params: dict[str, Any] | None = None
) -> Response[ErrorData | list[StepTypePermissionRead]]:
    """List step types with the caller's write verdicts

     List every registered step type with the caller's own write verdicts.

    Requires authentication but no specific permission: the response is scoped
    to the caller and describes reference data plus the caller's own verdicts
    in the requested project. One request evaluates every step type, so the
    add-step panel never needs per-kind ``can_i`` calls.

    Args:
        project_id (UUID): Project the verdicts are evaluated in

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | list[StepTypePermissionRead]]
    """

    kwargs = _get_kwargs(project_id=project_id, additional_params=additional_params)

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    project_id: UUID,
) -> ErrorData | list[StepTypePermissionRead] | None:
    """List step types with the caller's write verdicts

     List every registered step type with the caller's own write verdicts.

    Requires authentication but no specific permission: the response is scoped
    to the caller and describes reference data plus the caller's own verdicts
    in the requested project. One request evaluates every step type, so the
    add-step panel never needs per-kind ``can_i`` calls.

    Args:
        project_id (UUID): Project the verdicts are evaluated in

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | list[StepTypePermissionRead]
    """

    return sync_detailed(
        client=client,
        project_id=project_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    project_id: UUID,
) -> Response[ErrorData | list[StepTypePermissionRead]]:
    """List step types with the caller's write verdicts

     List every registered step type with the caller's own write verdicts.

    Requires authentication but no specific permission: the response is scoped
    to the caller and describes reference data plus the caller's own verdicts
    in the requested project. One request evaluates every step type, so the
    add-step panel never needs per-kind ``can_i`` calls.

    Args:
        project_id (UUID): Project the verdicts are evaluated in

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | list[StepTypePermissionRead]]
    """

    kwargs = _get_kwargs(
        project_id=project_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    project_id: UUID,
) -> ErrorData | list[StepTypePermissionRead] | None:
    """List step types with the caller's write verdicts

     List every registered step type with the caller's own write verdicts.

    Requires authentication but no specific permission: the response is scoped
    to the caller and describes reference data plus the caller's own verdicts
    in the requested project. One request evaluates every step type, so the
    add-step panel never needs per-kind ``can_i`` calls.

    Args:
        project_id (UUID): Project the verdicts are evaluated in

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | list[StepTypePermissionRead]
    """

    return (
        await asyncio_detailed(
            client=client,
            project_id=project_id,
        )
    ).parsed
