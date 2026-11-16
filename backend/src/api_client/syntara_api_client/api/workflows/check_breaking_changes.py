from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.breaking_changes_response import BreakingChangesResponse
from ...models.error_data import ErrorData
from ...models.workflow_validate_request import WorkflowValidateRequest
from ...types import Response


def _get_kwargs(
    workflow_id: UUID,
    *,
    body: WorkflowValidateRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": f"/workflows/{workflow_id}/check_breaking_changes",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> BreakingChangesResponse | ErrorData | None:
    if response.status_code == 200:
        response_200 = BreakingChangesResponse.from_dict(response.json())

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
) -> Response[BreakingChangesResponse | ErrorData]:
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
    body: WorkflowValidateRequest,
) -> Response[BreakingChangesResponse | ErrorData]:
    """Check for breaking changes before publishing

     Check a candidate workflow definition for SubWorkflow output contract changes.

    Compares the submitted candidate definition against the currently published version
    to detect breaking changes such as:
    - Removed outputs
    - Type changes
    - New required outputs

    This endpoint does not publish the candidate definition. It should be called before
    publishing to warn users about breaking changes that may affect parent workflows.

    Args:
        workflow_id (UUID):
        body (WorkflowValidateRequest): Request body for the workflow validation endpoint.

            The definition is accepted as a raw dict so that structurally invalid
            definitions reach the application-level validator for richer error
            reporting with node-level attribution.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BreakingChangesResponse | ErrorData]
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
    body: WorkflowValidateRequest,
) -> BreakingChangesResponse | ErrorData | None:
    """Check for breaking changes before publishing

     Check a candidate workflow definition for SubWorkflow output contract changes.

    Compares the submitted candidate definition against the currently published version
    to detect breaking changes such as:
    - Removed outputs
    - Type changes
    - New required outputs

    This endpoint does not publish the candidate definition. It should be called before
    publishing to warn users about breaking changes that may affect parent workflows.

    Args:
        workflow_id (UUID):
        body (WorkflowValidateRequest): Request body for the workflow validation endpoint.

            The definition is accepted as a raw dict so that structurally invalid
            definitions reach the application-level validator for richer error
            reporting with node-level attribution.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BreakingChangesResponse | ErrorData
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
    body: WorkflowValidateRequest,
) -> Response[BreakingChangesResponse | ErrorData]:
    """Check for breaking changes before publishing

     Check a candidate workflow definition for SubWorkflow output contract changes.

    Compares the submitted candidate definition against the currently published version
    to detect breaking changes such as:
    - Removed outputs
    - Type changes
    - New required outputs

    This endpoint does not publish the candidate definition. It should be called before
    publishing to warn users about breaking changes that may affect parent workflows.

    Args:
        workflow_id (UUID):
        body (WorkflowValidateRequest): Request body for the workflow validation endpoint.

            The definition is accepted as a raw dict so that structurally invalid
            definitions reach the application-level validator for richer error
            reporting with node-level attribution.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BreakingChangesResponse | ErrorData]
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
    body: WorkflowValidateRequest,
) -> BreakingChangesResponse | ErrorData | None:
    """Check for breaking changes before publishing

     Check a candidate workflow definition for SubWorkflow output contract changes.

    Compares the submitted candidate definition against the currently published version
    to detect breaking changes such as:
    - Removed outputs
    - Type changes
    - New required outputs

    This endpoint does not publish the candidate definition. It should be called before
    publishing to warn users about breaking changes that may affect parent workflows.

    Args:
        workflow_id (UUID):
        body (WorkflowValidateRequest): Request body for the workflow validation endpoint.

            The definition is accepted as a raw dict so that structurally invalid
            definitions reach the application-level validator for richer error
            reporting with node-level attribution.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BreakingChangesResponse | ErrorData
    """

    return (
        await asyncio_detailed(
            workflow_id=workflow_id,
            client=client,
            body=body,
        )
    ).parsed
