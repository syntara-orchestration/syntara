"""Integration Management API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Request, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

import syntara.integrations.adapters.aap  # register AAP adapter
import syntara.integrations.adapters.llm_provider  # register LLM provider adapter
import syntara.integrations.adapters.mcp_server  # noqa: F401 — register MCP adapter
from syntara.audit.decorators import audit
from syntara.audit.models.audit_event import EventCategory
from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, VisibilityFilter
from syntara.authz.engine import AllowedProjectsResult
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.authz.models.assignments import RoleAssignment
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.models.group import user_groups
from syntara.core.nexus_router import NexusRouter
from syntara.core.services.secret_service import create_secret_service
from syntara.integrations.adapters.protocol import DiscoverResult, ValidateResult
from syntara.integrations.exceptions import IntegrationNotFoundError, IntegrationTypeMismatchError
from syntara.integrations.models import (
    IntegrationCreate,
    IntegrationListParams,
    IntegrationListResponse,
    IntegrationPatch,
    IntegrationProjectAssignmentListParams,
    IntegrationProjectAssignmentListResponse,
    IntegrationProjectAssignmentRead,
    IntegrationRead,
)
from syntara.integrations.models.integration import (
    Integration,
    IntegrationTestConnection,
    IntegrationType,
    RefreshResult,
)
from syntara.integrations.models.llm_model import (
    LLMModelBulkUpdate,
    LLMModelBulkUpdateResponse,
    LLMModelListParams,
    LLMModelListResponse,
    LLMModelRead,
    LLMModelUpdate,
)
from syntara.integrations.services.integration_service import IntegrationService
from syntara.integrations.services.llm_model_service import LLMModelService
from syntara.tool_manager.models import ToolListParams
from syntara.tool_manager.models.tool import (
    ToolListResponse,
    ToolUpdate,
    ToolWithParameters,
)
from syntara.tool_manager.models.tool_bulk_update import ToolBulkUpdate, ToolBulkUpdateResponse
from syntara.tool_manager.services.tool_service import ToolService

router = NexusRouter(tags=["Integrations"])


# ============================================================================
# Permission Checkers
# ============================================================================

_perm_create = PermissionChecker("integration", "create")
_perm_update = PermissionChecker("integration", "update")
_perm_delete = PermissionChecker("integration", "delete")
_perm_discover = PermissionChecker("integration", "discover")
_perm_validate = PermissionChecker("integration", "validate")
_perm_refresh = PermissionChecker("integration", "refresh")
_model_read_gate = VisibilityFilter("llm_model", "read")
_perm_model_update = PermissionChecker("llm_model", "update")
_tool_read_gate = VisibilityFilter("tool", "read")
_perm_tool_update = PermissionChecker("tool", "update")


# ============================================================================
# Dependency Injection
# ============================================================================


def get_integration_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IntegrationService:
    """Dependency provider for IntegrationService."""
    secret_service = create_secret_service(db)
    return IntegrationService(db, current_user, secret_service)


_read_gate = VisibilityFilter("integration", "read")
_read_all_scope = VisibilityFilter("integration", "read-all")


async def _resolve_user_project_ids(db: AsyncSession, user_id: UUID) -> list[UUID]:
    """Return project IDs from the user's project-scoped role assignments (direct + group)."""
    direct_query = select(RoleAssignment.project_id).where(
        RoleAssignment.principal_id == user_id,
        col(RoleAssignment.project_id).is_not(None),
    )

    group_query = (
        select(RoleAssignment.project_id)
        .join(user_groups, user_groups.c.group_id == RoleAssignment.group_id)
        .where(
            user_groups.c.user_id == user_id,
            col(RoleAssignment.project_id).is_not(None),
        )
    )

    result = await db.execute(direct_query.union(group_query))
    return list(result.scalars().all())


async def integration_read_visibility(
    request: Request,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> AllowedProjectsResult:
    """Gate + scope for integration read endpoints.

    Uses integration:read to verify the user has any read access (403 if not).
    Uses integration:read-all to determine scope: if the user has read-all,
    they get unrestricted access. Otherwise, results are scoped to the
    projects from their integration:read policy.
    """
    gate_result = await _read_gate(request, current_user, db)
    if not gate_result.unrestricted and not gate_result.allowed_project_ids:
        msg = "Not authorized to perform read on integration"
        raise AuthorizationDeniedError(msg)

    scope_result = await _read_all_scope(request, current_user, db)
    if scope_result.unrestricted:
        return AllowedProjectsResult(all_projects=True, project_ids=[])

    project_ids = gate_result.allowed_project_ids
    if gate_result.unrestricted and not project_ids:
        project_ids = await _resolve_user_project_ids(db, current_user.id)

    return AllowedProjectsResult(all_projects=False, project_ids=project_ids)


# ============================================================================
# Integration Endpoints
# ============================================================================


@router.post(
    "/integrations",
    summary="Create integration",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_perm_create)],
    operation_id="create_integration",
)
@audit(EventCategory.USER_ACTION, event_action="integration_create")
async def create_integration(
    data: IntegrationCreate,
    service: Annotated[IntegrationService, Depends(get_integration_service)],
) -> IntegrationRead:
    """Create a new integration."""
    return await service.create_integration(data)


@router.get(
    "/integrations",
    summary="List integrations",
    dependencies=[Depends(_read_gate), Depends(_read_all_scope)],
    operation_id="list_integrations",
)
async def list_integrations(
    request: Request,
    service: Annotated[IntegrationService, Depends(get_integration_service)],
    params: Annotated[IntegrationListParams, Query()],
    allowed_projects: Annotated[AllowedProjectsResult, Depends(integration_read_visibility)],
) -> IntegrationListResponse:
    """List integrations with filtering and pagination."""
    return await service.list_integrations(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
        allowed_projects=allowed_projects,
        project_id=params.project_id,
    )


@router.get(
    "/integrations/{integration_id}",
    summary="Get integration",
    dependencies=[Depends(_read_gate), Depends(_read_all_scope)],
    operation_id="get_integration",
)
async def get_integration(
    integration_id: UUID,
    service: Annotated[IntegrationService, Depends(get_integration_service)],
    allowed_projects: Annotated[AllowedProjectsResult, Depends(integration_read_visibility)],
) -> IntegrationRead:
    """Get an integration by ID."""
    return await service.get_integration(integration_id, allowed_projects=allowed_projects)


# No VisibilityFilter on update/delete: these are admin-only permissions,
# and admins have unrestricted project access (all_projects=True).
@router.patch(
    "/integrations/{integration_id}",
    summary="Update integration",
    dependencies=[Depends(_perm_update)],
    operation_id="update_integration",
)
@audit(EventCategory.USER_ACTION, event_action="integration_update", capture_args={"integration_id"})
async def update_integration(
    integration_id: UUID,
    data: IntegrationPatch,
    service: Annotated[IntegrationService, Depends(get_integration_service)],
) -> IntegrationRead:
    """Update an integration."""
    return await service.patch_integration(integration_id, data)


@router.delete(
    "/integrations/{integration_id}",
    summary="Delete integration",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_perm_delete)],
    operation_id="delete_integration",
)
@audit(EventCategory.USER_ACTION, event_action="integration_delete", capture_args={"integration_id"})
async def delete_integration(
    integration_id: UUID,
    service: Annotated[IntegrationService, Depends(get_integration_service)],
) -> None:
    """Delete an integration."""
    await service.delete_integration(integration_id)


@router.post(
    "/integrations/discover",
    summary="Discover integration connection",
    dependencies=[Depends(_perm_discover)],
    operation_id="discover_integration_connection",
)
@audit(EventCategory.USER_ACTION, event_action="integration_discover")
async def discover_integration_connection(
    data: IntegrationTestConnection,
    service: Annotated[IntegrationService, Depends(get_integration_service)],
) -> DiscoverResult:
    """Test a connection and discover resources without saving an integration.

    Accepts integration configuration and a credential ID, resolves the
    credential, runs the adapter's discover() method, and returns the result
    including discovered tools (with parameters) or models. No integration
    is persisted.
    """
    return await service.discover(data)


@router.post(
    "/integrations/{integration_id}/validate",
    summary="Validate integration",
    dependencies=[Depends(_perm_validate)],
    operation_id="validate_integration",
)
@audit(EventCategory.USER_ACTION, event_action="integration_validate", capture_args={"integration_id"})
async def validate_integration(
    integration_id: UUID,
    service: Annotated[IntegrationService, Depends(get_integration_service)],
) -> ValidateResult:
    """Validate a saved integration with a lightweight connectivity ping.

    Resolves the management credential, dispatches to the type-specific
    adapter's validate() method, updates the integration's status fields,
    and returns the result. No tool sync is performed.
    """
    return await service.validate_integration(integration_id)


@router.post(
    "/integrations/{integration_id}/refresh",
    summary="Refresh resources",
    dependencies=[Depends(_perm_refresh)],
    operation_id="refresh_resources",
)
@audit(EventCategory.USER_ACTION, event_action="integration_refresh", capture_args={"integration_id"})
async def refresh_resources(
    integration_id: UUID,
    service: Annotated[IntegrationService, Depends(get_integration_service)],
) -> RefreshResult:
    """Sync resources (tools) for a saved integration from the external service.

    Connects to the MCP server, fetches the current tool list, and upserts
    Tool records in the database. Updates refresh_status and last_refreshed_at
    on the integration. Only supported for mcp_server integration types.
    """
    return await service.refresh_resources(integration_id)


# ============================================================================
# Integration Project Assignment Endpoints
# ============================================================================


@router.post(
    "/integrations/{integration_id}/projects/{project_id}",
    summary="Assign integration project",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_perm_update)],
    operation_id="assign_integration_project",
)
@audit(
    EventCategory.USER_ACTION,
    event_action="integration_project_assign",
    capture_args={"integration_id", "project_id"},
)
async def assign_integration_project(
    integration_id: UUID,
    project_id: UUID,
    service: Annotated[IntegrationService, Depends(get_integration_service)],
) -> IntegrationProjectAssignmentRead:
    """Assign a project to a project-scoped integration."""
    return await service.assign_project(integration_id, project_id)


@router.delete(
    "/integrations/{integration_id}/projects/{project_id}",
    summary="Unassign integration project",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_perm_update)],
    operation_id="unassign_integration_project",
)
@audit(
    EventCategory.USER_ACTION,
    event_action="integration_project_unassign",
    capture_args={"integration_id", "project_id"},
)
async def unassign_integration_project(
    integration_id: UUID,
    project_id: UUID,
    service: Annotated[IntegrationService, Depends(get_integration_service)],
) -> None:
    """Remove a project assignment from an integration."""
    await service.unassign_project(integration_id, project_id)


@router.get(
    "/integrations/{integration_id}/projects",
    summary="List integration projects",
    dependencies=[Depends(_read_gate), Depends(_read_all_scope)],
    operation_id="list_integration_projects",
)
async def list_integration_projects(
    integration_id: UUID,
    service: Annotated[IntegrationService, Depends(get_integration_service)],
    allowed_projects: Annotated[AllowedProjectsResult, Depends(integration_read_visibility)],
    params: Annotated[IntegrationProjectAssignmentListParams, Query()],
) -> IntegrationProjectAssignmentListResponse:
    """List project assignments for an integration."""
    await service.get_integration(integration_id, allowed_projects=allowed_projects)
    return await service.list_assigned_projects(
        integration_id,
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        include_total=params.include_total,
        allowed_projects=allowed_projects,
    )


# ============================================================================
# Integration Model Endpoints
# ============================================================================


def get_llm_model_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> LLMModelService:
    """Dependency provider for LLMModelService."""
    return LLMModelService(db, current_user)


async def _check_integration_visibility(
    db: AsyncSession, integration: Integration, allowed: AllowedProjectsResult
) -> None:
    """Raise IntegrationNotFoundError if the integration is not visible to the caller.

    Delegates to IntegrationService to avoid duplicating visibility query logic.
    """
    visible_ids = await IntegrationService.resolve_visible_integration_ids(db, allowed)
    if visible_ids is not None and integration.id not in set(visible_ids):
        raise IntegrationNotFoundError(integration.id)


async def _require_llm_provider(
    integration_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Verify the integration exists and is an LLM provider (no visibility check)."""
    integration = await db.get(Integration, integration_id)
    if not integration:
        raise IntegrationNotFoundError(integration_id)
    if integration.integration_type != IntegrationType.LLM_PROVIDER:
        raise IntegrationTypeMismatchError(
            integration_id,
            expected_type=IntegrationType.LLM_PROVIDER.value,
            actual_type=integration.integration_type.value,
        )


async def _require_visible_integration_of_type(
    integration_id: UUID,
    request: Request,
    db: AsyncSession,
    current_user: User,
    *,
    gate: VisibilityFilter,
    resource_name: str,
    expected_type: IntegrationType,
) -> None:
    """Verify the integration exists, matches the expected type, user passes the gate, and integration is visible."""
    gate_result = await gate(request, current_user, db)
    if not gate_result.unrestricted and not gate_result.allowed_project_ids:
        msg = f"Not authorized to perform read on {resource_name}"
        raise AuthorizationDeniedError(msg)

    allowed_projects = await integration_read_visibility(request, current_user, db)
    integration = await db.get(Integration, integration_id)
    if not integration:
        raise IntegrationNotFoundError(integration_id)
    if integration.integration_type != expected_type:
        raise IntegrationTypeMismatchError(
            integration_id,
            expected_type=expected_type.value,
            actual_type=integration.integration_type.value,
        )
    await _check_integration_visibility(db, integration, allowed_projects)


async def _require_visible_llm_provider(
    integration_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Verify the integration exists, is an LLM provider, user has llm_model:read, and integration is visible."""
    await _require_visible_integration_of_type(
        integration_id,
        request,
        db,
        current_user,
        gate=_model_read_gate,
        resource_name="llm_model",
        expected_type=IntegrationType.LLM_PROVIDER,
    )


@router.get(
    "/integrations/{integration_id}/models",
    summary="List integration models",
    dependencies=[Depends(_model_read_gate), Depends(_require_visible_llm_provider)],
    operation_id="list_integration_models",
)
async def list_integration_models(
    integration_id: UUID,
    request: Request,
    service: Annotated[LLMModelService, Depends(get_llm_model_service)],
    params: Annotated[LLMModelListParams, Query()],
) -> LLMModelListResponse:
    """List LLM models for an integration with filtering, sorting, and pagination."""
    query_items = [*request.query_params.items(), ("integration_id", str(integration_id))]
    return await service.list_models(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=query_items,
        include_total=params.include_total,
    )


@router.patch(
    "/integrations/{integration_id}/models/bulk_update",
    summary="Bulk update integration models",
    dependencies=[Depends(_perm_model_update), Depends(_require_llm_provider)],
    operation_id="bulk_update_integration_models",
)
@audit(EventCategory.USER_ACTION, event_action="model_bulk_update")
async def bulk_update_integration_models(
    integration_id: UUID,
    data: LLMModelBulkUpdate,
    service: Annotated[LLMModelService, Depends(get_llm_model_service)],
) -> LLMModelBulkUpdateResponse:
    """Bulk enable/disable LLM models."""
    return await service.bulk_update_models(integration_id, data.model_ids, enabled=data.enabled)


@router.get(
    "/integrations/{integration_id}/models/{model_id}",
    summary="Get integration model",
    dependencies=[Depends(_model_read_gate), Depends(_require_visible_llm_provider)],
    operation_id="get_integration_model",
)
async def get_integration_model(
    integration_id: UUID,
    model_id: UUID,
    service: Annotated[LLMModelService, Depends(get_llm_model_service)],
) -> LLMModelRead:
    """Get an LLM model by ID."""
    return await service.get_model_detail(integration_id, model_id)


@router.patch(
    "/integrations/{integration_id}/models/{model_id}",
    summary="Update integration model",
    dependencies=[Depends(_perm_model_update), Depends(_require_llm_provider)],
    operation_id="update_integration_model",
)
@audit(EventCategory.USER_ACTION, event_action="model_update", capture_args={"model_id"})
async def update_integration_model(
    integration_id: UUID,
    model_id: UUID,
    data: LLMModelUpdate,
    service: Annotated[LLMModelService, Depends(get_llm_model_service)],
) -> LLMModelRead:
    """Update an LLM model (enable/disable)."""
    return await service.update_model(integration_id, model_id, data)


# ============================================================================
# Integration Tool Endpoints
# ============================================================================


def get_tool_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ToolService:
    """Dependency provider for ToolService."""
    return ToolService(db, current_user)


async def _require_visible_mcp_server(
    integration_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Verify the integration exists, is an MCP server, user has tool:read, and integration is visible."""
    await _require_visible_integration_of_type(
        integration_id,
        request,
        db,
        current_user,
        gate=_tool_read_gate,
        resource_name="tool",
        expected_type=IntegrationType.MCP_SERVER,
    )


@router.get(
    "/integrations/{integration_id}/tools",
    dependencies=[Depends(_tool_read_gate), Depends(_require_visible_mcp_server)],
    operation_id="list_integration_tools",
)
async def list_integration_tools(
    integration_id: UUID,
    request: Request,
    service: Annotated[ToolService, Depends(get_tool_service)],
    params: Annotated[ToolListParams, Query()],
) -> ToolListResponse:
    """List tools for an integration with filtering, sorting, and pagination."""
    query_items = [*request.query_params.items(), ("integration_id", str(integration_id))]
    return await service.list_tools(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=query_items,
        include_total=params.include_total,
    )


@router.patch(
    "/integrations/{integration_id}/tools/bulk_update",
    dependencies=[Depends(_perm_tool_update), Depends(_require_visible_mcp_server)],
    operation_id="bulk_update_integration_tools",
)
@audit(EventCategory.USER_ACTION, event_action="tool_bulk_update")
async def bulk_update_integration_tools(
    integration_id: UUID,
    data: ToolBulkUpdate,
    service: Annotated[ToolService, Depends(get_tool_service)],
) -> ToolBulkUpdateResponse:
    """Bulk enable/disable tools for an integration."""
    return await service.bulk_update_tools_for_integration(integration_id, data.tool_ids, enabled=data.enabled)


@router.get(
    "/integrations/{integration_id}/tools/{tool_id}",
    dependencies=[Depends(_tool_read_gate), Depends(_require_visible_mcp_server)],
    operation_id="get_integration_tool",
)
async def get_integration_tool(
    integration_id: UUID,
    tool_id: UUID,
    service: Annotated[ToolService, Depends(get_tool_service)],
) -> ToolWithParameters:
    """Get a tool by ID, scoped to an integration."""
    return await service.get_tool_detail_for_integration(integration_id, tool_id)


@router.patch(
    "/integrations/{integration_id}/tools/{tool_id}",
    dependencies=[Depends(_perm_tool_update), Depends(_require_visible_mcp_server)],
    operation_id="update_integration_tool",
)
@audit(EventCategory.USER_ACTION, event_action="tool_update", capture_args={"tool_id"})
async def update_integration_tool(
    integration_id: UUID,
    tool_id: UUID,
    data: ToolUpdate,
    service: Annotated[ToolService, Depends(get_tool_service)],
) -> ToolWithParameters:
    """Update a tool (enable/disable), scoped to an integration."""
    return await service.update_tool_for_integration(integration_id, tool_id, data)
