from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_data import ErrorData
from ...models.list_workflow_versions_created_at import ListWorkflowVersionsCreatedAt
from ...models.list_workflow_versions_created_by import ListWorkflowVersionsCreatedBy
from ...models.list_workflow_versions_id import ListWorkflowVersionsId
from ...models.list_workflow_versions_updated_at import ListWorkflowVersionsUpdatedAt
from ...models.list_workflow_versions_updated_by import ListWorkflowVersionsUpdatedBy
from ...models.list_workflow_versions_version import ListWorkflowVersionsVersion
from ...models.workflow_version_list_response import WorkflowVersionListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    workflow_id: UUID,
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListWorkflowVersionsId | Unset = UNSET,
    created_at: ListWorkflowVersionsCreatedAt | Unset = UNSET,
    updated_at: ListWorkflowVersionsUpdatedAt | Unset = UNSET,
    created_by: ListWorkflowVersionsCreatedBy | Unset = UNSET,
    updated_by: ListWorkflowVersionsUpdatedBy | Unset = UNSET,
    version: ListWorkflowVersionsVersion | Unset = UNSET,
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

    json_version: dict[str, Any] | Unset = UNSET
    if not isinstance(version, Unset):
        json_version = version.to_dict()
    if not isinstance(json_version, Unset):
        params.update(json_version)

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/workflows/{workflow_id}/versions",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorData | WorkflowVersionListResponse | None:
    if response.status_code == 200:
        response_200 = WorkflowVersionListResponse.from_dict(response.json())

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
) -> Response[ErrorData | WorkflowVersionListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
        request=response.request,
        is_success=response.is_success,
    )


def sync_detailed(
    workflow_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListWorkflowVersionsId | Unset = UNSET,
    created_at: ListWorkflowVersionsCreatedAt | Unset = UNSET,
    updated_at: ListWorkflowVersionsUpdatedAt | Unset = UNSET,
    created_by: ListWorkflowVersionsCreatedBy | Unset = UNSET,
    updated_by: ListWorkflowVersionsUpdatedBy | Unset = UNSET,
    version: ListWorkflowVersionsVersion | Unset = UNSET,
    additional_params: dict[str, Any] | None = None,
) -> Response[ErrorData | WorkflowVersionListResponse]:
    """List workflow versions

     List versions for a workflow with cursor-based pagination.

    Args:
        workflow_id (UUID):
        limit (int | Unset):  Default: 20.
        cursor (None | str | Unset):
        sort (None | str | Unset):
        include_total (bool | Unset):  Default: False.
        id (ListWorkflowVersionsId | Unset):
        created_at (ListWorkflowVersionsCreatedAt | Unset):
        updated_at (ListWorkflowVersionsUpdatedAt | Unset):
        created_by (ListWorkflowVersionsCreatedBy | Unset):
        updated_by (ListWorkflowVersionsUpdatedBy | Unset):
        version (ListWorkflowVersionsVersion | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | WorkflowVersionListResponse]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        created_by=created_by,
        updated_by=updated_by,
        version=version,
        additional_params=additional_params,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    workflow_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListWorkflowVersionsId | Unset = UNSET,
    created_at: ListWorkflowVersionsCreatedAt | Unset = UNSET,
    updated_at: ListWorkflowVersionsUpdatedAt | Unset = UNSET,
    created_by: ListWorkflowVersionsCreatedBy | Unset = UNSET,
    updated_by: ListWorkflowVersionsUpdatedBy | Unset = UNSET,
    version: ListWorkflowVersionsVersion | Unset = UNSET,
) -> ErrorData | WorkflowVersionListResponse | None:
    """List workflow versions

     List versions for a workflow with cursor-based pagination.

    Args:
        workflow_id (UUID):
        limit (int | Unset):  Default: 20.
        cursor (None | str | Unset):
        sort (None | str | Unset):
        include_total (bool | Unset):  Default: False.
        id (ListWorkflowVersionsId | Unset):
        created_at (ListWorkflowVersionsCreatedAt | Unset):
        updated_at (ListWorkflowVersionsUpdatedAt | Unset):
        created_by (ListWorkflowVersionsCreatedBy | Unset):
        updated_by (ListWorkflowVersionsUpdatedBy | Unset):
        version (ListWorkflowVersionsVersion | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | WorkflowVersionListResponse
    """

    return sync_detailed(
        workflow_id=workflow_id,
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
        version=version,
    ).parsed


async def asyncio_detailed(
    workflow_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListWorkflowVersionsId | Unset = UNSET,
    created_at: ListWorkflowVersionsCreatedAt | Unset = UNSET,
    updated_at: ListWorkflowVersionsUpdatedAt | Unset = UNSET,
    created_by: ListWorkflowVersionsCreatedBy | Unset = UNSET,
    updated_by: ListWorkflowVersionsUpdatedBy | Unset = UNSET,
    version: ListWorkflowVersionsVersion | Unset = UNSET,
) -> Response[ErrorData | WorkflowVersionListResponse]:
    """List workflow versions

     List versions for a workflow with cursor-based pagination.

    Args:
        workflow_id (UUID):
        limit (int | Unset):  Default: 20.
        cursor (None | str | Unset):
        sort (None | str | Unset):
        include_total (bool | Unset):  Default: False.
        id (ListWorkflowVersionsId | Unset):
        created_at (ListWorkflowVersionsCreatedAt | Unset):
        updated_at (ListWorkflowVersionsUpdatedAt | Unset):
        created_by (ListWorkflowVersionsCreatedBy | Unset):
        updated_by (ListWorkflowVersionsUpdatedBy | Unset):
        version (ListWorkflowVersionsVersion | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorData | WorkflowVersionListResponse]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        limit=limit,
        cursor=cursor,
        sort=sort,
        include_total=include_total,
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        created_by=created_by,
        updated_by=updated_by,
        version=version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workflow_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    include_total: bool | Unset = False,
    id: ListWorkflowVersionsId | Unset = UNSET,
    created_at: ListWorkflowVersionsCreatedAt | Unset = UNSET,
    updated_at: ListWorkflowVersionsUpdatedAt | Unset = UNSET,
    created_by: ListWorkflowVersionsCreatedBy | Unset = UNSET,
    updated_by: ListWorkflowVersionsUpdatedBy | Unset = UNSET,
    version: ListWorkflowVersionsVersion | Unset = UNSET,
) -> ErrorData | WorkflowVersionListResponse | None:
    """List workflow versions

     List versions for a workflow with cursor-based pagination.

    Args:
        workflow_id (UUID):
        limit (int | Unset):  Default: 20.
        cursor (None | str | Unset):
        sort (None | str | Unset):
        include_total (bool | Unset):  Default: False.
        id (ListWorkflowVersionsId | Unset):
        created_at (ListWorkflowVersionsCreatedAt | Unset):
        updated_at (ListWorkflowVersionsUpdatedAt | Unset):
        created_by (ListWorkflowVersionsCreatedBy | Unset):
        updated_by (ListWorkflowVersionsUpdatedBy | Unset):
        version (ListWorkflowVersionsVersion | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorData | WorkflowVersionListResponse
    """

    return (
        await asyncio_detailed(
            workflow_id=workflow_id,
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
            version=version,
        )
    ).parsed
