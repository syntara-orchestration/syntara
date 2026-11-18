from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.workflow_read_with_version import WorkflowReadWithVersion
from ...models.workflow_write_forbidden_problem_detail import WorkflowWriteForbiddenProblemDetail
from ...types import Response


def _get_kwargs(
    workflow_id: UUID,
    version: int,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": f"/workflows/{workflow_id}/versions/{version}/restore",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | WorkflowReadWithVersion | WorkflowWriteForbiddenProblemDetail | None:
    if response.status_code == 200:
        response_200 = WorkflowReadWithVersion.from_dict(response.json())

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
) -> Response[ErrorData | WorkflowReadWithVersion | WorkflowWriteForbiddenProblemDetail]:
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
) -> Response[ErrorData | WorkflowReadWithVersion | WorkflowWriteForbiddenProblemDetail]:
    """Restore workflow version

     Restore a previous workflow version as a new draft.

    Args:
        workflow_id (UUID):
        version (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | WorkflowReadWithVersion | WorkflowWriteForbiddenProblemDetail]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        version=version,
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
) -> ErrorData | WorkflowReadWithVersion | WorkflowWriteForbiddenProblemDetail | None:
    """Restore workflow version

     Restore a previous workflow version as a new draft.

    Args:
        workflow_id (UUID):
        version (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | WorkflowReadWithVersion | WorkflowWriteForbiddenProblemDetail
    """

    return sync_detailed(
        workflow_id=workflow_id,
        version=version,
        client=client,
    ).parsed


async def asyncio_detailed(
    workflow_id: UUID,
    version: int,
    *,
    client: AuthenticatedClient,
) -> Response[ErrorData | WorkflowReadWithVersion | WorkflowWriteForbiddenProblemDetail]:
    """Restore workflow version

     Restore a previous workflow version as a new draft.

    Args:
        workflow_id (UUID):
        version (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | WorkflowReadWithVersion | WorkflowWriteForbiddenProblemDetail]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        version=version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workflow_id: UUID,
    version: int,
    *,
    client: AuthenticatedClient,
) -> ErrorData | WorkflowReadWithVersion | WorkflowWriteForbiddenProblemDetail | None:
    """Restore workflow version

     Restore a previous workflow version as a new draft.

    Args:
        workflow_id (UUID):
        version (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | WorkflowReadWithVersion | WorkflowWriteForbiddenProblemDetail
    """

    return (
        await asyncio_detailed(
            workflow_id=workflow_id,
            version=version,
            client=client,
        )
    ).parsed
