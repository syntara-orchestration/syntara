from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.service_account_credential_rotate_request import ServiceAccountCredentialRotateRequest
from ...models.service_account_credential_rotate_response import ServiceAccountCredentialRotateResponse
from ...types import Response


def _get_kwargs(
    service_account_id: UUID,
    credential_id: UUID,
    *,
    body: ServiceAccountCredentialRotateRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": f"/service_accounts/{service_account_id}/credentials/{credential_id}/rotate",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ServiceAccountCredentialRotateResponse | None:
    if response.status_code == 200:
        response_200 = ServiceAccountCredentialRotateResponse.from_dict(response.json())

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
) -> Response[ErrorData | ServiceAccountCredentialRotateResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    service_account_id: UUID,
    credential_id: UUID,
    *,
    client: AuthenticatedClient,
    body: ServiceAccountCredentialRotateRequest,
) -> Response[ErrorData | ServiceAccountCredentialRotateResponse]:
    """Rotate service account credential

     Rotate a credential's secret; returns the new one-time plaintext secret.

    Args:
        service_account_id (UUID):
        credential_id (UUID):
        body (ServiceAccountCredentialRotateRequest): Schema for rotating a credential's secret.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ServiceAccountCredentialRotateResponse]
    """

    kwargs = _get_kwargs(
        service_account_id=service_account_id,
        credential_id=credential_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    service_account_id: UUID,
    credential_id: UUID,
    *,
    client: AuthenticatedClient,
    body: ServiceAccountCredentialRotateRequest,
) -> ErrorData | ServiceAccountCredentialRotateResponse | None:
    """Rotate service account credential

     Rotate a credential's secret; returns the new one-time plaintext secret.

    Args:
        service_account_id (UUID):
        credential_id (UUID):
        body (ServiceAccountCredentialRotateRequest): Schema for rotating a credential's secret.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ServiceAccountCredentialRotateResponse
    """

    return sync_detailed(
        service_account_id=service_account_id,
        credential_id=credential_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    service_account_id: UUID,
    credential_id: UUID,
    *,
    client: AuthenticatedClient,
    body: ServiceAccountCredentialRotateRequest,
) -> Response[ErrorData | ServiceAccountCredentialRotateResponse]:
    """Rotate service account credential

     Rotate a credential's secret; returns the new one-time plaintext secret.

    Args:
        service_account_id (UUID):
        credential_id (UUID):
        body (ServiceAccountCredentialRotateRequest): Schema for rotating a credential's secret.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ServiceAccountCredentialRotateResponse]
    """

    kwargs = _get_kwargs(
        service_account_id=service_account_id,
        credential_id=credential_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    service_account_id: UUID,
    credential_id: UUID,
    *,
    client: AuthenticatedClient,
    body: ServiceAccountCredentialRotateRequest,
) -> ErrorData | ServiceAccountCredentialRotateResponse | None:
    """Rotate service account credential

     Rotate a credential's secret; returns the new one-time plaintext secret.

    Args:
        service_account_id (UUID):
        credential_id (UUID):
        body (ServiceAccountCredentialRotateRequest): Schema for rotating a credential's secret.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ServiceAccountCredentialRotateResponse
    """

    return (
        await asyncio_detailed(
            service_account_id=service_account_id,
            credential_id=credential_id,
            client=client,
            body=body,
        )
    ).parsed
