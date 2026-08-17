from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.aap_list_response_aap_credential import AAPListResponseAAPCredential
from ...models.error_data import ErrorData
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    search: None | str | Unset = UNSET,
    page_size: int | Unset = 50,
    credential_id: None | Unset | UUID = UNSET,
    integration_id: None | Unset | UUID = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if isinstance(additional_params, dict):
        params = additional_params

    json_search: None | str | Unset
    if isinstance(search, Unset):
        json_search = UNSET
    else:
        json_search = search
    params["search"] = json_search

    params["page_size"] = page_size

    json_credential_id: None | str | Unset
    if isinstance(credential_id, Unset):
        json_credential_id = UNSET
    elif isinstance(credential_id, UUID):
        json_credential_id = str(credential_id)
    else:
        json_credential_id = credential_id
    params["credential_id"] = json_credential_id

    json_integration_id: None | str | Unset
    if isinstance(integration_id, Unset):
        json_integration_id = UNSET
    elif isinstance(integration_id, UUID):
        json_integration_id = str(integration_id)
    else:
        json_integration_id = integration_id
    params["integration_id"] = json_integration_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/proxies/aap/credentials",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AAPListResponseAAPCredential | ErrorData | None:
    if response.status_code == 200:
        response_200 = AAPListResponseAAPCredential.from_dict(response.json())

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
) -> Response[AAPListResponseAAPCredential | ErrorData]:
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
    search: None | str | Unset = UNSET,
    page_size: int | Unset = 50,
    credential_id: None | Unset | UUID = UNSET,
    integration_id: None | Unset | UUID = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[AAPListResponseAAPCredential | ErrorData]:
    """List AAP credentials

     List Ansible Automation Platform credentials (not organization-scoped).

    Args:
        search (None | str | Unset):
        page_size (int | Unset):  Default: 50.
        credential_id (None | Unset | UUID):
        integration_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AAPListResponseAAPCredential | ErrorData]
    """

    kwargs = _get_kwargs(
        search=search,
        page_size=page_size,
        credential_id=credential_id,
        integration_id=integration_id,
        additional_params=additional_params,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    search: None | str | Unset = UNSET,
    page_size: int | Unset = 50,
    credential_id: None | Unset | UUID = UNSET,
    integration_id: None | Unset | UUID = UNSET,
) -> AAPListResponseAAPCredential | ErrorData | None:
    """List AAP credentials

     List Ansible Automation Platform credentials (not organization-scoped).

    Args:
        search (None | str | Unset):
        page_size (int | Unset):  Default: 50.
        credential_id (None | Unset | UUID):
        integration_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AAPListResponseAAPCredential | ErrorData
    """

    return sync_detailed(
        client=client,
        search=search,
        page_size=page_size,
        credential_id=credential_id,
        integration_id=integration_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    search: None | str | Unset = UNSET,
    page_size: int | Unset = 50,
    credential_id: None | Unset | UUID = UNSET,
    integration_id: None | Unset | UUID = UNSET,
) -> Response[AAPListResponseAAPCredential | ErrorData]:
    """List AAP credentials

     List Ansible Automation Platform credentials (not organization-scoped).

    Args:
        search (None | str | Unset):
        page_size (int | Unset):  Default: 50.
        credential_id (None | Unset | UUID):
        integration_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AAPListResponseAAPCredential | ErrorData]
    """

    kwargs = _get_kwargs(
        search=search,
        page_size=page_size,
        credential_id=credential_id,
        integration_id=integration_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    search: None | str | Unset = UNSET,
    page_size: int | Unset = 50,
    credential_id: None | Unset | UUID = UNSET,
    integration_id: None | Unset | UUID = UNSET,
) -> AAPListResponseAAPCredential | ErrorData | None:
    """List AAP credentials

     List Ansible Automation Platform credentials (not organization-scoped).

    Args:
        search (None | str | Unset):
        page_size (int | Unset):  Default: 50.
        credential_id (None | Unset | UUID):
        integration_id (None | Unset | UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AAPListResponseAAPCredential | ErrorData
    """

    return (
        await asyncio_detailed(
            client=client,
            search=search,
            page_size=page_size,
            credential_id=credential_id,
            integration_id=integration_id,
        )
    ).parsed
