"""Users CRUD API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.decorators import audit
from syntara.audit.models.audit_event import EventCategory
from syntara.auth import get_current_user
from syntara.auth.session import create_session_store
from syntara.authz.dependencies import PermissionChecker, VisibilityFilter
from syntara.authz.engine import VisibilityResult
from syntara.authz.models.assignments import RoleAssignment
from syntara.authz.role_assignment_router import (
    PrincipalRoleAssignmentListParams,
    RoleAssignmentListResponse,
    RoleAssignmentRead,
    SubResourceRoleAssignmentCreate,
    delete_sub_resource_assignment,
    list_sub_resource_assignments,
)
from syntara.authz.services.role_assignment_service import RoleAssignmentService
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.group import UserGroupListResponse, UserGroupsSet
from syntara.core.models.user_identity_schemas import UserIdentityAttach, UserIdentityListResponse, UserIdentityRead
from syntara.core.models.user_schemas import (
    UserCreate,
    UserListParams,
    UserListResponse,
    UserRead,
    UserUpdate,
)
from syntara.core.syntara_router import NO_PERMISSION, SyntaraRouter
from syntara.users.services.group_service import GroupsService
from syntara.users.services.user_identity_service import UserIdentityService
from syntara.users.services.user_service import UNSET, UsersService

router = SyntaraRouter(prefix="/users", tags=["Users"])

_user_create = PermissionChecker("user", "create")
_user_read = PermissionChecker("user", "read", resource_id_param="user_id")
_user_update = PermissionChecker("user", "update", resource_id_param="user_id")
_user_delete = PermissionChecker("user", "delete")
_group_member_manage = PermissionChecker("group", "manage-members")
_identity_read = PermissionChecker("user_identity", "read", resource_id_param="user_id")
_identity_attach = PermissionChecker("user_identity", "attach")
_identity_detach = PermissionChecker("user_identity", "detach", resource_id_param="user_id")


# ============================================================================
# Dependency Injection Providers
# ============================================================================


def get_user_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UsersService:
    """Dependency provider for UsersService."""
    return UsersService(db, current_user)


def get_identity_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> UserIdentityService:
    """Dependency provider for UserIdentityService."""
    return UserIdentityService(db)


def get_group_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GroupsService:
    """Dependency provider for GroupsService (used for user-groups listing)."""
    return GroupsService(db, current_user)


def _get_role_assignment_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RoleAssignmentService:
    return RoleAssignmentService(db, current_user)


# ============================================================================
# User endpoints
# ============================================================================


@router.post(
    "",
    summary="Create user",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_user_create)],
    operation_id="create_user",
    response_description="User created",
)
@audit(EventCategory.USER_ACTION, event_action="user_create")
async def create_user(
    request: UserCreate,
    service: Annotated[UsersService, Depends(get_user_service)],
) -> UserRead:
    """Create a new local user."""
    user = await service.create_user(
        username=request.username,
        first_name=request.first_name,
        password=request.password.get_secret_value(),
        last_name=request.last_name,
        email=request.email,
        is_enabled=request.is_enabled,
        group_names=request.group_names,
    )
    return await service.to_read(user)


@router.get(
    "",
    summary="List users",
    dependencies=[NO_PERMISSION],
    operation_id="list_users",
    response_description="List of users",
)
async def list_users(
    request: Request,
    service: Annotated[UsersService, Depends(get_user_service)],
    params: Annotated[UserListParams, Query()],
    visibility: Annotated[VisibilityResult, Depends(VisibilityFilter("user", "read"))],
) -> UserListResponse:
    """List users with visibility filtering and pagination.

    Users with ``user:read:any`` see all users.
    Users with ``user:read:self`` see only themselves.
    """
    return await service.list_users_cursor(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
        id_restriction=visibility.to_id_restriction(),
    )


@router.get(
    "/me",
    summary="Get current user profile",
    dependencies=[NO_PERMISSION],
    operation_id="get_current_user_profile",
    response_description="Current user profile",
)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UsersService, Depends(get_user_service)],
) -> UserRead:
    """Return information about the currently authenticated user."""
    user = await service.get_user_by_id(current_user.id)
    return await service.to_read(user)


@router.get(
    "/{user_id}",
    summary="Get user",
    dependencies=[Depends(_user_read)],
    operation_id="get_user",
    response_description="User details",
)
async def get_user(
    user_id: UUID,
    service: Annotated[UsersService, Depends(get_user_service)],
) -> UserRead:
    """Get a user by ID."""
    user = await service.get_user_by_id(user_id)
    return await service.to_read(user)


@router.patch(
    "/{user_id}",
    summary="Update user",
    dependencies=[Depends(_user_update)],
    operation_id="update_user",
    response_description="Updated user",
)
@audit(EventCategory.USER_ACTION, event_action="user_update", capture_args={"user_id"})
async def update_user(
    user_id: UUID,
    request: UserUpdate,
    service: Annotated[UsersService, Depends(get_user_service)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserRead:
    """Update a user.

    Supports partial updates - only provided fields are updated.
    """
    password = request.password.get_secret_value() if request.password else None

    last_name = request.last_name if "last_name" in request.model_fields_set else UNSET
    user = await service.update_user(
        user_id,
        username=request.username,
        first_name=request.first_name,
        last_name=last_name,
        email=request.email,
        password=password,
        is_enabled=request.is_enabled,
    )

    if password is not None:
        from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
        from syntara.auth.audit.user_account_change import UserPasswordChangedEvent  # noqa: PLC0415

        AuditEventDispatcher.dispatch(
            UserPasswordChangedEvent(
                actor_id=current_user.id,
                actor_username=current_user.username,
                target_user_id=user_id,
                target_username=user.username,
            )
        )

    if request.is_enabled is not None:
        from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
        from syntara.auth.audit.user_account_change import AccountStatus, UserAccountStatusChangedEvent  # noqa: PLC0415

        AuditEventDispatcher.dispatch(
            UserAccountStatusChangedEvent(
                actor_id=current_user.id,
                actor_username=current_user.username,
                target_user_id=user_id,
                target_username=user.username,
                new_status=AccountStatus.ENABLED if request.is_enabled else AccountStatus.DISABLED,
            )
        )

    # When a user's password is changed or their account is deactivated,
    # revoke all their existing refresh token sessions.  This is a hard
    # requirement — if the session store is unavailable, the request fails
    # so that compromised sessions cannot persist.
    # Note: StaleTokenMiddleware also rejects requests from disabled users
    # within ~5 seconds (TTL-cached DB check), closing the stateless JWT window.
    store = create_session_store(db)
    if password is not None or request.is_enabled is False:
        await store.revoke_all_for_user(user_id)

    # Signal that the user's token claims are stale so the frontend
    # triggers a background refresh on the next API response.
    await store.increment_token_version(user_id)
    await db.commit()

    return await service.to_read(user)


@router.delete(
    "/{user_id}",
    summary="Delete user",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_user_delete)],
    operation_id="delete_user",
    response_description="User deleted",
)
@audit(EventCategory.USER_ACTION, event_action="user_delete", capture_args={"user_id"})
async def delete_user(
    user_id: UUID,
    service: Annotated[UsersService, Depends(get_user_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Soft delete a user."""
    await service.delete_user(user_id)
    store = create_session_store(db)
    await store.revoke_all_for_user(user_id)

    # Signal stale token so the deleted user's next request triggers a
    # refresh attempt, which will fail with 401 (user not found).
    await store.increment_token_version(user_id)
    await db.commit()


@router.get(
    "/{user_id}/groups",
    summary="List user groups",
    dependencies=[Depends(_user_read)],
    operation_id="list_user_groups",
    response_description="List of groups the user belongs to",
)
async def list_user_groups(
    user_id: UUID,
    service: Annotated[GroupsService, Depends(get_group_service)],
    params: Annotated[BaseListParams, Query()],
) -> UserGroupListResponse:
    """List groups that a user belongs to."""
    return await service.list_user_groups(
        user_id,
        limit=params.limit,
        cursor=params.cursor,
    )


@router.put(
    "/{user_id}/groups",
    summary="Set user groups",
    dependencies=[Depends(_group_member_manage)],
    operation_id="set_user_groups",
    response_description="Updated group memberships",
)
@audit(EventCategory.SECURITY_EVENT, event_action="user_groups_set", capture_args={"user_id", "request"})
async def set_user_groups(
    user_id: UUID,
    request: UserGroupsSet,
    service: Annotated[GroupsService, Depends(get_group_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserGroupListResponse:
    """Set a user's group memberships declaratively.

    Replace all current memberships with the provided list of group IDs.
    An empty list removes the user from all groups.
    """
    result = await service.set_user_groups(user_id, request.group_ids)
    store = create_session_store(db)
    await store.increment_token_version(user_id)
    return result


# ============================================================================
# User Role Assignments
# ============================================================================


@router.post(
    "/{user_id}/role_assignments",
    summary="Create user role assignment",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionChecker("role-assignment", "assign", body_project_field="project_id"))],
    operation_id="create_user_role_assignment",
    response_description="Role assignment created",
)
@audit(EventCategory.SECURITY_EVENT, event_action="user_role_assign", capture_args={"user_id"})
async def create_user_role_assignment(
    user_id: UUID,
    body: SubResourceRoleAssignmentCreate,
    service: Annotated[RoleAssignmentService, Depends(_get_role_assignment_service)],
) -> RoleAssignmentRead:
    """Assign a role to this user."""
    result = await service.assign(
        principal_id=user_id,
        role_name=body.role_name,
        project_id=body.project_id,
    )
    return RoleAssignmentRead.model_validate(result)


@router.get(
    "/{user_id}/role_assignments",
    summary="List user role assignments",
    dependencies=[NO_PERMISSION],
    operation_id="list_user_role_assignments",
    response_description="List of role assignments for this user",
)
async def list_user_role_assignments(
    user_id: UUID,
    request: Request,
    params: Annotated[PrincipalRoleAssignmentListParams, Depends()],
    service: Annotated[RoleAssignmentService, Depends(_get_role_assignment_service)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RoleAssignmentListResponse:
    """List role assignments for a specific user."""
    return await list_sub_resource_assignments(
        principal_id=user_id,
        request=request,
        params=params,
        service=service,
        current_user=current_user,
        db=db,
    )


@router.delete(
    "/{user_id}/role_assignments/{assignment_id}",
    summary="Delete user role assignment",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(
            PermissionChecker(
                "role-assignment",
                "revoke",
                resource_model=RoleAssignment,
                resource_id_param="assignment_id",
            )
        )
    ],
    operation_id="delete_user_role_assignment",
    response_description="Assignment removed",
)
@audit(EventCategory.SECURITY_EVENT, event_action="user_role_revoke", capture_args={"user_id", "assignment_id"})
async def delete_user_role_assignment(
    user_id: UUID,
    assignment_id: UUID,
    service: Annotated[RoleAssignmentService, Depends(_get_role_assignment_service)],
) -> None:
    """Remove a role assignment from this user."""
    await delete_sub_resource_assignment(
        principal_id=user_id,
        assignment_id=assignment_id,
        service=service,
    )


# ============================================================================
# User Identity endpoints
# ============================================================================


@router.get(
    "/{user_id}/identities",
    summary="List user identities",
    dependencies=[Depends(_identity_read)],
    operation_id="list_user_identities",
)
async def list_user_identities(
    user_id: UUID,
    service: Annotated[UserIdentityService, Depends(get_identity_service)],
) -> UserIdentityListResponse:
    """List federated identities for a user."""
    return await service.list_for_user(user_id)


@router.post(
    "/{user_id}/identities",
    summary="Attach user identity",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_identity_attach)],
    operation_id="attach_user_identity",
)
@audit(EventCategory.USER_ACTION, event_action="identity_attach", capture_args={"user_id"})
async def attach_user_identity(
    user_id: UUID,
    request: UserIdentityAttach,
    service: Annotated[UserIdentityService, Depends(get_identity_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserIdentityRead:
    """Attach a federated identity from another user to this user."""
    result = await service.attach_identity(request.identity_id, user_id)
    await db.commit()
    return result


@router.delete(
    "/{user_id}/identities/{identity_id}",
    summary="Detach user identity",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_identity_detach)],
    operation_id="detach_user_identity",
)
@audit(EventCategory.USER_ACTION, event_action="identity_detach", capture_args={"user_id", "identity_id"})
async def detach_user_identity(
    user_id: UUID,
    identity_id: UUID,
    service: Annotated[UserIdentityService, Depends(get_identity_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Detach (hard-delete) a federated identity from a user."""
    await service.delete_identity(identity_id, expected_user_id=user_id)
    await db.commit()
