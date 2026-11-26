from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.role_assignment_create import RoleAssignmentCreate
from ...models.role_assignment_read import RoleAssignmentRead
from ...types import Response


def _get_kwargs(
    *,
    body: RoleAssignmentCreate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/role_assignments",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | RoleAssignmentRead | None:
    if response.status_code == 201:
        response_201 = RoleAssignmentRead.from_dict(response.json())

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
) -> Response[ErrorData | RoleAssignmentRead]:
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
    body: RoleAssignmentCreate,
) -> Response[ErrorData | RoleAssignmentRead]:
    """Create role assignment

     Assign a role to a user or group.

    When project_id is provided the assignment is project-scoped; when
    project_pattern is provided it applies (deny-only) to every project whose
    name matches; otherwise it is a global (system-level) assignment.

    Args:
        body (RoleAssignmentCreate): Request body for creating a role assignment.

            Exactly one of ``principal_id`` or ``group_id`` must be provided.
            At most one of ``project_id`` or ``project_pattern`` may be provided.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | RoleAssignmentRead]
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
    body: RoleAssignmentCreate,
) -> ErrorData | RoleAssignmentRead | None:
    """Create role assignment

     Assign a role to a user or group.

    When project_id is provided the assignment is project-scoped; when
    project_pattern is provided it applies (deny-only) to every project whose
    name matches; otherwise it is a global (system-level) assignment.

    Args:
        body (RoleAssignmentCreate): Request body for creating a role assignment.

            Exactly one of ``principal_id`` or ``group_id`` must be provided.
            At most one of ``project_id`` or ``project_pattern`` may be provided.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | RoleAssignmentRead
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: RoleAssignmentCreate,
) -> Response[ErrorData | RoleAssignmentRead]:
    """Create role assignment

     Assign a role to a user or group.

    When project_id is provided the assignment is project-scoped; when
    project_pattern is provided it applies (deny-only) to every project whose
    name matches; otherwise it is a global (system-level) assignment.

    Args:
        body (RoleAssignmentCreate): Request body for creating a role assignment.

            Exactly one of ``principal_id`` or ``group_id`` must be provided.
            At most one of ``project_id`` or ``project_pattern`` may be provided.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | RoleAssignmentRead]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: RoleAssignmentCreate,
) -> ErrorData | RoleAssignmentRead | None:
    """Create role assignment

     Assign a role to a user or group.

    When project_id is provided the assignment is project-scoped; when
    project_pattern is provided it applies (deny-only) to every project whose
    name matches; otherwise it is a global (system-level) assignment.

    Args:
        body (RoleAssignmentCreate): Request body for creating a role assignment.

            Exactly one of ``principal_id`` or ``group_id`` must be provided.
            At most one of ``project_id`` or ``project_pattern`` may be provided.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | RoleAssignmentRead
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
