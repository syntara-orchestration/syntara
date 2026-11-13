from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.integration_catalog_list_response import IntegrationCatalogListResponse
from ...models.list_integration_catalog_enabled import ListIntegrationCatalogEnabled
from ...models.list_integration_catalog_integration_type import ListIntegrationCatalogIntegrationType
from ...models.list_integration_catalog_management_credential_id import ListIntegrationCatalogManagementCredentialId
from ...models.list_integration_catalog_scope import ListIntegrationCatalogScope
from ...models.list_integration_catalog_validation_status import ListIntegrationCatalogValidationStatus
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    validation_status: ListIntegrationCatalogValidationStatus | Unset = UNSET,
    enabled: ListIntegrationCatalogEnabled | Unset = UNSET,
    scope: ListIntegrationCatalogScope | Unset = UNSET,
    management_credential_id: ListIntegrationCatalogManagementCredentialId | Unset = UNSET,
    project_id: None | Unset | UUID = UNSET,
    integration_type: ListIntegrationCatalogIntegrationType | Unset = UNSET,
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

    json_validation_status: dict[str, Any] | Unset = UNSET
    if not isinstance(validation_status, Unset):
        json_validation_status = validation_status.to_dict()
    if not isinstance(json_validation_status, Unset):
        params.update({f"validation_status[{operator}]": value for operator, value in json_validation_status.items()})

    json_enabled: dict[str, Any] | Unset = UNSET
    if not isinstance(enabled, Unset):
        json_enabled = enabled.to_dict()
    if not isinstance(json_enabled, Unset):
        params.update({f"enabled[{operator}]": value for operator, value in json_enabled.items()})

    json_scope: dict[str, Any] | Unset = UNSET
    if not isinstance(scope, Unset):
        json_scope = scope.to_dict()
    if not isinstance(json_scope, Unset):
        params.update({f"scope[{operator}]": value for operator, value in json_scope.items()})

    json_management_credential_id: dict[str, Any] | Unset = UNSET
    if not isinstance(management_credential_id, Unset):
        json_management_credential_id = management_credential_id.to_dict()
    if not isinstance(json_management_credential_id, Unset):
        params.update(
            {
                f"management_credential_id[{operator}]": value
                for operator, value in json_management_credential_id.items()
            }
        )

    json_project_id: None | str | Unset
    if isinstance(project_id, Unset):
        json_project_id = UNSET
    elif isinstance(project_id, UUID):
        json_project_id = str(project_id)
    else:
        json_project_id = project_id
    params["project_id"] = json_project_id

    json_integration_type: dict[str, Any] | Unset = UNSET
    if not isinstance(integration_type, Unset):
        json_integration_type = integration_type.to_dict()
    if not isinstance(json_integration_type, Unset):
        params.update({f"integration_type[{operator}]": value for operator, value in json_integration_type.items()})

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/integrations/catalog",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | IntegrationCatalogListResponse | None:
    if response.status_code == 200:
        response_200 = IntegrationCatalogListResponse.from_dict(response.json())

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
) -> Response[ErrorData | IntegrationCatalogListResponse]:
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
    validation_status: ListIntegrationCatalogValidationStatus | Unset = UNSET,
    enabled: ListIntegrationCatalogEnabled | Unset = UNSET,
    scope: ListIntegrationCatalogScope | Unset = UNSET,
    management_credential_id: ListIntegrationCatalogManagementCredentialId | Unset = UNSET,
    project_id: None | Unset | UUID = UNSET,
    integration_type: ListIntegrationCatalogIntegrationType | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | IntegrationCatalogListResponse]:
    """List integration catalog

     List integrations of every supported type with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        validation_status (ListIntegrationCatalogValidationStatus | Unset):
        enabled (ListIntegrationCatalogEnabled | Unset):
        scope (ListIntegrationCatalogScope | Unset):
        management_credential_id (ListIntegrationCatalogManagementCredentialId | Unset):
        project_id (None | Unset | UUID): Filter to integrations that are global or assigned to
            this project. Restricted to projects the user has RBAC access to; querying inaccessible
            projects returns only global integrations.
        integration_type (ListIntegrationCatalogIntegrationType | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | IntegrationCatalogListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        validation_status=validation_status,
        enabled=enabled,
        scope=scope,
        management_credential_id=management_credential_id,
        project_id=project_id,
        integration_type=integration_type,
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
    validation_status: ListIntegrationCatalogValidationStatus | Unset = UNSET,
    enabled: ListIntegrationCatalogEnabled | Unset = UNSET,
    scope: ListIntegrationCatalogScope | Unset = UNSET,
    management_credential_id: ListIntegrationCatalogManagementCredentialId | Unset = UNSET,
    project_id: None | Unset | UUID = UNSET,
    integration_type: ListIntegrationCatalogIntegrationType | Unset = UNSET,
) -> ErrorData | IntegrationCatalogListResponse | None:
    """List integration catalog

     List integrations of every supported type with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        validation_status (ListIntegrationCatalogValidationStatus | Unset):
        enabled (ListIntegrationCatalogEnabled | Unset):
        scope (ListIntegrationCatalogScope | Unset):
        management_credential_id (ListIntegrationCatalogManagementCredentialId | Unset):
        project_id (None | Unset | UUID): Filter to integrations that are global or assigned to
            this project. Restricted to projects the user has RBAC access to; querying inaccessible
            projects returns only global integrations.
        integration_type (ListIntegrationCatalogIntegrationType | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | IntegrationCatalogListResponse
    """

    return sync_detailed(
        client=client,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        validation_status=validation_status,
        enabled=enabled,
        scope=scope,
        management_credential_id=management_credential_id,
        project_id=project_id,
        integration_type=integration_type,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    validation_status: ListIntegrationCatalogValidationStatus | Unset = UNSET,
    enabled: ListIntegrationCatalogEnabled | Unset = UNSET,
    scope: ListIntegrationCatalogScope | Unset = UNSET,
    management_credential_id: ListIntegrationCatalogManagementCredentialId | Unset = UNSET,
    project_id: None | Unset | UUID = UNSET,
    integration_type: ListIntegrationCatalogIntegrationType | Unset = UNSET,
) -> Response[ErrorData | IntegrationCatalogListResponse]:
    """List integration catalog

     List integrations of every supported type with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        validation_status (ListIntegrationCatalogValidationStatus | Unset):
        enabled (ListIntegrationCatalogEnabled | Unset):
        scope (ListIntegrationCatalogScope | Unset):
        management_credential_id (ListIntegrationCatalogManagementCredentialId | Unset):
        project_id (None | Unset | UUID): Filter to integrations that are global or assigned to
            this project. Restricted to projects the user has RBAC access to; querying inaccessible
            projects returns only global integrations.
        integration_type (ListIntegrationCatalogIntegrationType | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | IntegrationCatalogListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        validation_status=validation_status,
        enabled=enabled,
        scope=scope,
        management_credential_id=management_credential_id,
        project_id=project_id,
        integration_type=integration_type,
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
    validation_status: ListIntegrationCatalogValidationStatus | Unset = UNSET,
    enabled: ListIntegrationCatalogEnabled | Unset = UNSET,
    scope: ListIntegrationCatalogScope | Unset = UNSET,
    management_credential_id: ListIntegrationCatalogManagementCredentialId | Unset = UNSET,
    project_id: None | Unset | UUID = UNSET,
    integration_type: ListIntegrationCatalogIntegrationType | Unset = UNSET,
) -> ErrorData | IntegrationCatalogListResponse | None:
    """List integration catalog

     List integrations of every supported type with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        validation_status (ListIntegrationCatalogValidationStatus | Unset):
        enabled (ListIntegrationCatalogEnabled | Unset):
        scope (ListIntegrationCatalogScope | Unset):
        management_credential_id (ListIntegrationCatalogManagementCredentialId | Unset):
        project_id (None | Unset | UUID): Filter to integrations that are global or assigned to
            this project. Restricted to projects the user has RBAC access to; querying inaccessible
            projects returns only global integrations.
        integration_type (ListIntegrationCatalogIntegrationType | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | IntegrationCatalogListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
            validation_status=validation_status,
            enabled=enabled,
            scope=scope,
            management_credential_id=management_credential_id,
            project_id=project_id,
            integration_type=integration_type,
        )
    ).parsed
