from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.integration_list_response_v2 import IntegrationListResponseV2
from ...models.integration_scope import IntegrationScope
from ...models.integration_status import IntegrationStatus
from ...models.integration_type_v2 import IntegrationTypeV2
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    integration_type: IntegrationTypeV2 | None | Unset = UNSET,
    validation_status: IntegrationStatus | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    scope: IntegrationScope | None | Unset = UNSET,
    management_credential_id: None | Unset | UUID = UNSET,
    project_id: None | Unset | UUID = UNSET,
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

    json_integration_type: None | str | Unset
    if isinstance(integration_type, Unset):
        json_integration_type = UNSET
    elif isinstance(integration_type, IntegrationTypeV2):
        json_integration_type = integration_type.value
    else:
        json_integration_type = integration_type
    params["integration_type"] = json_integration_type

    json_validation_status: None | str | Unset
    if isinstance(validation_status, Unset):
        json_validation_status = UNSET
    elif isinstance(validation_status, IntegrationStatus):
        json_validation_status = validation_status.value
    else:
        json_validation_status = validation_status
    params["validation_status"] = json_validation_status

    json_enabled: bool | None | Unset
    if isinstance(enabled, Unset):
        json_enabled = UNSET
    else:
        json_enabled = enabled
    params["enabled"] = json_enabled

    json_scope: None | str | Unset
    if isinstance(scope, Unset):
        json_scope = UNSET
    elif isinstance(scope, IntegrationScope):
        json_scope = scope.value
    else:
        json_scope = scope
    params["scope"] = json_scope

    json_management_credential_id: None | str | Unset
    if isinstance(management_credential_id, Unset):
        json_management_credential_id = UNSET
    elif isinstance(management_credential_id, UUID):
        json_management_credential_id = str(management_credential_id)
    else:
        json_management_credential_id = management_credential_id
    params["management_credential_id"] = json_management_credential_id

    json_project_id: None | str | Unset
    if isinstance(project_id, Unset):
        json_project_id = UNSET
    elif isinstance(project_id, UUID):
        json_project_id = str(project_id)
    else:
        json_project_id = project_id
    params["project_id"] = json_project_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/integrations",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | IntegrationListResponseV2 | None:
    if response.status_code == 200:
        response_200 = IntegrationListResponseV2.from_dict(response.json())

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
) -> Response[ErrorData | IntegrationListResponseV2]:
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
    integration_type: IntegrationTypeV2 | None | Unset = UNSET,
    validation_status: IntegrationStatus | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    scope: IntegrationScope | None | Unset = UNSET,
    management_credential_id: None | Unset | UUID = UNSET,
    project_id: None | Unset | UUID = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | IntegrationListResponseV2]:
    """List integrations

     List integrations with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        integration_type (IntegrationTypeV2 | None | Unset): Filter by integration type
        validation_status (IntegrationStatus | None | Unset): Filter by validation status
        enabled (bool | None | Unset): Filter by enabled status
        scope (IntegrationScope | None | Unset): Filter by visibility scope
        management_credential_id (None | Unset | UUID): Filter by management credential ID
        project_id (None | Unset | UUID): Filter to integrations that are global or assigned to
            this project. Restricted to projects the user has RBAC access to; querying inaccessible
            projects returns only global integrations.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | IntegrationListResponseV2]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        integration_type=integration_type,
        validation_status=validation_status,
        enabled=enabled,
        scope=scope,
        management_credential_id=management_credential_id,
        project_id=project_id,
        additional_params=additional_params,
    )

    httpx_client = client.get_httpx_client()
    # Path-level servers select v2 while existing clients may use a v1 base URL.
    api_root = httpx_client.base_url.path.rstrip("/").rsplit("/api/", 1)[0].removesuffix("/api")
    kwargs["url"] = httpx_client.base_url.copy_with(path=f"{api_root}{kwargs['url']}")
    response = httpx_client.request(
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
    integration_type: IntegrationTypeV2 | None | Unset = UNSET,
    validation_status: IntegrationStatus | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    scope: IntegrationScope | None | Unset = UNSET,
    management_credential_id: None | Unset | UUID = UNSET,
    project_id: None | Unset | UUID = UNSET,
) -> ErrorData | IntegrationListResponseV2 | None:
    """List integrations

     List integrations with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        integration_type (IntegrationTypeV2 | None | Unset): Filter by integration type
        validation_status (IntegrationStatus | None | Unset): Filter by validation status
        enabled (bool | None | Unset): Filter by enabled status
        scope (IntegrationScope | None | Unset): Filter by visibility scope
        management_credential_id (None | Unset | UUID): Filter by management credential ID
        project_id (None | Unset | UUID): Filter to integrations that are global or assigned to
            this project. Restricted to projects the user has RBAC access to; querying inaccessible
            projects returns only global integrations.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | IntegrationListResponseV2
    """

    return sync_detailed(
        client=client,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        integration_type=integration_type,
        validation_status=validation_status,
        enabled=enabled,
        scope=scope,
        management_credential_id=management_credential_id,
        project_id=project_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    integration_type: IntegrationTypeV2 | None | Unset = UNSET,
    validation_status: IntegrationStatus | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    scope: IntegrationScope | None | Unset = UNSET,
    management_credential_id: None | Unset | UUID = UNSET,
    project_id: None | Unset | UUID = UNSET,
) -> Response[ErrorData | IntegrationListResponseV2]:
    """List integrations

     List integrations with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        integration_type (IntegrationTypeV2 | None | Unset): Filter by integration type
        validation_status (IntegrationStatus | None | Unset): Filter by validation status
        enabled (bool | None | Unset): Filter by enabled status
        scope (IntegrationScope | None | Unset): Filter by visibility scope
        management_credential_id (None | Unset | UUID): Filter by management credential ID
        project_id (None | Unset | UUID): Filter to integrations that are global or assigned to
            this project. Restricted to projects the user has RBAC access to; querying inaccessible
            projects returns only global integrations.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | IntegrationListResponseV2]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        integration_type=integration_type,
        validation_status=validation_status,
        enabled=enabled,
        scope=scope,
        management_credential_id=management_credential_id,
        project_id=project_id,
    )

    httpx_client = client.get_async_httpx_client()
    # Preserve any deployment prefix while selecting the endpoint's API version.
    api_root = httpx_client.base_url.path.rstrip("/").rsplit("/api/", 1)[0].removesuffix("/api")
    kwargs["url"] = httpx_client.base_url.copy_with(path=f"{api_root}{kwargs['url']}")
    response = await httpx_client.request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    integration_type: IntegrationTypeV2 | None | Unset = UNSET,
    validation_status: IntegrationStatus | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    scope: IntegrationScope | None | Unset = UNSET,
    management_credential_id: None | Unset | UUID = UNSET,
    project_id: None | Unset | UUID = UNSET,
) -> ErrorData | IntegrationListResponseV2 | None:
    """List integrations

     List integrations with filtering and pagination.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        integration_type (IntegrationTypeV2 | None | Unset): Filter by integration type
        validation_status (IntegrationStatus | None | Unset): Filter by validation status
        enabled (bool | None | Unset): Filter by enabled status
        scope (IntegrationScope | None | Unset): Filter by visibility scope
        management_credential_id (None | Unset | UUID): Filter by management credential ID
        project_id (None | Unset | UUID): Filter to integrations that are global or assigned to
            this project. Restricted to projects the user has RBAC access to; querying inaccessible
            projects returns only global integrations.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | IntegrationListResponseV2
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
            integration_type=integration_type,
            validation_status=validation_status,
            enabled=enabled,
            scope=scope,
            management_credential_id=management_credential_id,
            project_id=project_id,
        )
    ).parsed
