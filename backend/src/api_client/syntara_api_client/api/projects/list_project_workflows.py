from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.list_project_workflows_created_at import ListProjectWorkflowsCreatedAt
from ...models.list_project_workflows_created_by import ListProjectWorkflowsCreatedBy
from ...models.list_project_workflows_deleted_at import ListProjectWorkflowsDeletedAt
from ...models.list_project_workflows_deleted_by import ListProjectWorkflowsDeletedBy
from ...models.list_project_workflows_description import ListProjectWorkflowsDescription
from ...models.list_project_workflows_has_validation_issues import ListProjectWorkflowsHasValidationIssues
from ...models.list_project_workflows_id import ListProjectWorkflowsId
from ...models.list_project_workflows_is_builtin import ListProjectWorkflowsIsBuiltin
from ...models.list_project_workflows_is_enabled import ListProjectWorkflowsIsEnabled
from ...models.list_project_workflows_name import ListProjectWorkflowsName
from ...models.list_project_workflows_published_version_id import ListProjectWorkflowsPublishedVersionId
from ...models.list_project_workflows_updated_at import ListProjectWorkflowsUpdatedAt
from ...models.list_project_workflows_updated_by import ListProjectWorkflowsUpdatedBy
from ...models.workflow_list_response import WorkflowListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    project_id: UUID,
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListProjectWorkflowsId | Unset = UNSET,
    created_at: ListProjectWorkflowsCreatedAt | Unset = UNSET,
    updated_at: ListProjectWorkflowsUpdatedAt | Unset = UNSET,
    name: ListProjectWorkflowsName | Unset = UNSET,
    description: ListProjectWorkflowsDescription | Unset = UNSET,
    deleted_at: ListProjectWorkflowsDeletedAt | Unset = UNSET,
    deleted_by: ListProjectWorkflowsDeletedBy | Unset = UNSET,
    created_by: ListProjectWorkflowsCreatedBy | Unset = UNSET,
    updated_by: ListProjectWorkflowsUpdatedBy | Unset = UNSET,
    is_builtin: ListProjectWorkflowsIsBuiltin | Unset = UNSET,
    is_enabled: ListProjectWorkflowsIsEnabled | Unset = UNSET,
    has_validation_issues: ListProjectWorkflowsHasValidationIssues | Unset = UNSET,
    published_version_id: ListProjectWorkflowsPublishedVersionId | Unset = UNSET,
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

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/projects/{project_id}/workflows",
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
    project_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListProjectWorkflowsId | Unset = UNSET,
    created_at: ListProjectWorkflowsCreatedAt | Unset = UNSET,
    updated_at: ListProjectWorkflowsUpdatedAt | Unset = UNSET,
    name: ListProjectWorkflowsName | Unset = UNSET,
    description: ListProjectWorkflowsDescription | Unset = UNSET,
    deleted_at: ListProjectWorkflowsDeletedAt | Unset = UNSET,
    deleted_by: ListProjectWorkflowsDeletedBy | Unset = UNSET,
    created_by: ListProjectWorkflowsCreatedBy | Unset = UNSET,
    updated_by: ListProjectWorkflowsUpdatedBy | Unset = UNSET,
    is_builtin: ListProjectWorkflowsIsBuiltin | Unset = UNSET,
    is_enabled: ListProjectWorkflowsIsEnabled | Unset = UNSET,
    has_validation_issues: ListProjectWorkflowsHasValidationIssues | Unset = UNSET,
    published_version_id: ListProjectWorkflowsPublishedVersionId | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | WorkflowListResponse]:
    """List project workflows

     List workflows belonging to a specific project.

    Returns only workflows with project_id matching the given project.
    Requires: workflow:read permission scoped to this project.

    Args:
        project_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListProjectWorkflowsId | Unset):
        created_at (ListProjectWorkflowsCreatedAt | Unset):
        updated_at (ListProjectWorkflowsUpdatedAt | Unset):
        name (ListProjectWorkflowsName | Unset):
        description (ListProjectWorkflowsDescription | Unset):
        deleted_at (ListProjectWorkflowsDeletedAt | Unset):
        deleted_by (ListProjectWorkflowsDeletedBy | Unset):
        created_by (ListProjectWorkflowsCreatedBy | Unset):
        updated_by (ListProjectWorkflowsUpdatedBy | Unset):
        is_builtin (ListProjectWorkflowsIsBuiltin | Unset):
        is_enabled (ListProjectWorkflowsIsEnabled | Unset):
        has_validation_issues (ListProjectWorkflowsHasValidationIssues | Unset):
        published_version_id (ListProjectWorkflowsPublishedVersionId | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | WorkflowListResponse]
    """

    kwargs = _get_kwargs(
        project_id=project_id,
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
    id: ListProjectWorkflowsId | Unset = UNSET,
    created_at: ListProjectWorkflowsCreatedAt | Unset = UNSET,
    updated_at: ListProjectWorkflowsUpdatedAt | Unset = UNSET,
    name: ListProjectWorkflowsName | Unset = UNSET,
    description: ListProjectWorkflowsDescription | Unset = UNSET,
    deleted_at: ListProjectWorkflowsDeletedAt | Unset = UNSET,
    deleted_by: ListProjectWorkflowsDeletedBy | Unset = UNSET,
    created_by: ListProjectWorkflowsCreatedBy | Unset = UNSET,
    updated_by: ListProjectWorkflowsUpdatedBy | Unset = UNSET,
    is_builtin: ListProjectWorkflowsIsBuiltin | Unset = UNSET,
    is_enabled: ListProjectWorkflowsIsEnabled | Unset = UNSET,
    has_validation_issues: ListProjectWorkflowsHasValidationIssues | Unset = UNSET,
    published_version_id: ListProjectWorkflowsPublishedVersionId | Unset = UNSET,
) -> ErrorData | WorkflowListResponse | None:
    """List project workflows

     List workflows belonging to a specific project.

    Returns only workflows with project_id matching the given project.
    Requires: workflow:read permission scoped to this project.

    Args:
        project_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListProjectWorkflowsId | Unset):
        created_at (ListProjectWorkflowsCreatedAt | Unset):
        updated_at (ListProjectWorkflowsUpdatedAt | Unset):
        name (ListProjectWorkflowsName | Unset):
        description (ListProjectWorkflowsDescription | Unset):
        deleted_at (ListProjectWorkflowsDeletedAt | Unset):
        deleted_by (ListProjectWorkflowsDeletedBy | Unset):
        created_by (ListProjectWorkflowsCreatedBy | Unset):
        updated_by (ListProjectWorkflowsUpdatedBy | Unset):
        is_builtin (ListProjectWorkflowsIsBuiltin | Unset):
        is_enabled (ListProjectWorkflowsIsEnabled | Unset):
        has_validation_issues (ListProjectWorkflowsHasValidationIssues | Unset):
        published_version_id (ListProjectWorkflowsPublishedVersionId | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | WorkflowListResponse
    """

    return sync_detailed(
        project_id=project_id,
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
    ).parsed


async def asyncio_detailed(
    project_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListProjectWorkflowsId | Unset = UNSET,
    created_at: ListProjectWorkflowsCreatedAt | Unset = UNSET,
    updated_at: ListProjectWorkflowsUpdatedAt | Unset = UNSET,
    name: ListProjectWorkflowsName | Unset = UNSET,
    description: ListProjectWorkflowsDescription | Unset = UNSET,
    deleted_at: ListProjectWorkflowsDeletedAt | Unset = UNSET,
    deleted_by: ListProjectWorkflowsDeletedBy | Unset = UNSET,
    created_by: ListProjectWorkflowsCreatedBy | Unset = UNSET,
    updated_by: ListProjectWorkflowsUpdatedBy | Unset = UNSET,
    is_builtin: ListProjectWorkflowsIsBuiltin | Unset = UNSET,
    is_enabled: ListProjectWorkflowsIsEnabled | Unset = UNSET,
    has_validation_issues: ListProjectWorkflowsHasValidationIssues | Unset = UNSET,
    published_version_id: ListProjectWorkflowsPublishedVersionId | Unset = UNSET,
) -> Response[ErrorData | WorkflowListResponse]:
    """List project workflows

     List workflows belonging to a specific project.

    Returns only workflows with project_id matching the given project.
    Requires: workflow:read permission scoped to this project.

    Args:
        project_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListProjectWorkflowsId | Unset):
        created_at (ListProjectWorkflowsCreatedAt | Unset):
        updated_at (ListProjectWorkflowsUpdatedAt | Unset):
        name (ListProjectWorkflowsName | Unset):
        description (ListProjectWorkflowsDescription | Unset):
        deleted_at (ListProjectWorkflowsDeletedAt | Unset):
        deleted_by (ListProjectWorkflowsDeletedBy | Unset):
        created_by (ListProjectWorkflowsCreatedBy | Unset):
        updated_by (ListProjectWorkflowsUpdatedBy | Unset):
        is_builtin (ListProjectWorkflowsIsBuiltin | Unset):
        is_enabled (ListProjectWorkflowsIsEnabled | Unset):
        has_validation_issues (ListProjectWorkflowsHasValidationIssues | Unset):
        published_version_id (ListProjectWorkflowsPublishedVersionId | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | WorkflowListResponse]
    """

    kwargs = _get_kwargs(
        project_id=project_id,
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
    id: ListProjectWorkflowsId | Unset = UNSET,
    created_at: ListProjectWorkflowsCreatedAt | Unset = UNSET,
    updated_at: ListProjectWorkflowsUpdatedAt | Unset = UNSET,
    name: ListProjectWorkflowsName | Unset = UNSET,
    description: ListProjectWorkflowsDescription | Unset = UNSET,
    deleted_at: ListProjectWorkflowsDeletedAt | Unset = UNSET,
    deleted_by: ListProjectWorkflowsDeletedBy | Unset = UNSET,
    created_by: ListProjectWorkflowsCreatedBy | Unset = UNSET,
    updated_by: ListProjectWorkflowsUpdatedBy | Unset = UNSET,
    is_builtin: ListProjectWorkflowsIsBuiltin | Unset = UNSET,
    is_enabled: ListProjectWorkflowsIsEnabled | Unset = UNSET,
    has_validation_issues: ListProjectWorkflowsHasValidationIssues | Unset = UNSET,
    published_version_id: ListProjectWorkflowsPublishedVersionId | Unset = UNSET,
) -> ErrorData | WorkflowListResponse | None:
    """List project workflows

     List workflows belonging to a specific project.

    Returns only workflows with project_id matching the given project.
    Requires: workflow:read permission scoped to this project.

    Args:
        project_id (UUID):
        limit (int | Unset): Maximum number of results per page Default: 20.
        cursor (None | str | Unset): Pagination cursor from previous response
        sort (None | str | Unset): Sort parameter (e.g., 'name', '-created_at')
        include_total (bool | Unset): Include total count in response (expensive) Default: False.
        id (ListProjectWorkflowsId | Unset):
        created_at (ListProjectWorkflowsCreatedAt | Unset):
        updated_at (ListProjectWorkflowsUpdatedAt | Unset):
        name (ListProjectWorkflowsName | Unset):
        description (ListProjectWorkflowsDescription | Unset):
        deleted_at (ListProjectWorkflowsDeletedAt | Unset):
        deleted_by (ListProjectWorkflowsDeletedBy | Unset):
        created_by (ListProjectWorkflowsCreatedBy | Unset):
        updated_by (ListProjectWorkflowsUpdatedBy | Unset):
        is_builtin (ListProjectWorkflowsIsBuiltin | Unset):
        is_enabled (ListProjectWorkflowsIsEnabled | Unset):
        has_validation_issues (ListProjectWorkflowsHasValidationIssues | Unset):
        published_version_id (ListProjectWorkflowsPublishedVersionId | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | WorkflowListResponse
    """

    return (
        await asyncio_detailed(
            project_id=project_id,
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
        )
    ).parsed
