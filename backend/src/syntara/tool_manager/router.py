"""Top-level tool endpoints.

Provides cross-integration tool listing at GET /tools and
unscoped tool update at PATCH /tools/{tool_id} (used by the
agent orchestrator for operational status reporting).
Integration-scoped tool CRUD lives in syntara.integrations.router.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.decorators import audit
from syntara.audit.models.audit_event import EventCategory
from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, VisibilityFilter
from syntara.authz.engine import AllowedProjectsResult
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.nexus_router import NexusRouter
from syntara.integrations.router import integration_read_visibility
from syntara.integrations.services.integration_service import IntegrationService
from syntara.tool_manager.exceptions import ToolNotFoundError
from syntara.tool_manager.models import ToolListParams
from syntara.tool_manager.models.tool import (
    ToolListResponse,
    ToolUpdate,
    ToolWithParameters,
)
from syntara.tool_manager.services.tool_service import ToolService

router = NexusRouter(tags=["Tools"])

_tool_read_gate = VisibilityFilter("tool", "read")
_perm_tool_update = PermissionChecker("tool", "update")


async def _tool_read_visibility(
    request: Request,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> AllowedProjectsResult:
    """Gate + scope for tool read endpoints.

    Checks tool:read for access (403 if denied), then uses
    integration_read_visibility to scope results by parent integration.
    """
    gate_result = await _tool_read_gate(request, current_user, db)
    if not gate_result.unrestricted and not gate_result.allowed_project_ids:
        msg = "Not authorized to perform read on tool"
        raise AuthorizationDeniedError(msg)

    return await integration_read_visibility(request, current_user, db)


def _get_tool_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ToolService:
    """Dependency provider for ToolService."""
    return ToolService(db, current_user)


@router.get("/tools", dependencies=[Depends(_tool_read_gate)], operation_id="list_tools")
async def list_tools(
    request: Request,
    service: Annotated[ToolService, Depends(_get_tool_service)],
    params: Annotated[ToolListParams, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
    allowed_projects: Annotated[AllowedProjectsResult, Depends(_tool_read_visibility)],
) -> ToolListResponse:
    """List tools with filtering, sorting, and pagination.

    Tools are filtered by the caller's integration visibility — only tools
    belonging to visible integrations are returned.
    """
    visible_ids: list[UUID] | None = await IntegrationService.resolve_visible_integration_ids(db, allowed_projects)
    return await service.list_tools(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
        visible_integration_ids=visible_ids,
    )


@router.get("/tools/{tool_id}", dependencies=[Depends(_tool_read_gate)], operation_id="get_tool")
async def get_tool(
    tool_id: UUID,
    service: Annotated[ToolService, Depends(_get_tool_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    allowed_projects: Annotated[AllowedProjectsResult, Depends(_tool_read_visibility)],
) -> ToolWithParameters:
    """Get tool details by ID."""
    tool = await service.get_tool_detail(tool_id)
    visible_ids = await IntegrationService.resolve_visible_integration_ids(db, allowed_projects)
    if visible_ids is not None and tool.integration_id not in set(visible_ids):
        raise ToolNotFoundError(str(tool_id))
    return tool


@router.patch("/tools/{tool_id}", dependencies=[Depends(_perm_tool_update)], operation_id="update_tool")
@audit(EventCategory.USER_ACTION, event_action="tool_update", capture_args={"tool_id"})
async def update_tool(
    tool_id: UUID,
    tool_update: ToolUpdate,
    service: Annotated[ToolService, Depends(_get_tool_service)],
) -> ToolWithParameters:
    """Update tool status (enable/disable)."""
    return await service.update_tool(tool_id, tool_update)
