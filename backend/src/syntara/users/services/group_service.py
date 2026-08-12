"""Group service layer for business logic.

This service encapsulates group-related business logic, separating it from
HTTP/API concerns in the FastAPI endpoints.
"""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import Select, delete, func, insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.auth.exceptions import (
    BuiltinGroupDeleteError,
    GroupNameConflictError,
    GroupNotFoundError,
    LastAdminRemovalError,
    UserAlreadyInGroupError,
    UserNotInGroupError,
)
from syntara.authz.audit.group_membership import (
    GroupMembershipEvent,
    dispatch_membership_diff_events,
)
from syntara.authz.resolver import AUTHENTICATED_GROUP_NAME
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.models.group import (
    Group,
    GroupListResponse,
    GroupRead,
    MembershipSource,
    UserGroupListResponse,
    UserGroupRead,
    user_groups,
    user_idp_groups,
)
from syntara.core.models.user import AuthType
from syntara.core.models.user_identity import UserIdentity
from syntara.core.models.user_schemas import GroupMemberListResponse, GroupMemberRead
from syntara.core.queries.user_queries import get_user_by_id
from syntara.core.services import BaseService
from syntara.core.services.extensions import ConvertResourceMixin
from syntara.core.utils.filters import Filter
from syntara.identity_providers.models.identity_provider import IdentityProvider


class GroupConvertResourceMixin(ConvertResourceMixin):
    """Group-specific resource conversion to GroupRead format."""

    def convert_resource(self, resource: Group) -> GroupRead:  # type: ignore[override]
        """Convert Group to GroupRead format."""
        return GroupRead.model_validate(resource)


logger = structlog.stdlib.get_logger(__name__)


class GroupsService(BaseService):
    """Service for group business logic.

    This service encapsulates all group-related business operations,
    including CRUD operations and duplicate name handling.
    """

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize GroupsService with database session and user context."""
        super().__init__(session, user, convert_resource_mixin=GroupConvertResourceMixin())

    def _is_duplicate_name_error(self, e: IntegrityError) -> bool:
        """Check if IntegrityError is due to duplicate group name.

        Args:
            e: The IntegrityError to check

        Returns:
            True if error is due to duplicate group name constraint

        """
        error_str = str(e)
        return (
            "ix_groups_name_unique" in error_str or "groups.name" in error_str or "duplicate key" in error_str.lower()
        )

    async def _commit_with_duplicate_check(self, group_name: str) -> None:
        """Commit database transaction with duplicate name error handling.

        Args:
            group_name: Name of group being created/updated

        Raises:
            GroupNameConflictError: If duplicate name constraint violated
            IntegrityError: For other integrity constraint violations

        """
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            if self._is_duplicate_name_error(e):
                raise GroupNameConflictError(group_name) from e
            raise

    async def get_member_counts(self, group_ids: list[UUID]) -> dict[UUID, int]:
        """Get member counts for a batch of groups."""
        if not group_ids:
            return {}

        result = await self.session.exec(
            select(user_groups.c.group_id, func.count())
            .join(User, User.id == user_groups.c.user_id)  # type: ignore[arg-type]
            .where(
                user_groups.c.group_id.in_(group_ids),
                User.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .group_by(user_groups.c.group_id)
        )
        return dict(result.all())

    async def get_member_count(self, group: Group) -> int:
        """Get member count for a single group."""
        counts = await self.get_member_counts([group.id])
        return counts.get(group.id, 0)

    def enrich_group_read(self, group: Group, member_count: int = 0) -> GroupRead:
        """Convert Group to GroupRead with member_count."""
        group_read = GroupRead.model_validate(group)
        group_read.member_count = member_count
        return group_read

    async def create_group(
        self,
        name: str,
        description: str | None,
    ) -> Group:
        """Create a new group.

        Args:
            name: Group name (must be unique among non-deleted groups)
            description: Optional group description

        Returns:
            Created group

        Raises:
            GroupNameConflictError: If group name already exists

        """
        group = Group(
            id=uuid4(),
            name=name,
            description=description,
            created_by=self.user.id,
        )

        self.session.add(group)
        await self._commit_with_duplicate_check(name)
        await self.session.refresh(group)

        return group

    @staticmethod
    def _get_special_field_handlers() -> dict[str, Any]:
        """Get special field handlers for group-specific filtering."""

        def handle_created_by_name(
            query: Select[tuple[Group]], filter_obj: Filter, _model: type[Group]
        ) -> Select[tuple[Group]]:
            """Filter groups by creator's username (joins User table)."""
            joined = query.join(User, col(Group.created_by) == col(User.id))
            value = str(filter_obj.value)
            if filter_obj.operator.value == "contains":
                return joined.filter(col(User.username).ilike(f"%{value}%"))
            if filter_obj.operator.value == "starts_with":
                return joined.filter(col(User.username).ilike(f"{value}%"))
            return joined.filter(col(User.username) == value)

        return {"created_by_name": handle_created_by_name}

    async def list_groups_cursor(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
        id_restriction: list[UUID] | None = None,
    ) -> GroupListResponse:
        """List groups with filtering, sorting, and pagination.

        Args:
            limit: Maximum number of groups to return (default 20)
            cursor: Cursor token for pagination
            sort: Sort parameter (e.g., "name", "-created_at")
            query_params_items: Raw query parameter items from request (for filtering)
            include_total: Whether to include total count in response
            id_restriction: Optional list of allowed group IDs to filter by

        Returns:
            GroupListResponse with groups, pagination metadata, and optional total

        """
        response = await self.list_resources(
            model=Group,
            response_type=GroupListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort or "-created_at",
            special_field_handlers=self._get_special_field_handlers(),
            query_params_items=query_params_items,
            include_total=include_total,
            id_restriction=id_restriction,
        )

        # Enrich with member counts
        if response.resources:
            group_ids = [r.id for r in response.resources]
            counts = await self.get_member_counts(group_ids)
            for resource in response.resources:
                resource.member_count = counts.get(resource.id, 0)

        return response

    async def get_group_by_id(self, group_id: UUID) -> Group:
        """Get a group by ID.

        Args:
            group_id: Group UUID

        Returns:
            Group instance

        Raises:
            GroupNotFoundError: If group not found or deleted

        """
        result = await self.session.exec(
            select(Group).filter(
                Group.id == group_id,  # type: ignore[arg-type]
                Group.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        group = result.one_or_none()

        if not group:
            raise GroupNotFoundError(group_id)

        return group

    async def update_group(
        self,
        group_id: UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> Group:
        """Update group fields.

        Args:
            group_id: UUID of group to update
            name: New name (optional)
            description: New description (optional)

        Returns:
            Updated group

        Raises:
            GroupNotFoundError: If group not found
            GroupNameConflictError: If new name conflicts
            SafeValueError: If name is empty

        """
        group = await self.get_group_by_id(group_id)

        has_changes = False

        if name is not None:
            if not name:
                msg = "Group name cannot be empty"
                raise SafeValueError(msg)
            group.name = name
            has_changes = True

        if description is not None:
            group.description = description
            has_changes = True

        if has_changes:
            group.updated_at = datetime.now(UTC)

        await self._commit_with_duplicate_check(group.name)
        await self.session.refresh(group)

        return group

    async def delete_group(self, group_id: UUID) -> None:
        """Soft delete a group.

        Args:
            group_id: UUID of group to delete

        Raises:
            GroupNotFoundError: If group not found
            BuiltinGroupDeleteError: If group is a builtin system group

        """
        group = await self.get_group_by_id(group_id)
        if group.is_builtin:
            raise BuiltinGroupDeleteError(group.name)
        group.soft_delete(self.user.id)
        await self.session.commit()

    # ========================================================================
    # Membership operations
    # ========================================================================

    async def add_member(self, group_id: UUID, user_id: UUID) -> None:
        """Add a user to a group.

        Args:
            group_id: UUID of the group
            user_id: UUID of the user to add

        Raises:
            GroupNotFoundError: If group not found
            UserNotFoundError: If user not found
            UserAlreadyInGroupError: If user is already a member

        """
        # Validate group and user exist
        group = await self.get_group_by_id(group_id)
        user = await get_user_by_id(self.session, user_id)

        # Check if membership already exists
        # Race condition note (TOCTOU): a concurrent request could insert the
        # same membership between this SELECT and the INSERT below.  The
        # composite primary key constraint on user_groups(user_id, group_id)
        # will raise IntegrityError in that case, which we catch and convert
        # to the appropriate user-facing error.
        result = await self.session.exec(
            select(user_groups.c.user_id).where(
                user_groups.c.user_id == user_id,
                user_groups.c.group_id == group_id,
            )
        )
        if result.one_or_none() is not None:
            raise UserAlreadyInGroupError(user_id, group_id)

        # Insert membership
        try:
            await self.session.exec(insert(user_groups).values(user_id=user_id, group_id=group_id))
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            raise UserAlreadyInGroupError(user_id, group_id) from e

        AuditEventDispatcher.dispatch(
            GroupMembershipEvent(
                user_id=user_id,
                username=user.username,
                group_id=group_id,
                group_name=group.name,
                action="added",
            ),
        )

    async def remove_member(self, group_id: UUID, user_id: UUID) -> None:
        """Remove a user from a group.

        Args:
            group_id: UUID of the group
            user_id: UUID of the user to remove

        Raises:
            GroupNotFoundError: If group not found
            UserNotFoundError: If user not found
            UserNotInGroupError: If user is not a member

        """
        # Validate group and user exist
        group = await self.get_group_by_id(group_id)
        user = await get_user_by_id(self.session, user_id)

        # Builtin users cannot be removed from builtin groups
        if user.is_builtin and group.is_builtin:
            raise LastAdminRemovalError

        # Check membership exists
        result = await self.session.exec(
            select(user_groups.c.user_id).where(
                user_groups.c.user_id == user_id,
                user_groups.c.group_id == group_id,
            )
        )
        if result.one_or_none() is None:
            raise UserNotInGroupError(user_id, group_id)

        # Prevent removing the last enabled admin from the admins group
        await self._guard_last_admin_removal(group_id, exclude_user_id=user_id)

        # Delete membership
        await self.session.exec(
            delete(user_groups).where(
                user_groups.c.user_id == user_id,
                user_groups.c.group_id == group_id,
            )
        )
        await self.session.commit()

        AuditEventDispatcher.dispatch(
            GroupMembershipEvent(
                user_id=user_id,
                username=user.username,
                group_id=group_id,
                group_name=group.name,
                action="removed",
            ),
        )

    async def list_members(
        self,
        group_id: UUID,
        limit: int = 20,
        cursor: str | None = None,
    ) -> GroupMemberListResponse:
        """List members of a group with cursor-based pagination.

        Includes membership source info (manual vs IdP) for each member.

        Args:
            group_id: UUID of the group
            limit: Maximum number of members to return
            cursor: Pagination cursor (user ID to start after)

        Returns:
            GroupMemberListResponse with group members and membership sources

        Raises:
            GroupNotFoundError: If group not found

        """
        # Validate group exists
        await self.get_group_by_id(group_id)

        # Build query for group members
        query = (
            select(User)
            .join(user_groups, User.id == user_groups.c.user_id)  # type: ignore[arg-type]
            .where(
                user_groups.c.group_id == group_id,
                User.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .order_by(col(User.username))
        )

        # Apply cursor if provided
        if cursor:
            query = query.where(col(User.username) > cursor)

        # Fetch N+1 to detect next page
        result = await self.session.exec(query.limit(limit + 1))
        users = list(result.all())

        has_next = len(users) > limit
        if has_next:
            users = users[:limit]

        next_cursor = users[-1].username if has_next and users else None

        # Fetch membership sources for all users in this group
        sources = await self._get_member_sources(group_id, [u.id for u in users])

        resources = []
        for u in users:
            read = GroupMemberRead.model_validate(u)
            if u.auth_type == AuthType.LOCAL:
                read.auth_sources = ["Local"]
            read.membership_sources = sources.get(u.id, [MembershipSource(type="manual")])
            resources.append(read)

        # Batch-populate auth_sources for federated users
        federated_ids = [r.id for r in resources if r.auth_type == AuthType.FEDERATED]
        if federated_ids:
            idp_result = await self.session.exec(
                select(UserIdentity.user_id, IdentityProvider.name)
                .join(
                    IdentityProvider,
                    col(IdentityProvider.id) == UserIdentity.identity_provider_id,
                )
                .where(
                    col(UserIdentity.user_id).in_(federated_ids),
                )
            )
            provider_map: dict[UUID, list[str]] = {}
            for uid, provider_name in idp_result.all():
                provider_map.setdefault(uid, []).append(provider_name)

            for member_read in resources:
                if member_read.id in provider_map:
                    member_read.auth_sources = sorted(provider_map[member_read.id])

        return GroupMemberListResponse(
            resources=resources,
            next=next_cursor,
        )

    async def list_user_groups(
        self,
        user_id: UUID,
        limit: int = 20,
        cursor: str | None = None,
    ) -> UserGroupListResponse:
        """List groups that a user belongs to with cursor-based pagination.

        Includes membership source info (manual assignment vs IdP auto-sync).

        Args:
            user_id: UUID of the user
            limit: Maximum number of groups to return
            cursor: Pagination cursor (group name to start after)

        Returns:
            UserGroupListResponse with user's groups and membership sources

        Raises:
            UserNotFoundError: If user not found

        """
        # Validate user exists
        await get_user_by_id(self.session, user_id)

        # Build query for user's groups
        query = (
            select(Group)
            .join(user_groups, Group.id == user_groups.c.group_id)  # type: ignore[arg-type]
            .where(
                user_groups.c.user_id == user_id,
                Group.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .order_by(col(Group.name))
        )

        # Apply cursor if provided
        if cursor:
            query = query.where(col(Group.name) > cursor)

        # Fetch N+1 to detect next page
        result = await self.session.exec(query.limit(limit + 1))
        groups = list(result.all())

        has_next = len(groups) > limit
        if has_next:
            groups = groups[:limit]

        next_cursor = groups[-1].name if has_next and groups else None

        # Fetch IdP sources for all groups in one query
        group_ids = [g.id for g in groups]
        sources = await self._get_membership_sources(user_id, group_ids)

        resources = []
        for g in groups:
            read = UserGroupRead.model_validate(g)
            read.membership_sources = sources.get(g.id, [MembershipSource(type="manual")])
            resources.append(read)

        return UserGroupListResponse(resources=resources, next=next_cursor)

    async def _get_membership_sources(
        self,
        user_id: UUID,
        group_ids: list[UUID],
    ) -> dict[UUID, list[MembershipSource]]:
        """Get membership sources for a user's groups.

        Returns a dict mapping group_id to list of MembershipSource.
        A group can have both manual and IdP sources simultaneously — e.g., when
        a user is manually assigned AND assigned by an identity provider.  If a
        group has no IdP tracking rows, it is considered manually assigned.
        """
        if not group_ids:
            return {}

        # Query IdP-managed group assignments with provider names
        idp_query = (
            select(
                user_idp_groups.c.group_id,
                col(IdentityProvider.id).label("provider_id"),
                col(IdentityProvider.name).label("provider_name"),
            )
            .join(
                IdentityProvider,
                user_idp_groups.c.identity_provider_id == IdentityProvider.id,
            )
            .where(
                user_idp_groups.c.user_id == user_id,
                user_idp_groups.c.group_id.in_(group_ids),
            )
        )
        idp_result = await self.session.exec(idp_query)

        sources: dict[UUID, list[MembershipSource]] = {}
        idp_managed_groups: set[UUID] = set()

        for gid, provider_id, provider_name in idp_result:
            idp_managed_groups.add(gid)
            sources.setdefault(gid, []).append(
                MembershipSource(type="idp", provider_name=provider_name, provider_id=provider_id)
            )

        # Groups without any IdP tracking rows are manually assigned.
        for gid in group_ids:
            if gid not in idp_managed_groups:
                sources.setdefault(gid, []).append(MembershipSource(type="manual"))

        return sources

    async def _get_member_sources(
        self,
        group_id: UUID,
        user_ids: list[UUID],
    ) -> dict[UUID, list[MembershipSource]]:
        """Get membership sources for users in a specific group.

        Returns a dict mapping user_id to list of MembershipSource.
        """
        if not user_ids:
            return {}

        idp_query = (
            select(
                user_idp_groups.c.user_id,
                col(IdentityProvider.id).label("provider_id"),
                col(IdentityProvider.name).label("provider_name"),
            )
            .join(IdentityProvider, user_idp_groups.c.identity_provider_id == IdentityProvider.id)
            .where(
                user_idp_groups.c.group_id == group_id,
                user_idp_groups.c.user_id.in_(user_ids),
            )
        )
        idp_result = await self.session.exec(idp_query)

        sources: dict[UUID, list[MembershipSource]] = {}
        idp_managed_users: set[UUID] = set()

        for uid, provider_id, provider_name in idp_result:
            idp_managed_users.add(uid)
            sources.setdefault(uid, []).append(
                MembershipSource(type="idp", provider_name=provider_name, provider_id=provider_id)
            )

        for uid in user_ids:
            if uid not in idp_managed_users:
                sources.setdefault(uid, []).append(MembershipSource(type="manual"))

        return sources

    async def set_user_groups(self, user_id: UUID, group_ids: list[UUID]) -> UserGroupListResponse:
        """Set a user's group memberships declaratively.

        Replace all current memberships with the provided list of group IDs.
        An empty list removes the user from all groups.

        Args:
            user_id: UUID of the user
            group_ids: Complete list of group IDs the user should belong to

        Returns:
            GroupListResponse with the user's updated groups

        Raises:
            UserNotFoundError: If user not found
            GroupNotFoundError: If any group ID does not exist

        """
        # Validate user exists
        user = await get_user_by_id(self.session, user_id)

        # Always include the authenticated group
        auth_result = await self.session.exec(
            select(Group.id).where(
                Group.name == AUTHENTICATED_GROUP_NAME,
                Group.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        auth_group_id = auth_result.first()
        if not auth_group_id:
            msg = f"Required built-in group '{AUTHENTICATED_GROUP_NAME}' is missing from the database"
            raise RuntimeError(msg)

        # Validate all desired groups exist (deduplicate first)
        desired = set(group_ids)
        desired.add(auth_group_id)
        result = await self.session.exec(
            select(Group.id).filter(
                col(Group.id).in_(desired),
                Group.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        found = set(result.all())
        missing = desired - found
        if missing:
            raise GroupNotFoundError(next(iter(missing)))

        # Get current memberships
        # Race condition note (TOCTOU): concurrent set_user_groups calls for
        # the same user could interleave between this SELECT and the
        # DELETE/INSERT below.  The composite PK on user_groups prevents
        # duplicate rows, and we catch IntegrityError to handle the rare
        # collision gracefully.  A SELECT ... FOR UPDATE on the membership
        # rows would serialise concurrent calls but adds lock contention;
        # the current approach is acceptable given the low frequency of
        # admin-initiated group changes.
        result = await self.session.exec(select(user_groups.c.group_id).where(user_groups.c.user_id == user_id))
        current = set(result.all())

        # Compute diff
        to_add = desired - current
        to_remove = current - desired

        # Remove old memberships
        if to_remove:
            # Block builtin users from being removed from builtin groups
            if user.is_builtin:
                builtin_result = await self.session.exec(
                    select(Group.id).where(
                        col(Group.id).in_(to_remove),
                        col(Group.is_builtin) == True,  # noqa: E712
                    )
                )
                if builtin_result.first() is not None:
                    raise LastAdminRemovalError

            # Check if any of the groups being removed is the admins group
            for gid in to_remove:
                await self._guard_last_admin_removal(gid, exclude_user_id=user_id)

            await self.session.exec(
                delete(user_groups).where(
                    user_groups.c.user_id == user_id,
                    user_groups.c.group_id.in_(to_remove),
                )
            )

        # Add new memberships
        if to_add:
            try:
                await self.session.exec(
                    insert(user_groups),
                    params=[{"user_id": user_id, "group_id": gid} for gid in to_add],
                )
            except IntegrityError:
                await self.session.rollback()
                # Rollback undoes both the DELETE and INSERT.  A concurrent
                # request modified memberships, so re-read the actual state
                # and return it rather than committing an empty transaction.
                logger.info(
                    "Concurrent group membership change, returning current state",
                    user_id=str(user_id),
                )
                return await self.list_user_groups(user_id)

        await self.session.commit()

        await self._dispatch_membership_diff_events(
            user_id=user_id,
            username=user.username,
            added=to_add,
            removed=to_remove,
        )

        # Return updated group list
        return await self.list_user_groups(user_id)

    async def _dispatch_membership_diff_events(
        self,
        *,
        user_id: UUID,
        username: str,
        added: set[UUID],
        removed: set[UUID],
    ) -> None:
        """Emit GroupMembershipEvent for each membership added or removed."""
        await dispatch_membership_diff_events(
            self.session,
            user_id=user_id,
            username=username,
            added=added,
            removed=removed,
        )

    async def _guard_last_admin_removal(self, group_id: UUID, *, exclude_user_id: UUID) -> None:
        """Raise if removing this user would leave no enabled admins in the group.

        Only applies to the builtin admins group. No-op for other groups.
        """
        # Check if this is the builtin admins group
        result = await self.session.exec(
            select(Group).where(
                col(Group.id) == group_id,
                col(Group.name) == "admins",
                col(Group.is_builtin) == True,  # noqa: E712
            )
        )
        if result.one_or_none() is None:
            return  # Not the admins group — no guard needed

        # Lock the group row to serialize concurrent removals
        await self.session.exec(select(Group).where(col(Group.id) == group_id).with_for_update())

        # Count remaining enabled admins excluding the user being removed
        count_result = await self.session.exec(
            select(func.count())
            .select_from(user_groups)
            .join(User, User.id == user_groups.c.user_id)  # type: ignore[arg-type]
            .where(
                user_groups.c.group_id == group_id,
                col(User.id) != exclude_user_id,
                User.deleted_at.is_(None),  # type: ignore[union-attr]
                col(User.is_enabled) == True,  # noqa: E712
            )
        )
        if count_result.one() < 1:
            raise LastAdminRemovalError
