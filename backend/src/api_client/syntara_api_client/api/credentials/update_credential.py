from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.credential_read import CredentialRead
from ...models.credential_update import CredentialUpdate
from ...models.error_data import ErrorData
from ...types import Response


def _get_kwargs(
    credential_id: UUID,
    *,
    body: CredentialUpdate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": f"/credentials/{credential_id}",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CredentialRead | ErrorData | None:
    if response.status_code == 200:
        response_200 = CredentialRead.from_dict(response.json())

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
) -> Response[CredentialRead | ErrorData]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    credential_id: UUID,
    *,
    client: AuthenticatedClient,
    body: CredentialUpdate,
) -> Response[CredentialRead | ErrorData]:
    """Update credential

     Update a Credential. Fields set to $encrypted$ retain existing values.

    An mTLS Client Identity is validated after the update is merged with the stored inputs.
    The same mTLS validation codes apply as on create. Set `client_key_passphrase` to null
    to clear it when replacing a protected key with an unprotected key.

    Args:
        credential_id (UUID):
        body (CredentialUpdate): Schema for partially updating a credential. $encrypted$ preserves
            existing values.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CredentialRead | ErrorData]
    """

    kwargs = _get_kwargs(
        credential_id=credential_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    credential_id: UUID,
    *,
    client: AuthenticatedClient,
    body: CredentialUpdate,
) -> CredentialRead | ErrorData | None:
    """Update credential

     Update a Credential. Fields set to $encrypted$ retain existing values.

    An mTLS Client Identity is validated after the update is merged with the stored inputs.
    The same mTLS validation codes apply as on create. Set `client_key_passphrase` to null
    to clear it when replacing a protected key with an unprotected key.

    Args:
        credential_id (UUID):
        body (CredentialUpdate): Schema for partially updating a credential. $encrypted$ preserves
            existing values.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CredentialRead | ErrorData
    """

    return sync_detailed(
        credential_id=credential_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    credential_id: UUID,
    *,
    client: AuthenticatedClient,
    body: CredentialUpdate,
) -> Response[CredentialRead | ErrorData]:
    """Update credential

     Update a Credential. Fields set to $encrypted$ retain existing values.

    An mTLS Client Identity is validated after the update is merged with the stored inputs.
    The same mTLS validation codes apply as on create. Set `client_key_passphrase` to null
    to clear it when replacing a protected key with an unprotected key.

    Args:
        credential_id (UUID):
        body (CredentialUpdate): Schema for partially updating a credential. $encrypted$ preserves
            existing values.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CredentialRead | ErrorData]
    """

    kwargs = _get_kwargs(
        credential_id=credential_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    credential_id: UUID,
    *,
    client: AuthenticatedClient,
    body: CredentialUpdate,
) -> CredentialRead | ErrorData | None:
    """Update credential

     Update a Credential. Fields set to $encrypted$ retain existing values.

    An mTLS Client Identity is validated after the update is merged with the stored inputs.
    The same mTLS validation codes apply as on create. Set `client_key_passphrase` to null
    to clear it when replacing a protected key with an unprotected key.

    Args:
        credential_id (UUID):
        body (CredentialUpdate): Schema for partially updating a credential. $encrypted$ preserves
            existing values.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CredentialRead | ErrorData
    """

    return (
        await asyncio_detailed(
            credential_id=credential_id,
            client=client,
            body=body,
        )
    ).parsed
