from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.integration_list_response import IntegrationListResponse
from ...models.list_integrations_created_at import ListIntegrationsCreatedAt
from ...models.list_integrations_created_by import ListIntegrationsCreatedBy
from ...models.list_integrations_description import ListIntegrationsDescription
from ...models.list_integrations_enabled import ListIntegrationsEnabled
from ...models.list_integrations_id import ListIntegrationsId
from ...models.list_integrations_integration_type import ListIntegrationsIntegrationType
from ...models.list_integrations_management_credential_id import ListIntegrationsManagementCredentialId
from ...models.list_integrations_name import ListIntegrationsName
from ...models.list_integrations_scope import ListIntegrationsScope
from ...models.list_integrations_updated_at import ListIntegrationsUpdatedAt
from ...models.list_integrations_updated_by import ListIntegrationsUpdatedBy
from ...models.list_integrations_validation_status import ListIntegrationsValidationStatus
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    project_id: None | Unset | UUID = UNSET,
    id: ListIntegrationsId | Unset = UNSET,
    created_at: ListIntegrationsCreatedAt | Unset = UNSET,
    updated_at: ListIntegrationsUpdatedAt | Unset = UNSET,
    name: ListIntegrationsName | Unset = UNSET,
    description: ListIntegrationsDescription | Unset = UNSET,
    created_by: ListIntegrationsCreatedBy | Unset = UNSET,
    updated_by: ListIntegrationsUpdatedBy | Unset = UNSET,
    integration_type: ListIntegrationsIntegrationType | Unset = UNSET,
    validation_status: ListIntegrationsValidationStatus | Unset = UNSET,
    enabled: ListIntegrationsEnabled | Unset = UNSET,
    scope: ListIntegrationsScope | Unset = UNSET,
    management_credential_id: ListIntegrationsManagementCredentialId | Unset = UNSET,
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

    json_project_id: None | str | Unset
    if isinstance(project_id, Unset):
        json_project_id = UNSET
    elif isinstance(project_id, UUID):
        json_project_id = str(project_id)
    else:
        json_project_id = project_id
    params["project_id"] = json_project_id

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

    json_integration_type: dict[str, Any] | Unset = UNSET
    if not isinstance(integration_type, Unset):
        json_integration_type = integration_type.to_dict()
    if not isinstance(json_integration_type, Unset):
        params.update(json_integration_type)

    json_validation_status: dict[str, Any] | Unset = UNSET
    if not isinstance(validation_status, Unset):
        json_validation_status = validation_status.to_dict()
    if not isinstance(json_validation_status, Unset):
        params.update(json_validation_status)

    json_enabled: dict[str, Any] | Unset = UNSET
    if not isinstance(enabled, Unset):
        json_enabled = enabled.to_dict()
    if not isinstance(json_enabled, Unset):
        params.update(json_enabled)

    json_scope: dict[str, Any] | Unset = UNSET
    if not isinstance(scope, Unset):
        json_scope = scope.to_dict()
    if not isinstance(json_scope, Unset):
        params.update(json_scope)

    json_management_credential_id: dict[str, Any] | Unset = UNSET
    if not isinstance(management_credential_id, Unset):
        json_management_credential_id = management_credential_id.to_dict()
    if not isinstance(json_management_credential_id, Unset):
        params.update(json_management_credential_id)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/integrations",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | IntegrationListResponse | None:
    if response.status_code == 200:
        response_200 = IntegrationListResponse.from_dict(response.json())

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
) -> Response[ErrorData | IntegrationListResponse]:
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
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    project_id: None | Unset | UUID = UNSET,
    id: ListIntegrationsId | Unset = UNSET,
    created_at: ListIntegrationsCreatedAt | Unset = UNSET,
    updated_at: ListIntegrationsUpdatedAt | Unset = UNSET,
    name: ListIntegrationsName | Unset = UNSET,
    description: ListIntegrationsDescription | Unset = UNSET,
    created_by: ListIntegrationsCreatedBy | Unset = UNSET,
    updated_by: ListIntegrationsUpdatedBy | Unset = UNSET,
    integration_type: ListIntegrationsIntegrationType | Unset = UNSET,
    validation_status: ListIntegrationsValidationStatus | Unset = UNSET,
    enabled: ListIntegrationsEnabled | Unset = UNSET,
    scope: ListIntegrationsScope | Unset = UNSET,
    management_credential_id: ListIntegrationsManagementCredentialId | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | IntegrationListResponse]:
    """List integrations

     List integrations with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        project_id (None | Unset | UUID):
        id (ListIntegrationsId | Unset):
        created_at (ListIntegrationsCreatedAt | Unset):
        updated_at (ListIntegrationsUpdatedAt | Unset):
        name (ListIntegrationsName | Unset):
        description (ListIntegrationsDescription | Unset):
        created_by (ListIntegrationsCreatedBy | Unset):
        updated_by (ListIntegrationsUpdatedBy | Unset):
        integration_type (ListIntegrationsIntegrationType | Unset):
        validation_status (ListIntegrationsValidationStatus | Unset):
        enabled (ListIntegrationsEnabled | Unset):
        scope (ListIntegrationsScope | Unset):
        management_credential_id (ListIntegrationsManagementCredentialId | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | IntegrationListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        project_id=project_id,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        description=description,
        created_by=created_by,
        updated_by=updated_by,
        integration_type=integration_type,
        validation_status=validation_status,
        enabled=enabled,
        scope=scope,
        management_credential_id=management_credential_id,
        additional_params=additional_params,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    project_id: None | Unset | UUID = UNSET,
    id: ListIntegrationsId | Unset = UNSET,
    created_at: ListIntegrationsCreatedAt | Unset = UNSET,
    updated_at: ListIntegrationsUpdatedAt | Unset = UNSET,
    name: ListIntegrationsName | Unset = UNSET,
    description: ListIntegrationsDescription | Unset = UNSET,
    created_by: ListIntegrationsCreatedBy | Unset = UNSET,
    updated_by: ListIntegrationsUpdatedBy | Unset = UNSET,
    integration_type: ListIntegrationsIntegrationType | Unset = UNSET,
    validation_status: ListIntegrationsValidationStatus | Unset = UNSET,
    enabled: ListIntegrationsEnabled | Unset = UNSET,
    scope: ListIntegrationsScope | Unset = UNSET,
    management_credential_id: ListIntegrationsManagementCredentialId | Unset = UNSET,
) -> ErrorData | IntegrationListResponse | None:
    """List integrations

     List integrations with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        project_id (None | Unset | UUID):
        id (ListIntegrationsId | Unset):
        created_at (ListIntegrationsCreatedAt | Unset):
        updated_at (ListIntegrationsUpdatedAt | Unset):
        name (ListIntegrationsName | Unset):
        description (ListIntegrationsDescription | Unset):
        created_by (ListIntegrationsCreatedBy | Unset):
        updated_by (ListIntegrationsUpdatedBy | Unset):
        integration_type (ListIntegrationsIntegrationType | Unset):
        validation_status (ListIntegrationsValidationStatus | Unset):
        enabled (ListIntegrationsEnabled | Unset):
        scope (ListIntegrationsScope | Unset):
        management_credential_id (ListIntegrationsManagementCredentialId | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | IntegrationListResponse
    """

    return sync_detailed(
        client=client,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        project_id=project_id,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        description=description,
        created_by=created_by,
        updated_by=updated_by,
        integration_type=integration_type,
        validation_status=validation_status,
        enabled=enabled,
        scope=scope,
        management_credential_id=management_credential_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    project_id: None | Unset | UUID = UNSET,
    id: ListIntegrationsId | Unset = UNSET,
    created_at: ListIntegrationsCreatedAt | Unset = UNSET,
    updated_at: ListIntegrationsUpdatedAt | Unset = UNSET,
    name: ListIntegrationsName | Unset = UNSET,
    description: ListIntegrationsDescription | Unset = UNSET,
    created_by: ListIntegrationsCreatedBy | Unset = UNSET,
    updated_by: ListIntegrationsUpdatedBy | Unset = UNSET,
    integration_type: ListIntegrationsIntegrationType | Unset = UNSET,
    validation_status: ListIntegrationsValidationStatus | Unset = UNSET,
    enabled: ListIntegrationsEnabled | Unset = UNSET,
    scope: ListIntegrationsScope | Unset = UNSET,
    management_credential_id: ListIntegrationsManagementCredentialId | Unset = UNSET,
) -> Response[ErrorData | IntegrationListResponse]:
    """List integrations

     List integrations with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        project_id (None | Unset | UUID):
        id (ListIntegrationsId | Unset):
        created_at (ListIntegrationsCreatedAt | Unset):
        updated_at (ListIntegrationsUpdatedAt | Unset):
        name (ListIntegrationsName | Unset):
        description (ListIntegrationsDescription | Unset):
        created_by (ListIntegrationsCreatedBy | Unset):
        updated_by (ListIntegrationsUpdatedBy | Unset):
        integration_type (ListIntegrationsIntegrationType | Unset):
        validation_status (ListIntegrationsValidationStatus | Unset):
        enabled (ListIntegrationsEnabled | Unset):
        scope (ListIntegrationsScope | Unset):
        management_credential_id (ListIntegrationsManagementCredentialId | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | IntegrationListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        project_id=project_id,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        description=description,
        created_by=created_by,
        updated_by=updated_by,
        integration_type=integration_type,
        validation_status=validation_status,
        enabled=enabled,
        scope=scope,
        management_credential_id=management_credential_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    project_id: None | Unset | UUID = UNSET,
    id: ListIntegrationsId | Unset = UNSET,
    created_at: ListIntegrationsCreatedAt | Unset = UNSET,
    updated_at: ListIntegrationsUpdatedAt | Unset = UNSET,
    name: ListIntegrationsName | Unset = UNSET,
    description: ListIntegrationsDescription | Unset = UNSET,
    created_by: ListIntegrationsCreatedBy | Unset = UNSET,
    updated_by: ListIntegrationsUpdatedBy | Unset = UNSET,
    integration_type: ListIntegrationsIntegrationType | Unset = UNSET,
    validation_status: ListIntegrationsValidationStatus | Unset = UNSET,
    enabled: ListIntegrationsEnabled | Unset = UNSET,
    scope: ListIntegrationsScope | Unset = UNSET,
    management_credential_id: ListIntegrationsManagementCredentialId | Unset = UNSET,
) -> ErrorData | IntegrationListResponse | None:
    """List integrations

     List integrations with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        project_id (None | Unset | UUID):
        id (ListIntegrationsId | Unset):
        created_at (ListIntegrationsCreatedAt | Unset):
        updated_at (ListIntegrationsUpdatedAt | Unset):
        name (ListIntegrationsName | Unset):
        description (ListIntegrationsDescription | Unset):
        created_by (ListIntegrationsCreatedBy | Unset):
        updated_by (ListIntegrationsUpdatedBy | Unset):
        integration_type (ListIntegrationsIntegrationType | Unset):
        validation_status (ListIntegrationsValidationStatus | Unset):
        enabled (ListIntegrationsEnabled | Unset):
        scope (ListIntegrationsScope | Unset):
        management_credential_id (ListIntegrationsManagementCredentialId | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | IntegrationListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
            project_id=project_id,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            name=name,
            description=description,
            created_by=created_by,
            updated_by=updated_by,
            integration_type=integration_type,
            validation_status=validation_status,
            enabled=enabled,
            scope=scope,
            management_credential_id=management_credential_id,
        )
    ).parsed
