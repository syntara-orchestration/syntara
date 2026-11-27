from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.credential_create import CredentialCreate
from ...models.credential_read import CredentialRead
from ...models.error_data import ErrorData
from ...types import Response


def _get_kwargs(
    *,
    body: CredentialCreate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/credentials",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CredentialRead | ErrorData | None:
    if response.status_code == 201:
        response_201 = CredentialRead.from_dict(response.json())

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
    *,
    client: AuthenticatedClient,
    body: CredentialCreate,
) -> Response[CredentialRead | ErrorData]:
    """Create credential

     Create a new Credential with encrypted inputs.

    The mTLS Client Identity type requires `client_certificate` and `client_private_key` in PEM format.
    An optional `client_key_passphrase` must contain at least four characters.
    A 422 response can identify the invalid field using `MTLS_INVALID_CLIENT_CERTIFICATE`,
    `MTLS_INVALID_PRIVATE_KEY`, `MTLS_WRONG_PASSPHRASE`, or `MTLS_CERTIFICATE_KEY_MISMATCH`.

    Args:
        body (CredentialCreate): Schema for creating a new credential.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CredentialRead | ErrorData]
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
    body: CredentialCreate,
) -> CredentialRead | ErrorData | None:
    """Create credential

     Create a new Credential with encrypted inputs.

    The mTLS Client Identity type requires `client_certificate` and `client_private_key` in PEM format.
    An optional `client_key_passphrase` must contain at least four characters.
    A 422 response can identify the invalid field using `MTLS_INVALID_CLIENT_CERTIFICATE`,
    `MTLS_INVALID_PRIVATE_KEY`, `MTLS_WRONG_PASSPHRASE`, or `MTLS_CERTIFICATE_KEY_MISMATCH`.

    Args:
        body (CredentialCreate): Schema for creating a new credential.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CredentialRead | ErrorData
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: CredentialCreate,
) -> Response[CredentialRead | ErrorData]:
    """Create credential

     Create a new Credential with encrypted inputs.

    The mTLS Client Identity type requires `client_certificate` and `client_private_key` in PEM format.
    An optional `client_key_passphrase` must contain at least four characters.
    A 422 response can identify the invalid field using `MTLS_INVALID_CLIENT_CERTIFICATE`,
    `MTLS_INVALID_PRIVATE_KEY`, `MTLS_WRONG_PASSPHRASE`, or `MTLS_CERTIFICATE_KEY_MISMATCH`.

    Args:
        body (CredentialCreate): Schema for creating a new credential.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CredentialRead | ErrorData]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: CredentialCreate,
) -> CredentialRead | ErrorData | None:
    """Create credential

     Create a new Credential with encrypted inputs.

    The mTLS Client Identity type requires `client_certificate` and `client_private_key` in PEM format.
    An optional `client_key_passphrase` must contain at least four characters.
    A 422 response can identify the invalid field using `MTLS_INVALID_CLIENT_CERTIFICATE`,
    `MTLS_INVALID_PRIVATE_KEY`, `MTLS_WRONG_PASSPHRASE`, or `MTLS_CERTIFICATE_KEY_MISMATCH`.

    Args:
        body (CredentialCreate): Schema for creating a new credential.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CredentialRead | ErrorData
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
