from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.integration_scope import IntegrationScope
from ...models.integration_status import IntegrationStatus
from ...models.kafka_integration_list_response import KafkaIntegrationListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
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
        "url": "/kafka_integrations",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | KafkaIntegrationListResponse | None:
    if response.status_code == 200:
        response_200 = KafkaIntegrationListResponse.from_dict(response.json())

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
) -> Response[ErrorData | KafkaIntegrationListResponse]:
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
    validation_status: IntegrationStatus | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    scope: IntegrationScope | None | Unset = UNSET,
    management_credential_id: None | Unset | UUID = UNSET,
    project_id: None | Unset | UUID = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | KafkaIntegrationListResponse]:
    """List Kafka Integrations

     List Kafka connections with filtering, pagination, and project visibility.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
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
        Response[ErrorData | KafkaIntegrationListResponse]
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
    validation_status: IntegrationStatus | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    scope: IntegrationScope | None | Unset = UNSET,
    management_credential_id: None | Unset | UUID = UNSET,
    project_id: None | Unset | UUID = UNSET,
) -> ErrorData | KafkaIntegrationListResponse | None:
    """List Kafka Integrations

     List Kafka connections with filtering, pagination, and project visibility.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
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
        ErrorData | KafkaIntegrationListResponse
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
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    validation_status: IntegrationStatus | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    scope: IntegrationScope | None | Unset = UNSET,
    management_credential_id: None | Unset | UUID = UNSET,
    project_id: None | Unset | UUID = UNSET,
) -> Response[ErrorData | KafkaIntegrationListResponse]:
    """List Kafka Integrations

     List Kafka connections with filtering, pagination, and project visibility.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
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
        Response[ErrorData | KafkaIntegrationListResponse]
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
    validation_status: IntegrationStatus | None | Unset = UNSET,
    enabled: bool | None | Unset = UNSET,
    scope: IntegrationScope | None | Unset = UNSET,
    management_credential_id: None | Unset | UUID = UNSET,
    project_id: None | Unset | UUID = UNSET,
) -> ErrorData | KafkaIntegrationListResponse | None:
    """List Kafka Integrations

     List Kafka connections with filtering, pagination, and project visibility.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
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
        ErrorData | KafkaIntegrationListResponse
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
        )
    ).parsed
