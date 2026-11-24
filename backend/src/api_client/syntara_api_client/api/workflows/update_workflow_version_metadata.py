from http import HTTPStatus
from typing import Any, cast
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.workflow_version_read import WorkflowVersionRead
from ...models.workflow_version_update import WorkflowVersionUpdate
from ...models.workflow_write_forbidden_problem_detail import WorkflowWriteForbiddenProblemDetail
from ...types import Response


def _get_kwargs(
    workflow_id: UUID,
    version: int,
    *,
    body: WorkflowVersionUpdate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": f"/workflows/{workflow_id}/versions/{version}",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | ErrorData | WorkflowVersionRead | WorkflowWriteForbiddenProblemDetail | None:
    if response.status_code == 200:
        response_200 = WorkflowVersionRead.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = ErrorData.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = ErrorData.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = WorkflowWriteForbiddenProblemDetail.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = cast(Any, None)
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
) -> Response[Any | ErrorData | WorkflowVersionRead | WorkflowWriteForbiddenProblemDetail]:
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
    version: int,
    *,
    client: AuthenticatedClient,
    body: WorkflowVersionUpdate,
) -> Response[Any | ErrorData | WorkflowVersionRead | WorkflowWriteForbiddenProblemDetail]:
    """Update workflow version metadata

     Update a workflow version's metadata (name, change_description).

    Args:
        workflow_id (UUID):
        version (int):
        body (WorkflowVersionUpdate): Request body for updating version metadata (PATCH
            /workflows/{id}/versions/{version}).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ErrorData | WorkflowVersionRead | WorkflowWriteForbiddenProblemDetail]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        version=version,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    workflow_id: UUID,
    version: int,
    *,
    client: AuthenticatedClient,
    body: WorkflowVersionUpdate,
) -> Any | ErrorData | WorkflowVersionRead | WorkflowWriteForbiddenProblemDetail | None:
    """Update workflow version metadata

     Update a workflow version's metadata (name, change_description).

    Args:
        workflow_id (UUID):
        version (int):
        body (WorkflowVersionUpdate): Request body for updating version metadata (PATCH
            /workflows/{id}/versions/{version}).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ErrorData | WorkflowVersionRead | WorkflowWriteForbiddenProblemDetail
    """

    return sync_detailed(
        workflow_id=workflow_id,
        version=version,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    workflow_id: UUID,
    version: int,
    *,
    client: AuthenticatedClient,
    body: WorkflowVersionUpdate,
) -> Response[Any | ErrorData | WorkflowVersionRead | WorkflowWriteForbiddenProblemDetail]:
    """Update workflow version metadata

     Update a workflow version's metadata (name, change_description).

    Args:
        workflow_id (UUID):
        version (int):
        body (WorkflowVersionUpdate): Request body for updating version metadata (PATCH
            /workflows/{id}/versions/{version}).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ErrorData | WorkflowVersionRead | WorkflowWriteForbiddenProblemDetail]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        version=version,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workflow_id: UUID,
    version: int,
    *,
    client: AuthenticatedClient,
    body: WorkflowVersionUpdate,
) -> Any | ErrorData | WorkflowVersionRead | WorkflowWriteForbiddenProblemDetail | None:
    """Update workflow version metadata

     Update a workflow version's metadata (name, change_description).

    Args:
        workflow_id (UUID):
        version (int):
        body (WorkflowVersionUpdate): Request body for updating version metadata (PATCH
            /workflows/{id}/versions/{version}).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ErrorData | WorkflowVersionRead | WorkflowWriteForbiddenProblemDetail
    """

    return (
        await asyncio_detailed(
            workflow_id=workflow_id,
            version=version,
            client=client,
            body=body,
        )
    ).parsed
