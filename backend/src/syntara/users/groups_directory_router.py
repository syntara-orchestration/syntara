"""Lightweight group directory lookup endpoint."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Request
from sqlmodel import Field, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker
from syntara.core.database.session import get_db
from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.group import Group
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.models.user import User
from syntara.core.nexus_router import NexusRouter
from syntara.core.services.base import BaseService

router = NexusRouter(prefix="/groups_directory", tags=["Groups Directory"])

_group_directory_read = PermissionChecker("group-directory", "read")


class GroupDirectoryEntry(SQLModel):
    """Lightweight group record for directory lookups."""

    id: UUID
    name: str


GroupDirectoryListResponse = ResourcesResponse[GroupDirectoryEntry]


class GroupDirectoryListParams(BaseListParams):
    """Query parameters for the group directory listing."""

    name: str | None = Field(default=None, description="Filter by group name")


class _GroupDirectoryService(BaseService):
    """Thin service wrapping BaseService.list_resources for directory queries."""

    async def list_directory(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: list[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
    ) -> GroupDirectoryListResponse:
        return await self.list_resources(
            model=Group,
            response_type=GroupDirectoryListResponse,
            response_type_converter=lambda g: GroupDirectoryEntry(id=g.id, name=g.name),
            limit=limit,
            cursor=cursor,
            sort=sort or "name",
            query_params_items=query_params_items,
            include_total=include_total,
        )


def _get_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> _GroupDirectoryService:
    return _GroupDirectoryService(db, _current_user)


@router.get(
    "",
    summary="List groups directory",
    dependencies=[Depends(_group_directory_read)],
    operation_id="list_groups_directory",
    response_description="Lightweight list of groups",
)
async def list_groups_directory(
    request: Request,
    service: Annotated[_GroupDirectoryService, Depends(_get_service)],
    params: Annotated[GroupDirectoryListParams, Query()],
) -> GroupDirectoryListResponse:
    """Return a lightweight directory of groups (id + name only)."""
    return await service.list_directory(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=list(request.query_params.items()),
        include_total=params.include_total,
    )
