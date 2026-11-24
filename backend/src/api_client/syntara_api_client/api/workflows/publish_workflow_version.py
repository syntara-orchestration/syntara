from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.publish_version_request import PublishVersionRequest
from ...models.publish_workflow_version_response import PublishWorkflowVersionResponse
from ...models.workflow_publish_trigger_removal_confirmation_problem import (
    WorkflowPublishTriggerRemovalConfirmationProblem,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    workflow_id: UUID,
    version: int,
    *,
    body: PublishVersionRequest,
    confirm: bool | Unset = False,
    additional_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    params: dict[str, Any] = {}
    if isinstance(additional_params, dict):
        params = additional_params

    params["confirm"] = confirm

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": f"/workflows/{workflow_id}/versions/{version}/publish",
        "params": params,
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ErrorData | WorkflowPublishTriggerRemovalConfirmationProblem | PublishWorkflowVersionResponse | None:
    if response.status_code == 200:
        response_200 = PublishWorkflowVersionResponse.from_dict(response.json())

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

        def _parse_response_409(data: object) -> ErrorData | WorkflowPublishTriggerRemovalConfirmationProblem:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_409_type_0 = WorkflowPublishTriggerRemovalConfirmationProblem.from_dict(data)

                return response_409_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            response_409_type_1 = ErrorData.from_dict(data)

            return response_409_type_1

        response_409 = _parse_response_409(response.json())

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
) -> Response[
    ErrorData | ErrorData | WorkflowPublishTriggerRemovalConfirmationProblem | PublishWorkflowVersionResponse
]:
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
    body: PublishVersionRequest,
    confirm: bool | Unset = False,
    additional_params: dict[str, Any] | None = None,
) -> Response[
    ErrorData | ErrorData | WorkflowPublishTriggerRemovalConfirmationProblem | PublishWorkflowVersionResponse
]:
    """Publish workflow version

     Publish a specific workflow version.

    If publishing removes a Subworkflow Trigger that published parents invoke, it requires
    ``confirm=true``; otherwise it returns 409 with the count of affected parents (no parent details).

    Args:
        workflow_id (UUID):
        version (int):
        confirm (bool | Unset):  Default: False.
        body (PublishVersionRequest): Request body for publishing a workflow version.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ErrorData | WorkflowPublishTriggerRemovalConfirmationProblem | PublishWorkflowVersionResponse]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id, version=version, body=body, confirm=confirm, additional_params=additional_params
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
    body: PublishVersionRequest,
    confirm: bool | Unset = False,
) -> ErrorData | ErrorData | WorkflowPublishTriggerRemovalConfirmationProblem | PublishWorkflowVersionResponse | None:
    """Publish workflow version

     Publish a specific workflow version.

    If publishing removes a Subworkflow Trigger that published parents invoke, it requires
    ``confirm=true``; otherwise it returns 409 with the count of affected parents (no parent details).

    Args:
        workflow_id (UUID):
        version (int):
        confirm (bool | Unset):  Default: False.
        body (PublishVersionRequest): Request body for publishing a workflow version.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ErrorData | WorkflowPublishTriggerRemovalConfirmationProblem | PublishWorkflowVersionResponse
    """

    return sync_detailed(
        workflow_id=workflow_id,
        version=version,
        client=client,
        body=body,
        confirm=confirm,
    ).parsed


async def asyncio_detailed(
    workflow_id: UUID,
    version: int,
    *,
    client: AuthenticatedClient,
    body: PublishVersionRequest,
    confirm: bool | Unset = False,
) -> Response[
    ErrorData | ErrorData | WorkflowPublishTriggerRemovalConfirmationProblem | PublishWorkflowVersionResponse
]:
    """Publish workflow version

     Publish a specific workflow version.

    If publishing removes a Subworkflow Trigger that published parents invoke, it requires
    ``confirm=true``; otherwise it returns 409 with the count of affected parents (no parent details).

    Args:
        workflow_id (UUID):
        version (int):
        confirm (bool | Unset):  Default: False.
        body (PublishVersionRequest): Request body for publishing a workflow version.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ErrorData | WorkflowPublishTriggerRemovalConfirmationProblem | PublishWorkflowVersionResponse]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        version=version,
        body=body,
        confirm=confirm,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workflow_id: UUID,
    version: int,
    *,
    client: AuthenticatedClient,
    body: PublishVersionRequest,
    confirm: bool | Unset = False,
) -> ErrorData | ErrorData | WorkflowPublishTriggerRemovalConfirmationProblem | PublishWorkflowVersionResponse | None:
    """Publish workflow version

     Publish a specific workflow version.

    If publishing removes a Subworkflow Trigger that published parents invoke, it requires
    ``confirm=true``; otherwise it returns 409 with the count of affected parents (no parent details).

    Args:
        workflow_id (UUID):
        version (int):
        confirm (bool | Unset):  Default: False.
        body (PublishVersionRequest): Request body for publishing a workflow version.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ErrorData | WorkflowPublishTriggerRemovalConfirmationProblem | PublishWorkflowVersionResponse
    """

    return (
        await asyncio_detailed(
            workflow_id=workflow_id,
            version=version,
            client=client,
            body=body,
            confirm=confirm,
        )
    ).parsed
