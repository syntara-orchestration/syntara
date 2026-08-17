"""Tool Service for database operations and business logic.

This module provides the service layer for Tool management, wrapping
core domain logic with database persistence and transaction management.
"""

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import Select
from sqlalchemy.orm import selectinload
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql._expression_select_cls import SelectOfScalar

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.models import User
from syntara.core.services import BaseService
from syntara.core.services.extensions import ConvertResourceMixin, EnrichQueryMixin
from syntara.tool_manager.audit.tool_bulk_update import ToolBulkUpdateEvent
from syntara.tool_manager.audit.tool_update import ToolUpdateEvent
from syntara.tool_manager.exceptions import (
    ToolBulkUpdateValidationError,
    ToolNotFoundError,
)
from syntara.tool_manager.models.tool import (
    Tool,
    ToolListResponse,
    ToolUpdate,
    ToolWithParameters,
)
from syntara.tool_manager.models.tool_bulk_update import MAX_BULK_UPDATES, ToolBulkUpdateResponse

SelectTool = Select[tuple[Tool]] | SelectOfScalar[tuple[Tool]]

logger = structlog.stdlib.get_logger(__name__)


class ToolServiceEnrichQuery(EnrichQueryMixin):
    """Tool-specific query enrichment to eager load tool parameters."""

    def enrich(  # type: ignore[override]
        self, query: Select[tuple[Tool]] | SelectOfScalar[tuple[Tool]]
    ) -> Select[tuple[Tool]] | SelectOfScalar[tuple[Tool]]:
        """Extend the query to eager load tool parameters."""
        return query.options(selectinload(Tool.parameters))  # type: ignore[arg-type]


class ToolServiceConvertResourceMixin(ConvertResourceMixin):
    """Mixin for converting Tool resources to ToolWithParameters format."""

    def convert_resource(self, resource: Tool) -> ToolWithParameters:  # type: ignore[override]
        """Convert Tool to ToolWithParameters format."""
        return ToolWithParameters.model_validate(resource)


class ToolService(BaseService):
    """Service for Tool CRUD operations and business logic.

    This service handles database persistence, transaction management, and provides
    all core tool management functions with proper filtering and pagination.
    """

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize ToolService with database session and user context."""
        super().__init__(
            session,
            user,
            enrich_query_mixin=ToolServiceEnrichQuery(),
            convert_resource_mixin=ToolServiceConvertResourceMixin(),
        )

    async def list_tools(
        self,
        limit: int = 100,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
        visible_integration_ids: list[UUID] | None = None,
    ) -> ToolListResponse:
        """List tools with filtering, sorting, and pagination.

        Args:
            limit: Maximum number of tools to return (max 100)
            cursor: Cursor token for pagination
            sort: Sort parameter (e.g., "name", "-created_at")
            query_params_items: Raw query parameter items from request (for filtering)
            include_total: Whether to include total count in response
            visible_integration_ids: Restrict to tools from these integrations (None = no restriction)

        Returns:
            ToolListResponse with tools, pagination metadata, and optional total

        """
        id_restriction: list[UUID] | None = None
        if visible_integration_ids is not None:
            result = await self.session.exec(
                select(Tool.id).where(col(Tool.integration_id).in_(visible_integration_ids))
            )
            id_restriction = list(result.all())

        return await self.list_resources(
            model=Tool,
            response_type=ToolListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort,
            query_params_items=query_params_items,
            include_total=include_total,
            id_restriction=id_restriction,
        )

    async def _get_tool_for_integration(self, integration_id: UUID, tool_id: UUID) -> Tool:
        """Fetch a tool and verify it belongs to the specified integration."""
        query = select(Tool).options(selectinload(Tool.parameters)).filter(Tool.id == tool_id)  # type: ignore[arg-type]
        result = await self.session.exec(query)
        tool = result.one_or_none()
        if not tool or tool.integration_id != integration_id:
            logger.warning(
                "Tool not found for integration",
                tool_id=str(tool_id),
                integration_id=str(integration_id),
            )
            raise ToolNotFoundError(str(tool_id))
        return tool

    async def get_tool_detail_for_integration(self, integration_id: UUID, tool_id: UUID) -> ToolWithParameters:
        """Get a tool by ID, scoped to an integration (IDOR protection)."""
        tool = await self._get_tool_for_integration(integration_id, tool_id)
        return ToolWithParameters.model_validate(tool)

    async def get_tool_detail(self, tool_id: UUID) -> ToolWithParameters:
        """Get a tool by ID with full details including parameters.

        Args:
            tool_id: UUID of the tool

        Returns:
            Tool instance with full schema and parameters

        Raises:
            ToolNotFoundError: If tool doesn't exist or is deleted

        """
        query = (
            select(Tool).options(selectinload(Tool.parameters)).filter(Tool.id == tool_id)  # type: ignore[arg-type]
        )

        result = await self.session.exec(query)
        tool = result.one_or_none()

        if not tool:
            msg = f"Tool {tool_id} not found"
            raise ToolNotFoundError(msg)

        return ToolWithParameters.model_validate(tool)

    async def update_tool_for_integration(
        self,
        integration_id: UUID,
        tool_id: UUID,
        tool_update: ToolUpdate,
    ) -> ToolWithParameters:
        """Update a tool, scoped to an integration (IDOR protection)."""
        await self._get_tool_for_integration(integration_id, tool_id)
        return await self.update_tool(tool_id, tool_update)

    async def update_tool(
        self,
        tool_id: UUID,
        tool_update: ToolUpdate,
    ) -> ToolWithParameters:
        """Update tool enabled state, status, and refresh error.

        Args:
            tool_id: UUID of the tool to update
            tool_update: Tool update data with optional fields

        Returns:
            Updated Tool instance

        Raises:
            ToolNotFoundError: If tool doesn't exist
            pydantic.ValidationError: If update data is invalid

        """
        query = (
            select(Tool).options(selectinload(Tool.parameters)).filter(Tool.id == tool_id)  # type: ignore[arg-type]
        )

        result = await self.session.exec(query)
        tool = result.one_or_none()

        if not tool:
            msg = f"Tool {tool_id} not found"
            AuditEventDispatcher.dispatch(
                ToolUpdateEvent(
                    tool_id=tool_id,
                    tool_name="<unknown>",
                    namespaced_name="<unknown>",
                    integration_id=None,
                    error_type="ToolNotFoundError",
                )
            )
            raise ToolNotFoundError(msg)

        # Track which fields are being updated
        updated_fields: list[str] = []
        if tool_update.enabled is not None:
            tool.enabled = tool_update.enabled
            updated_fields.append("enabled")

        if tool_update.status is not None:
            tool.status = tool_update.status
            updated_fields.append("status")

        # Handle refresh_error - check if field was explicitly provided (including None)
        if "refresh_error" in tool_update.model_fields_set:
            tool.refresh_error = tool_update.refresh_error
            updated_fields.append("refresh_error")

        tool.updated_by = self.user.id
        tool.updated_at = datetime.now(UTC)

        await self.session.flush()
        await self.session.commit()

        AuditEventDispatcher.dispatch(
            ToolUpdateEvent(
                tool_id=tool.id,
                tool_name=tool.name,
                namespaced_name=tool.namespaced_name,
                integration_id=tool.integration_id,
                updated_fields=updated_fields,
            )
        )

        return await self.get_tool_detail(tool.id)

    async def bulk_update_tools(self, tool_ids: list[UUID], *, enabled: bool) -> ToolBulkUpdateResponse:
        """Batch enable/disable operations with transaction management.

        Args:
            tool_ids: List of tool UUIDs to update (max 50)
            enabled: Enable/disable the tools

        Returns:
            Dict with updated_count, skipped_count, and updated_at

        Raises:
            pydantic.ValidationError: If tool_ids list is invalid

        """
        if not tool_ids:
            msg = "tool_ids cannot be empty"
            AuditEventDispatcher.dispatch(
                ToolBulkUpdateEvent(
                    tool_ids=[],
                    enabled=enabled,
                    error_type="ToolBulkUpdateValidationError",
                )
            )
            raise ToolBulkUpdateValidationError(msg)

        if len(tool_ids) > MAX_BULK_UPDATES:
            msg = f"Cannot update more than {MAX_BULK_UPDATES} tools at once"
            AuditEventDispatcher.dispatch(
                ToolBulkUpdateEvent(
                    tool_ids=tool_ids,
                    enabled=enabled,
                    error_type="ToolBulkUpdateValidationError",
                )
            )
            raise ToolBulkUpdateValidationError(msg)

        # Remove duplicates while preserving order
        unique_tool_ids = list(dict.fromkeys(tool_ids))
        duplicate_count = len(tool_ids) - len(unique_tool_ids)

        if duplicate_count > 0:
            logger.info(
                "Bulk update request contained duplicate tool_ids, removed duplicates",
                duplicate_count=duplicate_count,
                user_id=self.user.id,
                original_count=len(tool_ids),
                unique_count=len(unique_tool_ids),
            )

        query = select(Tool).filter(Tool.id.in_(unique_tool_ids))  # type: ignore[attr-defined]
        result = await self.session.exec(query)
        found_tools = result.all()
        found_tool_ids = {tool.id for tool in found_tools}

        not_found_tool_ids = set(unique_tool_ids) - found_tool_ids

        if not_found_tool_ids:
            logger.warning(
                "Bulk update request included tool_ids that do not exist in database",
                not_found_count=len(not_found_tool_ids),
                user_id=self.user.id,
                not_found_tool_ids=[str(tool_id) for tool_id in not_found_tool_ids],
                enabled=enabled,
            )

        updated_count = 0
        current_time = datetime.now(UTC)

        for tool in found_tools:
            tool.enabled = enabled
            tool.updated_by = self.user.id
            tool.updated_at = current_time
            updated_count += 1

        skipped_count = len(unique_tool_ids) - updated_count

        await self.session.flush()
        await self.session.commit()

        AuditEventDispatcher.dispatch(
            ToolBulkUpdateEvent(
                tool_ids=tool_ids,
                enabled=enabled,
                updated_count=updated_count,
                skipped_count=skipped_count,
                duplicate_count=duplicate_count,
                not_found_count=len(not_found_tool_ids),
            )
        )

        logger.info(
            "Bulk update completed",
            updated_count=updated_count,
            skipped_count=skipped_count,
            user_id=self.user.id,
            enabled=enabled,
            total_requested=len(tool_ids),
            unique_requested=len(unique_tool_ids),
            duplicates=duplicate_count,
            not_found=len(not_found_tool_ids),
        )

        return ToolBulkUpdateResponse(
            updated_count=updated_count,
            skipped_count=skipped_count,
            updated_at=current_time,
        )

    async def bulk_update_tools_for_integration(
        self,
        integration_id: UUID,
        tool_ids: list[UUID],
        *,
        enabled: bool,
    ) -> ToolBulkUpdateResponse:
        """Bulk enable/disable tools, scoped to an integration (IDOR protection).

        Only tools belonging to the specified integration are updated. Tool IDs
        that don't exist or don't belong to this integration are silently skipped
        and counted in ``skipped_count`` (they do not raise). This differs from
        ``bulk_update_tools``, which operates across all tools.

        Args:
            integration_id: UUID of the integration that owns the tools to update
            tool_ids: List of tool UUIDs to update (max 50)
            enabled: Enable/disable the tools

        Returns:
            ToolBulkUpdateResponse with updated_count, skipped_count, and updated_at

        Raises:
            ToolBulkUpdateValidationError: If tool_ids is empty or exceeds the
                maximum bulk update size.

        """
        if not tool_ids:
            msg = "tool_ids cannot be empty"
            raise ToolBulkUpdateValidationError(msg)

        if len(tool_ids) > MAX_BULK_UPDATES:
            msg = f"Cannot update more than {MAX_BULK_UPDATES} tools at once"
            raise ToolBulkUpdateValidationError(msg)

        unique_tool_ids = list(dict.fromkeys(tool_ids))

        query = select(Tool).filter(
            Tool.id.in_(unique_tool_ids),  # type: ignore[attr-defined]
            Tool.integration_id == integration_id,  # type: ignore[arg-type]
        )
        result = await self.session.exec(query)
        found_tools = result.all()

        skipped_count = len(unique_tool_ids) - len(found_tools)
        if skipped_count > 0:
            logger.warning(
                "Bulk update included tool IDs not found in integration",
                integration_id=str(integration_id),
                requested_count=len(unique_tool_ids),
                not_found_count=skipped_count,
                enabled=enabled,
            )

        current_time = datetime.now(UTC)
        updated_count = 0
        for tool in found_tools:
            tool.enabled = enabled
            tool.updated_by = self.user.id
            tool.updated_at = current_time
            updated_count += 1

        await self.session.flush()
        await self.session.commit()

        AuditEventDispatcher.dispatch(
            ToolBulkUpdateEvent(
                tool_ids=tool_ids,
                enabled=enabled,
                updated_count=updated_count,
                skipped_count=skipped_count,
            )
        )

        return ToolBulkUpdateResponse(
            updated_count=updated_count,
            skipped_count=skipped_count,
            updated_at=current_time,
        )
