from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.integration_project_assignment_read import IntegrationProjectAssignmentRead
from ...types import Response


def _get_kwargs(
    integration_id: UUID,
    project_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": f"/api/v2/integrations/{integration_id}/projects/{project_id}",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | IntegrationProjectAssignmentRead | None:
    if response.status_code == 201:
        response_201 = IntegrationProjectAssignmentRead.from_dict(response.json())

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
) -> Response[ErrorData | IntegrationProjectAssignmentRead]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    integration_id: UUID,
    project_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[ErrorData | IntegrationProjectAssignmentRead]:
    """Assign integration project

     Assign a project to a project-scoped integration.

    Args:
        integration_id (UUID):
        project_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | IntegrationProjectAssignmentRead]
    """

    kwargs = _get_kwargs(
        integration_id=integration_id,
        project_id=project_id,
    )

    httpx_client = client.get_httpx_client()
    # Path-level servers select v2 while existing clients may use a v1 base URL.
    api_root = httpx_client.base_url.path.rstrip("/").rsplit("/api/", 1)[0].removesuffix("/api")
    kwargs["url"] = httpx_client.base_url.copy_with(path=f"{api_root}{kwargs['url']}")
    response = httpx_client.request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    integration_id: UUID,
    project_id: UUID,
    *,
    client: AuthenticatedClient,
) -> ErrorData | IntegrationProjectAssignmentRead | None:
    """Assign integration project

     Assign a project to a project-scoped integration.

    Args:
        integration_id (UUID):
        project_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | IntegrationProjectAssignmentRead
    """

    return sync_detailed(
        integration_id=integration_id,
        project_id=project_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    integration_id: UUID,
    project_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[ErrorData | IntegrationProjectAssignmentRead]:
    """Assign integration project

     Assign a project to a project-scoped integration.

    Args:
        integration_id (UUID):
        project_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | IntegrationProjectAssignmentRead]
    """

    kwargs = _get_kwargs(
        integration_id=integration_id,
        project_id=project_id,
    )

    httpx_client = client.get_async_httpx_client()
    # Preserve any deployment prefix while selecting the endpoint's API version.
    api_root = httpx_client.base_url.path.rstrip("/").rsplit("/api/", 1)[0].removesuffix("/api")
    kwargs["url"] = httpx_client.base_url.copy_with(path=f"{api_root}{kwargs['url']}")
    response = await httpx_client.request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    integration_id: UUID,
    project_id: UUID,
    *,
    client: AuthenticatedClient,
) -> ErrorData | IntegrationProjectAssignmentRead | None:
    """Assign integration project

     Assign a project to a project-scoped integration.

    Args:
        integration_id (UUID):
        project_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | IntegrationProjectAssignmentRead
    """

    return (
        await asyncio_detailed(
            integration_id=integration_id,
            project_id=project_id,
            client=client,
        )
    ).parsed
