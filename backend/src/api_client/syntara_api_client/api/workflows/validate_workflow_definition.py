from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.detailed_validation_problem_detail import DetailedValidationProblemDetail
from ...models.error_data import ErrorData
from ...models.validation_result import ValidationResult
from ...models.workflow_validate_request import WorkflowValidateRequest
from ...types import Response


def _get_kwargs(
    *,
    body: WorkflowValidateRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/workflows/validate",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DetailedValidationProblemDetail | ErrorData | ValidationResult | None:
    if response.status_code == 200:
        response_200 = ValidationResult.from_dict(response.json())

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
        response_422 = DetailedValidationProblemDetail.from_dict(response.json())

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
) -> Response[DetailedValidationProblemDetail | ErrorData | ValidationResult]:
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
    body: WorkflowValidateRequest,
) -> Response[DetailedValidationProblemDetail | ErrorData | ValidationResult]:
    """Validate workflow definition

     Validate a workflow definition without saving it.

    Requires authentication but no specific workflow/project permission:
    validation is a stateless, side-effect-free check of caller-supplied
    data with no workflow_id or project_id in scope to authorize against.

    Args:
        body (WorkflowValidateRequest): Request body for the workflow validation endpoint.

            The definition is accepted as a raw dict so that structurally invalid
            definitions reach the application-level validator for richer error
            reporting with node-level attribution.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DetailedValidationProblemDetail | ErrorData | ValidationResult]
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
    body: WorkflowValidateRequest,
) -> DetailedValidationProblemDetail | ErrorData | ValidationResult | None:
    """Validate workflow definition

     Validate a workflow definition without saving it.

    Requires authentication but no specific workflow/project permission:
    validation is a stateless, side-effect-free check of caller-supplied
    data with no workflow_id or project_id in scope to authorize against.

    Args:
        body (WorkflowValidateRequest): Request body for the workflow validation endpoint.

            The definition is accepted as a raw dict so that structurally invalid
            definitions reach the application-level validator for richer error
            reporting with node-level attribution.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DetailedValidationProblemDetail | ErrorData | ValidationResult
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: WorkflowValidateRequest,
) -> Response[DetailedValidationProblemDetail | ErrorData | ValidationResult]:
    """Validate workflow definition

     Validate a workflow definition without saving it.

    Requires authentication but no specific workflow/project permission:
    validation is a stateless, side-effect-free check of caller-supplied
    data with no workflow_id or project_id in scope to authorize against.

    Args:
        body (WorkflowValidateRequest): Request body for the workflow validation endpoint.

            The definition is accepted as a raw dict so that structurally invalid
            definitions reach the application-level validator for richer error
            reporting with node-level attribution.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DetailedValidationProblemDetail | ErrorData | ValidationResult]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: WorkflowValidateRequest,
) -> DetailedValidationProblemDetail | ErrorData | ValidationResult | None:
    """Validate workflow definition

     Validate a workflow definition without saving it.

    Requires authentication but no specific workflow/project permission:
    validation is a stateless, side-effect-free check of caller-supplied
    data with no workflow_id or project_id in scope to authorize against.

    Args:
        body (WorkflowValidateRequest): Request body for the workflow validation endpoint.

            The definition is accepted as a raw dict so that structurally invalid
            definitions reach the application-level validator for richer error
            reporting with node-level attribution.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DetailedValidationProblemDetail | ErrorData | ValidationResult
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
