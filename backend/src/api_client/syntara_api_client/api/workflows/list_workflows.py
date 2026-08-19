from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.list_workflows_created_at import ListWorkflowsCreatedAt
from ...models.list_workflows_created_by import ListWorkflowsCreatedBy
from ...models.list_workflows_deleted_at import ListWorkflowsDeletedAt
from ...models.list_workflows_deleted_by import ListWorkflowsDeletedBy
from ...models.list_workflows_description import ListWorkflowsDescription
from ...models.list_workflows_has_validation_issues import ListWorkflowsHasValidationIssues
from ...models.list_workflows_id import ListWorkflowsId
from ...models.list_workflows_is_builtin import ListWorkflowsIsBuiltin
from ...models.list_workflows_is_enabled import ListWorkflowsIsEnabled
from ...models.list_workflows_name import ListWorkflowsName
from ...models.list_workflows_project_id import ListWorkflowsProjectId
from ...models.list_workflows_published_version_id import ListWorkflowsPublishedVersionId
from ...models.list_workflows_updated_at import ListWorkflowsUpdatedAt
from ...models.list_workflows_updated_by import ListWorkflowsUpdatedBy
from ...models.workflow_list_response import WorkflowListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListWorkflowsId | Unset = UNSET,
    created_at: ListWorkflowsCreatedAt | Unset = UNSET,
    updated_at: ListWorkflowsUpdatedAt | Unset = UNSET,
    name: ListWorkflowsName | Unset = UNSET,
    description: ListWorkflowsDescription | Unset = UNSET,
    deleted_at: ListWorkflowsDeletedAt | Unset = UNSET,
    deleted_by: ListWorkflowsDeletedBy | Unset = UNSET,
    created_by: ListWorkflowsCreatedBy | Unset = UNSET,
    updated_by: ListWorkflowsUpdatedBy | Unset = UNSET,
    is_builtin: ListWorkflowsIsBuiltin | Unset = UNSET,
    is_enabled: ListWorkflowsIsEnabled | Unset = UNSET,
    has_validation_issues: ListWorkflowsHasValidationIssues | Unset = UNSET,
    published_version_id: ListWorkflowsPublishedVersionId | Unset = UNSET,
    project_id: ListWorkflowsProjectId | Unset = UNSET,
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

    json_deleted_at: dict[str, Any] | Unset = UNSET
    if not isinstance(deleted_at, Unset):
        json_deleted_at = deleted_at.to_dict()
    if not isinstance(json_deleted_at, Unset):
        params.update(json_deleted_at)

    json_deleted_by: dict[str, Any] | Unset = UNSET
    if not isinstance(deleted_by, Unset):
        json_deleted_by = deleted_by.to_dict()
    if not isinstance(json_deleted_by, Unset):
        params.update(json_deleted_by)

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

    json_is_builtin: dict[str, Any] | Unset = UNSET
    if not isinstance(is_builtin, Unset):
        json_is_builtin = is_builtin.to_dict()
    if not isinstance(json_is_builtin, Unset):
        params.update(json_is_builtin)

    json_is_enabled: dict[str, Any] | Unset = UNSET
    if not isinstance(is_enabled, Unset):
        json_is_enabled = is_enabled.to_dict()
    if not isinstance(json_is_enabled, Unset):
        params.update(json_is_enabled)

    json_has_validation_issues: dict[str, Any] | Unset = UNSET
    if not isinstance(has_validation_issues, Unset):
        json_has_validation_issues = has_validation_issues.to_dict()
    if not isinstance(json_has_validation_issues, Unset):
        params.update(json_has_validation_issues)

    json_published_version_id: dict[str, Any] | Unset = UNSET
    if not isinstance(published_version_id, Unset):
        json_published_version_id = published_version_id.to_dict()
    if not isinstance(json_published_version_id, Unset):
        params.update(json_published_version_id)

    json_project_id: dict[str, Any] | Unset = UNSET
    if not isinstance(project_id, Unset):
        json_project_id = project_id.to_dict()
    if not isinstance(json_project_id, Unset):
        params.update(json_project_id)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/workflows",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | WorkflowListResponse | None:
    if response.status_code == 200:
        response_200 = WorkflowListResponse.from_dict(response.json())

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
) -> Response[ErrorData | WorkflowListResponse]:
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
    id: ListWorkflowsId | Unset = UNSET,
    created_at: ListWorkflowsCreatedAt | Unset = UNSET,
    updated_at: ListWorkflowsUpdatedAt | Unset = UNSET,
    name: ListWorkflowsName | Unset = UNSET,
    description: ListWorkflowsDescription | Unset = UNSET,
    deleted_at: ListWorkflowsDeletedAt | Unset = UNSET,
    deleted_by: ListWorkflowsDeletedBy | Unset = UNSET,
    created_by: ListWorkflowsCreatedBy | Unset = UNSET,
    updated_by: ListWorkflowsUpdatedBy | Unset = UNSET,
    is_builtin: ListWorkflowsIsBuiltin | Unset = UNSET,
    is_enabled: ListWorkflowsIsEnabled | Unset = UNSET,
    has_validation_issues: ListWorkflowsHasValidationIssues | Unset = UNSET,
    published_version_id: ListWorkflowsPublishedVersionId | Unset = UNSET,
    project_id: ListWorkflowsProjectId | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | WorkflowListResponse]:
    """List workflows

     List workflows the current user has read access to.

    Supports filtering using query parameters with standard operators:
    - created_by: Filter by creator user ID (created_by=uuid)
    - is_enabled: Filter by enabled status (is_enabled=true|false)
    - labels: Filter by labels using bracket notation (labels[environment]=production)

    Uses cursor-based pagination for scalability and consistency.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListWorkflowsId | Unset):
        created_at (ListWorkflowsCreatedAt | Unset):
        updated_at (ListWorkflowsUpdatedAt | Unset):
        name (ListWorkflowsName | Unset):
        description (ListWorkflowsDescription | Unset):
        deleted_at (ListWorkflowsDeletedAt | Unset):
        deleted_by (ListWorkflowsDeletedBy | Unset):
        created_by (ListWorkflowsCreatedBy | Unset):
        updated_by (ListWorkflowsUpdatedBy | Unset):
        is_builtin (ListWorkflowsIsBuiltin | Unset):
        is_enabled (ListWorkflowsIsEnabled | Unset):
        has_validation_issues (ListWorkflowsHasValidationIssues | Unset):
        published_version_id (ListWorkflowsPublishedVersionId | Unset):
        project_id (ListWorkflowsProjectId | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | WorkflowListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        description=description,
        deleted_at=deleted_at,
        deleted_by=deleted_by,
        created_by=created_by,
        updated_by=updated_by,
        is_builtin=is_builtin,
        is_enabled=is_enabled,
        has_validation_issues=has_validation_issues,
        published_version_id=published_version_id,
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
    id: ListWorkflowsId | Unset = UNSET,
    created_at: ListWorkflowsCreatedAt | Unset = UNSET,
    updated_at: ListWorkflowsUpdatedAt | Unset = UNSET,
    name: ListWorkflowsName | Unset = UNSET,
    description: ListWorkflowsDescription | Unset = UNSET,
    deleted_at: ListWorkflowsDeletedAt | Unset = UNSET,
    deleted_by: ListWorkflowsDeletedBy | Unset = UNSET,
    created_by: ListWorkflowsCreatedBy | Unset = UNSET,
    updated_by: ListWorkflowsUpdatedBy | Unset = UNSET,
    is_builtin: ListWorkflowsIsBuiltin | Unset = UNSET,
    is_enabled: ListWorkflowsIsEnabled | Unset = UNSET,
    has_validation_issues: ListWorkflowsHasValidationIssues | Unset = UNSET,
    published_version_id: ListWorkflowsPublishedVersionId | Unset = UNSET,
    project_id: ListWorkflowsProjectId | Unset = UNSET,
) -> ErrorData | WorkflowListResponse | None:
    """List workflows

     List workflows the current user has read access to.

    Supports filtering using query parameters with standard operators:
    - created_by: Filter by creator user ID (created_by=uuid)
    - is_enabled: Filter by enabled status (is_enabled=true|false)
    - labels: Filter by labels using bracket notation (labels[environment]=production)

    Uses cursor-based pagination for scalability and consistency.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListWorkflowsId | Unset):
        created_at (ListWorkflowsCreatedAt | Unset):
        updated_at (ListWorkflowsUpdatedAt | Unset):
        name (ListWorkflowsName | Unset):
        description (ListWorkflowsDescription | Unset):
        deleted_at (ListWorkflowsDeletedAt | Unset):
        deleted_by (ListWorkflowsDeletedBy | Unset):
        created_by (ListWorkflowsCreatedBy | Unset):
        updated_by (ListWorkflowsUpdatedBy | Unset):
        is_builtin (ListWorkflowsIsBuiltin | Unset):
        is_enabled (ListWorkflowsIsEnabled | Unset):
        has_validation_issues (ListWorkflowsHasValidationIssues | Unset):
        published_version_id (ListWorkflowsPublishedVersionId | Unset):
        project_id (ListWorkflowsProjectId | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | WorkflowListResponse
    """

    return sync_detailed(
        client=client,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        description=description,
        deleted_at=deleted_at,
        deleted_by=deleted_by,
        created_by=created_by,
        updated_by=updated_by,
        is_builtin=is_builtin,
        is_enabled=is_enabled,
        has_validation_issues=has_validation_issues,
        published_version_id=published_version_id,
        project_id=project_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListWorkflowsId | Unset = UNSET,
    created_at: ListWorkflowsCreatedAt | Unset = UNSET,
    updated_at: ListWorkflowsUpdatedAt | Unset = UNSET,
    name: ListWorkflowsName | Unset = UNSET,
    description: ListWorkflowsDescription | Unset = UNSET,
    deleted_at: ListWorkflowsDeletedAt | Unset = UNSET,
    deleted_by: ListWorkflowsDeletedBy | Unset = UNSET,
    created_by: ListWorkflowsCreatedBy | Unset = UNSET,
    updated_by: ListWorkflowsUpdatedBy | Unset = UNSET,
    is_builtin: ListWorkflowsIsBuiltin | Unset = UNSET,
    is_enabled: ListWorkflowsIsEnabled | Unset = UNSET,
    has_validation_issues: ListWorkflowsHasValidationIssues | Unset = UNSET,
    published_version_id: ListWorkflowsPublishedVersionId | Unset = UNSET,
    project_id: ListWorkflowsProjectId | Unset = UNSET,
) -> Response[ErrorData | WorkflowListResponse]:
    """List workflows

     List workflows the current user has read access to.

    Supports filtering using query parameters with standard operators:
    - created_by: Filter by creator user ID (created_by=uuid)
    - is_enabled: Filter by enabled status (is_enabled=true|false)
    - labels: Filter by labels using bracket notation (labels[environment]=production)

    Uses cursor-based pagination for scalability and consistency.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListWorkflowsId | Unset):
        created_at (ListWorkflowsCreatedAt | Unset):
        updated_at (ListWorkflowsUpdatedAt | Unset):
        name (ListWorkflowsName | Unset):
        description (ListWorkflowsDescription | Unset):
        deleted_at (ListWorkflowsDeletedAt | Unset):
        deleted_by (ListWorkflowsDeletedBy | Unset):
        created_by (ListWorkflowsCreatedBy | Unset):
        updated_by (ListWorkflowsUpdatedBy | Unset):
        is_builtin (ListWorkflowsIsBuiltin | Unset):
        is_enabled (ListWorkflowsIsEnabled | Unset):
        has_validation_issues (ListWorkflowsHasValidationIssues | Unset):
        published_version_id (ListWorkflowsPublishedVersionId | Unset):
        project_id (ListWorkflowsProjectId | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | WorkflowListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        name=name,
        description=description,
        deleted_at=deleted_at,
        deleted_by=deleted_by,
        created_by=created_by,
        updated_by=updated_by,
        is_builtin=is_builtin,
        is_enabled=is_enabled,
        has_validation_issues=has_validation_issues,
        published_version_id=published_version_id,
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
    id: ListWorkflowsId | Unset = UNSET,
    created_at: ListWorkflowsCreatedAt | Unset = UNSET,
    updated_at: ListWorkflowsUpdatedAt | Unset = UNSET,
    name: ListWorkflowsName | Unset = UNSET,
    description: ListWorkflowsDescription | Unset = UNSET,
    deleted_at: ListWorkflowsDeletedAt | Unset = UNSET,
    deleted_by: ListWorkflowsDeletedBy | Unset = UNSET,
    created_by: ListWorkflowsCreatedBy | Unset = UNSET,
    updated_by: ListWorkflowsUpdatedBy | Unset = UNSET,
    is_builtin: ListWorkflowsIsBuiltin | Unset = UNSET,
    is_enabled: ListWorkflowsIsEnabled | Unset = UNSET,
    has_validation_issues: ListWorkflowsHasValidationIssues | Unset = UNSET,
    published_version_id: ListWorkflowsPublishedVersionId | Unset = UNSET,
    project_id: ListWorkflowsProjectId | Unset = UNSET,
) -> ErrorData | WorkflowListResponse | None:
    """List workflows

     List workflows the current user has read access to.

    Supports filtering using query parameters with standard operators:
    - created_by: Filter by creator user ID (created_by=uuid)
    - is_enabled: Filter by enabled status (is_enabled=true|false)
    - labels: Filter by labels using bracket notation (labels[environment]=production)

    Uses cursor-based pagination for scalability and consistency.

    Args:
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListWorkflowsId | Unset):
        created_at (ListWorkflowsCreatedAt | Unset):
        updated_at (ListWorkflowsUpdatedAt | Unset):
        name (ListWorkflowsName | Unset):
        description (ListWorkflowsDescription | Unset):
        deleted_at (ListWorkflowsDeletedAt | Unset):
        deleted_by (ListWorkflowsDeletedBy | Unset):
        created_by (ListWorkflowsCreatedBy | Unset):
        updated_by (ListWorkflowsUpdatedBy | Unset):
        is_builtin (ListWorkflowsIsBuiltin | Unset):
        is_enabled (ListWorkflowsIsEnabled | Unset):
        has_validation_issues (ListWorkflowsHasValidationIssues | Unset):
        published_version_id (ListWorkflowsPublishedVersionId | Unset):
        project_id (ListWorkflowsProjectId | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | WorkflowListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            cursor=cursor,
            sort=sort,
            include_total=include_total,
            id=id,
            created_at=created_at,
            updated_at=updated_at,
            name=name,
            description=description,
            deleted_at=deleted_at,
            deleted_by=deleted_by,
            created_by=created_by,
            updated_by=updated_by,
            is_builtin=is_builtin,
            is_enabled=is_enabled,
            has_validation_issues=has_validation_issues,
            published_version_id=published_version_id,
            project_id=project_id,
        )
    ).parsed
