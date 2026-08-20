from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.list_service_account_credentials_created_at import ListServiceAccountCredentialsCreatedAt
from ...models.list_service_account_credentials_created_by import ListServiceAccountCredentialsCreatedBy
from ...models.list_service_account_credentials_credential_type import ListServiceAccountCredentialsCredentialType
from ...models.list_service_account_credentials_expires_at import ListServiceAccountCredentialsExpiresAt
from ...models.list_service_account_credentials_id import ListServiceAccountCredentialsId
from ...models.list_service_account_credentials_identifier import ListServiceAccountCredentialsIdentifier
from ...models.list_service_account_credentials_last_used_at import ListServiceAccountCredentialsLastUsedAt
from ...models.list_service_account_credentials_status import ListServiceAccountCredentialsStatus
from ...models.list_service_account_credentials_updated_at import ListServiceAccountCredentialsUpdatedAt
from ...models.list_service_account_credentials_updated_by import ListServiceAccountCredentialsUpdatedBy
from ...models.service_account_credential_list_response import ServiceAccountCredentialListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    service_account_id: UUID,
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListServiceAccountCredentialsId | Unset = UNSET,
    created_at: ListServiceAccountCredentialsCreatedAt | Unset = UNSET,
    updated_at: ListServiceAccountCredentialsUpdatedAt | Unset = UNSET,
    created_by: ListServiceAccountCredentialsCreatedBy | Unset = UNSET,
    updated_by: ListServiceAccountCredentialsUpdatedBy | Unset = UNSET,
    credential_type: ListServiceAccountCredentialsCredentialType | Unset = UNSET,
    identifier: ListServiceAccountCredentialsIdentifier | Unset = UNSET,
    status: ListServiceAccountCredentialsStatus | Unset = UNSET,
    expires_at: ListServiceAccountCredentialsExpiresAt | Unset = UNSET,
    last_used_at: ListServiceAccountCredentialsLastUsedAt | Unset = UNSET,
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

    json_id: dict[str, Any] | Unset = UNSET
    if not isinstance(id, Unset):
        json_id = id.to_dict()
    if not isinstance(json_id, Unset):
        params.update(json_id)

    json_created_at: dict[str, Any] | Unset = UNSET
    if not isinstance(created_at, Unset):
        json_created_at = created_at.to_dict()
    if not isinstance(json_created_at, Unset):
        params.update(json_created_at)

    json_updated_at: dict[str, Any] | Unset = UNSET
    if not isinstance(updated_at, Unset):
        json_updated_at = updated_at.to_dict()
    if not isinstance(json_updated_at, Unset):
        params.update(json_updated_at)

    json_created_by: dict[str, Any] | Unset = UNSET
    if not isinstance(created_by, Unset):
        json_created_by = created_by.to_dict()
    if not isinstance(json_created_by, Unset):
        params.update(json_created_by)

    json_updated_by: dict[str, Any] | Unset = UNSET
    if not isinstance(updated_by, Unset):
        json_updated_by = updated_by.to_dict()
    if not isinstance(json_updated_by, Unset):
        params.update(json_updated_by)

    json_credential_type: dict[str, Any] | Unset = UNSET
    if not isinstance(credential_type, Unset):
        json_credential_type = credential_type.to_dict()
    if not isinstance(json_credential_type, Unset):
        params.update(json_credential_type)

    json_identifier: dict[str, Any] | Unset = UNSET
    if not isinstance(identifier, Unset):
        json_identifier = identifier.to_dict()
    if not isinstance(json_identifier, Unset):
        params.update(json_identifier)

    json_status: dict[str, Any] | Unset = UNSET
    if not isinstance(status, Unset):
        json_status = status.to_dict()
    if not isinstance(json_status, Unset):
        params.update(json_status)

    json_expires_at: dict[str, Any] | Unset = UNSET
    if not isinstance(expires_at, Unset):
        json_expires_at = expires_at.to_dict()
    if not isinstance(json_expires_at, Unset):
        params.update(json_expires_at)

    json_last_used_at: dict[str, Any] | Unset = UNSET
    if not isinstance(last_used_at, Unset):
        json_last_used_at = last_used_at.to_dict()
    if not isinstance(json_last_used_at, Unset):
        params.update(json_last_used_at)

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
    id: ListServiceAccountCredentialsId | Unset = UNSET,
    created_at: ListServiceAccountCredentialsCreatedAt | Unset = UNSET,
    updated_at: ListServiceAccountCredentialsUpdatedAt | Unset = UNSET,
    created_by: ListServiceAccountCredentialsCreatedBy | Unset = UNSET,
    updated_by: ListServiceAccountCredentialsUpdatedBy | Unset = UNSET,
    credential_type: ListServiceAccountCredentialsCredentialType | Unset = UNSET,
    identifier: ListServiceAccountCredentialsIdentifier | Unset = UNSET,
    status: ListServiceAccountCredentialsStatus | Unset = UNSET,
    expires_at: ListServiceAccountCredentialsExpiresAt | Unset = UNSET,
    last_used_at: ListServiceAccountCredentialsLastUsedAt | Unset = UNSET,
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
        id (ListServiceAccountCredentialsId | Unset):
        created_at (ListServiceAccountCredentialsCreatedAt | Unset):
        updated_at (ListServiceAccountCredentialsUpdatedAt | Unset):
        created_by (ListServiceAccountCredentialsCreatedBy | Unset):
        updated_by (ListServiceAccountCredentialsUpdatedBy | Unset):
        credential_type (ListServiceAccountCredentialsCredentialType | Unset):
        identifier (ListServiceAccountCredentialsIdentifier | Unset):
        status (ListServiceAccountCredentialsStatus | Unset):
        expires_at (ListServiceAccountCredentialsExpiresAt | Unset):
        last_used_at (ListServiceAccountCredentialsLastUsedAt | Unset):

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
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        created_by=created_by,
        updated_by=updated_by,
        credential_type=credential_type,
        identifier=identifier,
        status=status,
        expires_at=expires_at,
        last_used_at=last_used_at,
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
    id: ListServiceAccountCredentialsId | Unset = UNSET,
    created_at: ListServiceAccountCredentialsCreatedAt | Unset = UNSET,
    updated_at: ListServiceAccountCredentialsUpdatedAt | Unset = UNSET,
    created_by: ListServiceAccountCredentialsCreatedBy | Unset = UNSET,
    updated_by: ListServiceAccountCredentialsUpdatedBy | Unset = UNSET,
    credential_type: ListServiceAccountCredentialsCredentialType | Unset = UNSET,
    identifier: ListServiceAccountCredentialsIdentifier | Unset = UNSET,
    status: ListServiceAccountCredentialsStatus | Unset = UNSET,
    expires_at: ListServiceAccountCredentialsExpiresAt | Unset = UNSET,
    last_used_at: ListServiceAccountCredentialsLastUsedAt | Unset = UNSET,
) -> ErrorData | ServiceAccountCredentialListResponse | None:
    """List service account credentials

     List credentials for a service account with pagination.

    Args:
        service_account_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListServiceAccountCredentialsId | Unset):
        created_at (ListServiceAccountCredentialsCreatedAt | Unset):
        updated_at (ListServiceAccountCredentialsUpdatedAt | Unset):
        created_by (ListServiceAccountCredentialsCreatedBy | Unset):
        updated_by (ListServiceAccountCredentialsUpdatedBy | Unset):
        credential_type (ListServiceAccountCredentialsCredentialType | Unset):
        identifier (ListServiceAccountCredentialsIdentifier | Unset):
        status (ListServiceAccountCredentialsStatus | Unset):
        expires_at (ListServiceAccountCredentialsExpiresAt | Unset):
        last_used_at (ListServiceAccountCredentialsLastUsedAt | Unset):

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
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        created_by=created_by,
        updated_by=updated_by,
        credential_type=credential_type,
        identifier=identifier,
        status=status,
        expires_at=expires_at,
        last_used_at=last_used_at,
    ).parsed


async def asyncio_detailed(
    service_account_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListServiceAccountCredentialsId | Unset = UNSET,
    created_at: ListServiceAccountCredentialsCreatedAt | Unset = UNSET,
    updated_at: ListServiceAccountCredentialsUpdatedAt | Unset = UNSET,
    created_by: ListServiceAccountCredentialsCreatedBy | Unset = UNSET,
    updated_by: ListServiceAccountCredentialsUpdatedBy | Unset = UNSET,
    credential_type: ListServiceAccountCredentialsCredentialType | Unset = UNSET,
    identifier: ListServiceAccountCredentialsIdentifier | Unset = UNSET,
    status: ListServiceAccountCredentialsStatus | Unset = UNSET,
    expires_at: ListServiceAccountCredentialsExpiresAt | Unset = UNSET,
    last_used_at: ListServiceAccountCredentialsLastUsedAt | Unset = UNSET,
) -> Response[ErrorData | ServiceAccountCredentialListResponse]:
    """List service account credentials

     List credentials for a service account with pagination.

    Args:
        service_account_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListServiceAccountCredentialsId | Unset):
        created_at (ListServiceAccountCredentialsCreatedAt | Unset):
        updated_at (ListServiceAccountCredentialsUpdatedAt | Unset):
        created_by (ListServiceAccountCredentialsCreatedBy | Unset):
        updated_by (ListServiceAccountCredentialsUpdatedBy | Unset):
        credential_type (ListServiceAccountCredentialsCredentialType | Unset):
        identifier (ListServiceAccountCredentialsIdentifier | Unset):
        status (ListServiceAccountCredentialsStatus | Unset):
        expires_at (ListServiceAccountCredentialsExpiresAt | Unset):
        last_used_at (ListServiceAccountCredentialsLastUsedAt | Unset):

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
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        created_by=created_by,
        updated_by=updated_by,
        credential_type=credential_type,
        identifier=identifier,
        status=status,
        expires_at=expires_at,
        last_used_at=last_used_at,
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
    id: ListServiceAccountCredentialsId | Unset = UNSET,
    created_at: ListServiceAccountCredentialsCreatedAt | Unset = UNSET,
    updated_at: ListServiceAccountCredentialsUpdatedAt | Unset = UNSET,
    created_by: ListServiceAccountCredentialsCreatedBy | Unset = UNSET,
    updated_by: ListServiceAccountCredentialsUpdatedBy | Unset = UNSET,
    credential_type: ListServiceAccountCredentialsCredentialType | Unset = UNSET,
    identifier: ListServiceAccountCredentialsIdentifier | Unset = UNSET,
    status: ListServiceAccountCredentialsStatus | Unset = UNSET,
    expires_at: ListServiceAccountCredentialsExpiresAt | Unset = UNSET,
    last_used_at: ListServiceAccountCredentialsLastUsedAt | Unset = UNSET,
) -> ErrorData | ServiceAccountCredentialListResponse | None:
    """List service account credentials

     List credentials for a service account with pagination.

    Args:
        service_account_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListServiceAccountCredentialsId | Unset):
        created_at (ListServiceAccountCredentialsCreatedAt | Unset):
        updated_at (ListServiceAccountCredentialsUpdatedAt | Unset):
        created_by (ListServiceAccountCredentialsCreatedBy | Unset):
        updated_by (ListServiceAccountCredentialsUpdatedBy | Unset):
        credential_type (ListServiceAccountCredentialsCredentialType | Unset):
        identifier (ListServiceAccountCredentialsIdentifier | Unset):
        status (ListServiceAccountCredentialsStatus | Unset):
        expires_at (ListServiceAccountCredentialsExpiresAt | Unset):
        last_used_at (ListServiceAccountCredentialsLastUsedAt | Unset):

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
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            created_by=created_by,
            updated_by=updated_by,
            credential_type=credential_type,
            identifier=identifier,
            status=status,
            expires_at=expires_at,
            last_used_at=last_used_at,
        )
    ).parsed
