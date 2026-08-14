from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.service_account_credential_list_response import ServiceAccountCredentialListResponse
from ...models.service_account_credential_status import ServiceAccountCredentialStatus
from ...models.service_account_credential_type import ServiceAccountCredentialType
from ...types import UNSET, Response, Unset


def _get_kwargs(
    service_account_id: UUID,
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    credential_type: None | ServiceAccountCredentialType | Unset = UNSET,
    status: None | ServiceAccountCredentialStatus | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if isinstance(additional_params, dict):
        params = additional_params

    params["limit"] = limit

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    json_sort: None | str | Unset
    if isinstance(sort, Unset):
        json_sort = UNSET
    else:
        json_sort = sort
    params["sort"] = json_sort

    params["include_total"] = include_total

    json_credential_type: None | str | Unset
    if isinstance(credential_type, Unset):
        json_credential_type = UNSET
    elif isinstance(credential_type, ServiceAccountCredentialType):
        json_credential_type = credential_type.value
    else:
        json_credential_type = credential_type
    params["credential_type"] = json_credential_type

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    elif isinstance(status, ServiceAccountCredentialStatus):
        json_status = status.value
    else:
        json_status = status
    params["status"] = json_status

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/service_accounts/{service_account_id}/credentials",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | ServiceAccountCredentialListResponse | None:
    if response.status_code == 200:
        response_200 = ServiceAccountCredentialListResponse.from_dict(response.json())

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
) -> Response[ErrorData | ServiceAccountCredentialListResponse]:
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
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    credential_type: None | ServiceAccountCredentialType | Unset = UNSET,
    status: None | ServiceAccountCredentialStatus | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | ServiceAccountCredentialListResponse]:
    """List service account credentials

     List credentials for a service account with pagination.

    Args:
        service_account_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        credential_type (None | ServiceAccountCredentialType | Unset): Filter by credential type
        status (None | ServiceAccountCredentialStatus | Unset): Filter by status

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ServiceAccountCredentialListResponse]
    """

    kwargs = _get_kwargs(
        service_account_id=service_account_id,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        credential_type=credential_type,
        status=status,
        additional_params=additional_params,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    service_account_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    credential_type: None | ServiceAccountCredentialType | Unset = UNSET,
    status: None | ServiceAccountCredentialStatus | Unset = UNSET,
) -> ErrorData | ServiceAccountCredentialListResponse | None:
    """List service account credentials

     List credentials for a service account with pagination.

    Args:
        service_account_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        credential_type (None | ServiceAccountCredentialType | Unset): Filter by credential type
        status (None | ServiceAccountCredentialStatus | Unset): Filter by status

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ServiceAccountCredentialListResponse
    """

    return sync_detailed(
        service_account_id=service_account_id,
        client=client,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        credential_type=credential_type,
        status=status,
    ).parsed


async def asyncio_detailed(
    service_account_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    credential_type: None | ServiceAccountCredentialType | Unset = UNSET,
    status: None | ServiceAccountCredentialStatus | Unset = UNSET,
) -> Response[ErrorData | ServiceAccountCredentialListResponse]:
    """List service account credentials

     List credentials for a service account with pagination.

    Args:
        service_account_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        credential_type (None | ServiceAccountCredentialType | Unset): Filter by credential type
        status (None | ServiceAccountCredentialStatus | Unset): Filter by status

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | ServiceAccountCredentialListResponse]
    """

    kwargs = _get_kwargs(
        service_account_id=service_account_id,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        credential_type=credential_type,
        status=status,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    service_account_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    credential_type: None | ServiceAccountCredentialType | Unset = UNSET,
    status: None | ServiceAccountCredentialStatus | Unset = UNSET,
) -> ErrorData | ServiceAccountCredentialListResponse | None:
    """List service account credentials

     List credentials for a service account with pagination.

    Args:
        service_account_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        credential_type (None | ServiceAccountCredentialType | Unset): Filter by credential type
        status (None | ServiceAccountCredentialStatus | Unset): Filter by status

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | ServiceAccountCredentialListResponse
    """

    return (
        await asyncio_detailed(
            service_account_id=service_account_id,
            client=client,
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
            credential_type=credential_type,
            status=status,
        )
    ).parsed
