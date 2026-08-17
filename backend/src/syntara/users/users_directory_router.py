"""Lightweight user directory lookup endpoint."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Request
from sqlmodel import Field, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker
from syntara.core.database.session import get_db
from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.models.user import User
from syntara.core.services.base import BaseService
from syntara.core.syntara_router import SyntaraRouter

router = SyntaraRouter(prefix="/users/directory", tags=["Users Directory"])

_user_directory_read = PermissionChecker("user-directory", "read")


class UserDirectoryEntry(SQLModel):
    """Lightweight user record for directory lookups."""

    id: UUID
    username: str


UserDirectoryListResponse = ResourcesResponse[UserDirectoryEntry]


class UserDirectoryListParams(BaseListParams):
    """Query parameters for the user directory listing."""

    username: str | None = Field(default=None, description="Filter by username")


class _UserDirectoryService(BaseService):
    """Thin service wrapping BaseService.list_resources for directory queries."""

    async def list_directory(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: list[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
    ) -> UserDirectoryListResponse:
        return await self.list_resources(
            model=User,
            response_type=UserDirectoryListResponse,
            response_type_converter=lambda u: UserDirectoryEntry(id=u.id, username=u.username),
            limit=limit,
            cursor=cursor,
            sort=sort or "username",
            query_params_items=query_params_items,
            include_total=include_total,
        )


def _get_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> _UserDirectoryService:
    return _UserDirectoryService(db, _current_user)


@router.get(
    "",
    summary="List users directory",
    dependencies=[Depends(_user_directory_read)],
    operation_id="list_users_directory",
    response_description="Lightweight list of users",
)
async def list_users_directory(
    request: Request,
    service: Annotated[_UserDirectoryService, Depends(_get_service)],
    params: Annotated[UserDirectoryListParams, Query()],
) -> UserDirectoryListResponse:
    """Return a lightweight directory of users (id + username only)."""
    return await service.list_directory(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=list(request.query_params.items()),
        include_total=params.include_total,
    )
