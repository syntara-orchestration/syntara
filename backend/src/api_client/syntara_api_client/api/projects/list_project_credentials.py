from http import HTTPStatus
from typing import Any, Literal
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.credential_list_response import CredentialListResponse
from ...models.error_data import ErrorData
from ...models.list_project_credentials_created_at import ListProjectCredentialsCreatedAt
from ...models.list_project_credentials_created_by import ListProjectCredentialsCreatedBy
from ...models.list_project_credentials_credential_type_id import ListProjectCredentialsCredentialTypeId
from ...models.list_project_credentials_description import ListProjectCredentialsDescription
from ...models.list_project_credentials_enabled import ListProjectCredentialsEnabled
from ...models.list_project_credentials_id import ListProjectCredentialsId
from ...models.list_project_credentials_name import ListProjectCredentialsName
from ...models.list_project_credentials_secret_id import ListProjectCredentialsSecretId
from ...models.list_project_credentials_updated_at import ListProjectCredentialsUpdatedAt
from ...models.list_project_credentials_updated_by import ListProjectCredentialsUpdatedBy
from ...types import UNSET, Response, Unset


def _get_kwargs(
    project_id: UUID,
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    for_action: Literal["use"] | None | Unset = UNSET,
    id: ListProjectCredentialsId | Unset = UNSET,
    created_at: ListProjectCredentialsCreatedAt | Unset = UNSET,
    updated_at: ListProjectCredentialsUpdatedAt | Unset = UNSET,
    name: ListProjectCredentialsName | Unset = UNSET,
    description: ListProjectCredentialsDescription | Unset = UNSET,
    created_by: ListProjectCredentialsCreatedBy | Unset = UNSET,
    updated_by: ListProjectCredentialsUpdatedBy | Unset = UNSET,
    credential_type_id: ListProjectCredentialsCredentialTypeId | Unset = UNSET,
    secret_id: ListProjectCredentialsSecretId | Unset = UNSET,
    enabled: ListProjectCredentialsEnabled | Unset = UNSET,
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

    json_for_action: Literal["use"] | None | Unset
    if isinstance(for_action, Unset):
        json_for_action = UNSET
    else:
        json_for_action = for_action
    params["for_action"] = json_for_action

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

    json_name: dict[str, Any] | Unset = UNSET
    if not isinstance(name, Unset):
        json_name = name.to_dict()
    if not isinstance(json_name, Unset):
        params.update(json_name)

    json_description: dict[str, Any] | Unset = UNSET
    if not isinstance(description, Unset):
        json_description = description.to_dict()
    if not isinstance(json_description, Unset):
        params.update(json_description)

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

    json_credential_type_id: dict[str, Any] | Unset = UNSET
    if not isinstance(credential_type_id, Unset):
        json_credential_type_id = credential_type_id.to_dict()
    if not isinstance(json_credential_type_id, Unset):
        params.update(json_credential_type_id)

    json_secret_id: dict[str, Any] | Unset = UNSET
    if not isinstance(secret_id, Unset):
        json_secret_id = secret_id.to_dict()
    if not isinstance(json_secret_id, Unset):
        params.update(json_secret_id)

    json_enabled: dict[str, Any] | Unset = UNSET
    if not isinstance(enabled, Unset):
        json_enabled = enabled.to_dict()
    if not isinstance(json_enabled, Unset):
        params.update(json_enabled)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/projects/{project_id}/credentials",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CredentialListResponse | ErrorData | None:
    if response.status_code == 200:
        response_200 = CredentialListResponse.from_dict(response.json())

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
) -> Response[CredentialListResponse | ErrorData]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    project_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    for_action: Literal["use"] | None | Unset = UNSET,
    id: ListProjectCredentialsId | Unset = UNSET,
    created_at: ListProjectCredentialsCreatedAt | Unset = UNSET,
    updated_at: ListProjectCredentialsUpdatedAt | Unset = UNSET,
    name: ListProjectCredentialsName | Unset = UNSET,
    description: ListProjectCredentialsDescription | Unset = UNSET,
    created_by: ListProjectCredentialsCreatedBy | Unset = UNSET,
    updated_by: ListProjectCredentialsUpdatedBy | Unset = UNSET,
    credential_type_id: ListProjectCredentialsCredentialTypeId | Unset = UNSET,
    secret_id: ListProjectCredentialsSecretId | Unset = UNSET,
    enabled: ListProjectCredentialsEnabled | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[CredentialListResponse | ErrorData]:
    """List project credentials

     List credentials belonging to this project. Requires: credential:read permission.

    The ``for_action`` parameter is accepted for API consistency but not enforced
    here.

    Use ``GET /credentials?for_action=use`` for use-permission-filtered listing.

    Args:
        project_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        for_action (Literal['use'] | None | Unset):
        id (ListProjectCredentialsId | Unset):
        created_at (ListProjectCredentialsCreatedAt | Unset):
        updated_at (ListProjectCredentialsUpdatedAt | Unset):
        name (ListProjectCredentialsName | Unset):
        description (ListProjectCredentialsDescription | Unset):
        created_by (ListProjectCredentialsCreatedBy | Unset):
        updated_by (ListProjectCredentialsUpdatedBy | Unset):
        credential_type_id (ListProjectCredentialsCredentialTypeId | Unset):
        secret_id (ListProjectCredentialsSecretId | Unset):
        enabled (ListProjectCredentialsEnabled | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CredentialListResponse | ErrorData]
    """

    kwargs = _get_kwargs(
        project_id=project_id,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        for_action=for_action,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        description=description,
        created_by=created_by,
        updated_by=updated_by,
        credential_type_id=credential_type_id,
        secret_id=secret_id,
        enabled=enabled,
        additional_params=additional_params,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    project_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    for_action: Literal["use"] | None | Unset = UNSET,
    id: ListProjectCredentialsId | Unset = UNSET,
    created_at: ListProjectCredentialsCreatedAt | Unset = UNSET,
    updated_at: ListProjectCredentialsUpdatedAt | Unset = UNSET,
    name: ListProjectCredentialsName | Unset = UNSET,
    description: ListProjectCredentialsDescription | Unset = UNSET,
    created_by: ListProjectCredentialsCreatedBy | Unset = UNSET,
    updated_by: ListProjectCredentialsUpdatedBy | Unset = UNSET,
    credential_type_id: ListProjectCredentialsCredentialTypeId | Unset = UNSET,
    secret_id: ListProjectCredentialsSecretId | Unset = UNSET,
    enabled: ListProjectCredentialsEnabled | Unset = UNSET,
) -> CredentialListResponse | ErrorData | None:
    """List project credentials

     List credentials belonging to this project. Requires: credential:read permission.

    The ``for_action`` parameter is accepted for API consistency but not enforced
    here.

    Use ``GET /credentials?for_action=use`` for use-permission-filtered listing.

    Args:
        project_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        for_action (Literal['use'] | None | Unset):
        id (ListProjectCredentialsId | Unset):
        created_at (ListProjectCredentialsCreatedAt | Unset):
        updated_at (ListProjectCredentialsUpdatedAt | Unset):
        name (ListProjectCredentialsName | Unset):
        description (ListProjectCredentialsDescription | Unset):
        created_by (ListProjectCredentialsCreatedBy | Unset):
        updated_by (ListProjectCredentialsUpdatedBy | Unset):
        credential_type_id (ListProjectCredentialsCredentialTypeId | Unset):
        secret_id (ListProjectCredentialsSecretId | Unset):
        enabled (ListProjectCredentialsEnabled | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CredentialListResponse | ErrorData
    """

    return sync_detailed(
        project_id=project_id,
        client=client,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        for_action=for_action,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        description=description,
        created_by=created_by,
        updated_by=updated_by,
        credential_type_id=credential_type_id,
        secret_id=secret_id,
        enabled=enabled,
    ).parsed


async def asyncio_detailed(
    project_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    for_action: Literal["use"] | None | Unset = UNSET,
    id: ListProjectCredentialsId | Unset = UNSET,
    created_at: ListProjectCredentialsCreatedAt | Unset = UNSET,
    updated_at: ListProjectCredentialsUpdatedAt | Unset = UNSET,
    name: ListProjectCredentialsName | Unset = UNSET,
    description: ListProjectCredentialsDescription | Unset = UNSET,
    created_by: ListProjectCredentialsCreatedBy | Unset = UNSET,
    updated_by: ListProjectCredentialsUpdatedBy | Unset = UNSET,
    credential_type_id: ListProjectCredentialsCredentialTypeId | Unset = UNSET,
    secret_id: ListProjectCredentialsSecretId | Unset = UNSET,
    enabled: ListProjectCredentialsEnabled | Unset = UNSET,
) -> Response[CredentialListResponse | ErrorData]:
    """List project credentials

     List credentials belonging to this project. Requires: credential:read permission.

    The ``for_action`` parameter is accepted for API consistency but not enforced
    here.

    Use ``GET /credentials?for_action=use`` for use-permission-filtered listing.

    Args:
        project_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        for_action (Literal['use'] | None | Unset):
        id (ListProjectCredentialsId | Unset):
        created_at (ListProjectCredentialsCreatedAt | Unset):
        updated_at (ListProjectCredentialsUpdatedAt | Unset):
        name (ListProjectCredentialsName | Unset):
        description (ListProjectCredentialsDescription | Unset):
        created_by (ListProjectCredentialsCreatedBy | Unset):
        updated_by (ListProjectCredentialsUpdatedBy | Unset):
        credential_type_id (ListProjectCredentialsCredentialTypeId | Unset):
        secret_id (ListProjectCredentialsSecretId | Unset):
        enabled (ListProjectCredentialsEnabled | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CredentialListResponse | ErrorData]
    """

    kwargs = _get_kwargs(
        project_id=project_id,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        for_action=for_action,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        description=description,
        created_by=created_by,
        updated_by=updated_by,
        credential_type_id=credential_type_id,
        secret_id=secret_id,
        enabled=enabled,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    project_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    for_action: Literal["use"] | None | Unset = UNSET,
    id: ListProjectCredentialsId | Unset = UNSET,
    created_at: ListProjectCredentialsCreatedAt | Unset = UNSET,
    updated_at: ListProjectCredentialsUpdatedAt | Unset = UNSET,
    name: ListProjectCredentialsName | Unset = UNSET,
    description: ListProjectCredentialsDescription | Unset = UNSET,
    created_by: ListProjectCredentialsCreatedBy | Unset = UNSET,
    updated_by: ListProjectCredentialsUpdatedBy | Unset = UNSET,
    credential_type_id: ListProjectCredentialsCredentialTypeId | Unset = UNSET,
    secret_id: ListProjectCredentialsSecretId | Unset = UNSET,
    enabled: ListProjectCredentialsEnabled | Unset = UNSET,
) -> CredentialListResponse | ErrorData | None:
    """List project credentials

     List credentials belonging to this project. Requires: credential:read permission.

    The ``for_action`` parameter is accepted for API consistency but not enforced
    here.

    Use ``GET /credentials?for_action=use`` for use-permission-filtered listing.

    Args:
        project_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        for_action (Literal['use'] | None | Unset):
        id (ListProjectCredentialsId | Unset):
        created_at (ListProjectCredentialsCreatedAt | Unset):
        updated_at (ListProjectCredentialsUpdatedAt | Unset):
        name (ListProjectCredentialsName | Unset):
        description (ListProjectCredentialsDescription | Unset):
        created_by (ListProjectCredentialsCreatedBy | Unset):
        updated_by (ListProjectCredentialsUpdatedBy | Unset):
        credential_type_id (ListProjectCredentialsCredentialTypeId | Unset):
        secret_id (ListProjectCredentialsSecretId | Unset):
        enabled (ListProjectCredentialsEnabled | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CredentialListResponse | ErrorData
    """

    return (
        await asyncio_detailed(
            project_id=project_id,
            client=client,
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
            for_action=for_action,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            name=name,
            description=description,
            created_by=created_by,
            updated_by=updated_by,
            credential_type_id=credential_type_id,
            secret_id=secret_id,
            enabled=enabled,
        )
    ).parsed
