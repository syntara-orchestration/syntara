from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.node_kind_write_denied_problem_detail import NodeKindWriteDeniedProblemDetail
from ...models.workflow_read_with_version import WorkflowReadWithVersion
from ...models.workflow_update import WorkflowUpdate
from ...types import Response


def _get_kwargs(
    workflow_id: UUID,
    *,
    body: WorkflowUpdate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": f"/workflows/{workflow_id}",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ErrorData | NodeKindWriteDeniedProblemDetail | WorkflowReadWithVersion | None:
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

        def _parse_response_403(data: object) -> ErrorData | NodeKindWriteDeniedProblemDetail:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_403_type_0 = NodeKindWriteDeniedProblemDetail.from_dict(data)

                return response_403_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            response_403_type_1 = ErrorData.from_dict(data)

            return response_403_type_1

        response_403 = _parse_response_403(response.json())

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
) -> Response[ErrorData | ErrorData | NodeKindWriteDeniedProblemDetail | WorkflowReadWithVersion]:
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
    body: WorkflowUpdate,
) -> Response[ErrorData | ErrorData | NodeKindWriteDeniedProblemDetail | WorkflowReadWithVersion]:
    """Update workflow

     Update workflow.

    Supports both metadata-only updates and workflow definition updates:
    - Metadata only (name, description, labels): Updates without creating new version
    - With workflow_definition: Validates definition, compares with current version, creates new
    WorkflowVersion
      only if definition differs (change detection optimization)

    Args:
        workflow_id (UUID):
        body (WorkflowUpdate): Schema for updating workflow (PATCH /workflows/{id}).

            All fields are optional for partial updates.
            Supports metadata updates and workflow definition updates (creates new version).
            Pydantic tries to parse workflow_definition as WorkflowDefinition first;
            on failure, the raw dict falls through to the service-level validator.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ErrorData | NodeKindWriteDeniedProblemDetail | WorkflowReadWithVersion]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    workflow_id: UUID,
    *,
    client: AuthenticatedClient,
    body: WorkflowUpdate,
) -> ErrorData | ErrorData | NodeKindWriteDeniedProblemDetail | WorkflowReadWithVersion | None:
    """Update workflow

     Update workflow.

    Supports both metadata-only updates and workflow definition updates:
    - Metadata only (name, description, labels): Updates without creating new version
    - With workflow_definition: Validates definition, compares with current version, creates new
    WorkflowVersion
      only if definition differs (change detection optimization)

    Args:
        workflow_id (UUID):
        body (WorkflowUpdate): Schema for updating workflow (PATCH /workflows/{id}).

            All fields are optional for partial updates.
            Supports metadata updates and workflow definition updates (creates new version).
            Pydantic tries to parse workflow_definition as WorkflowDefinition first;
            on failure, the raw dict falls through to the service-level validator.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ErrorData | NodeKindWriteDeniedProblemDetail | WorkflowReadWithVersion
    """

    return sync_detailed(
        workflow_id=workflow_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    workflow_id: UUID,
    *,
    client: AuthenticatedClient,
    body: WorkflowUpdate,
) -> Response[ErrorData | ErrorData | NodeKindWriteDeniedProblemDetail | WorkflowReadWithVersion]:
    """Update workflow

     Update workflow.

    Supports both metadata-only updates and workflow definition updates:
    - Metadata only (name, description, labels): Updates without creating new version
    - With workflow_definition: Validates definition, compares with current version, creates new
    WorkflowVersion
      only if definition differs (change detection optimization)

    Args:
        workflow_id (UUID):
        body (WorkflowUpdate): Schema for updating workflow (PATCH /workflows/{id}).

            All fields are optional for partial updates.
            Supports metadata updates and workflow definition updates (creates new version).
            Pydantic tries to parse workflow_definition as WorkflowDefinition first;
            on failure, the raw dict falls through to the service-level validator.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ErrorData | NodeKindWriteDeniedProblemDetail | WorkflowReadWithVersion]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workflow_id: UUID,
    *,
    client: AuthenticatedClient,
    body: WorkflowUpdate,
) -> ErrorData | ErrorData | NodeKindWriteDeniedProblemDetail | WorkflowReadWithVersion | None:
    """Update workflow

     Update workflow.

    Supports both metadata-only updates and workflow definition updates:
    - Metadata only (name, description, labels): Updates without creating new version
    - With workflow_definition: Validates definition, compares with current version, creates new
    WorkflowVersion
      only if definition differs (change detection optimization)

    Args:
        workflow_id (UUID):
        body (WorkflowUpdate): Schema for updating workflow (PATCH /workflows/{id}).

            All fields are optional for partial updates.
            Supports metadata updates and workflow definition updates (creates new version).
            Pydantic tries to parse workflow_definition as WorkflowDefinition first;
            on failure, the raw dict falls through to the service-level validator.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ErrorData | NodeKindWriteDeniedProblemDetail | WorkflowReadWithVersion
    """

    return (
        await asyncio_detailed(
            workflow_id=workflow_id,
            client=client,
            body=body,
        )
    ).parsed
