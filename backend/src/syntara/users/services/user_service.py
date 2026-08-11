"""User service layer for business logic.

This service encapsulates user-related business logic, separating it from
HTTP/API concerns in the FastAPI endpoints.
"""

from collections.abc import Iterable
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy import insert as sa_insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.auth.exceptions import (
    AdminDeleteError,
    AdminDisableNoOtherAdminsError,
    AdminModifyError,
    GroupNamesNotFoundError,
    PasswordOnFederatedUserError,
    UserEmailConflictError,
    UserUsernameConflictError,
)
from syntara.auth.passwords import hash_password
from syntara.authz.audit.group_membership import GroupMembershipEvent
from syntara.authz.resolver import AUTHENTICATED_GROUP_NAME
from syntara.core.lib.sanitization import strip_control_chars
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups
from syntara.core.models.user import AuthType
from syntara.core.models.user_identity import UserIdentity
from syntara.core.models.user_schemas import (
    UserListResponse,
    UserRead,
)
from syntara.core.queries.user_queries import get_user_by_id
from syntara.core.services import BaseService
from syntara.core.services.extensions import ConvertResourceMixin
from syntara.identity_providers.models.identity_provider import IdentityProvider


class _Sentinel(Enum):
    UNSET = "UNSET"


UNSET = _Sentinel.UNSET


class UserConvertResourceMixin(ConvertResourceMixin):
    """User-specific resource conversion to UserRead format."""

    def convert_resource(self, resource: User) -> UserRead:  # type: ignore[override]
        """Convert User to UserRead format."""
        read = UserRead.model_validate(resource)
        if resource.auth_type == AuthType.LOCAL:
            read.auth_sources = ["Local"]
        return read


class UsersService(BaseService):
    """Service for user business logic.

    This service encapsulates all user-related business operations,
    including CRUD operations and duplicate handling.
    """

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize UsersService with database session and user context."""
        super().__init__(session, user, convert_resource_mixin=UserConvertResourceMixin())

    async def to_read(self, user: User) -> UserRead:
        """Convert a User model to UserRead response."""
        result: UserRead = self.convert_resource_mixin.convert_resource(user)
        if user.auth_type == AuthType.FEDERATED:
            identity_result = await self.session.exec(
                select(IdentityProvider.name)
                .join(UserIdentity, col(UserIdentity.identity_provider_id) == IdentityProvider.id)
                .where(
                    col(UserIdentity.user_id) == user.id,
                )
            )
            result.auth_sources = sorted(identity_result.all())
        return result

    def _is_duplicate_username_error(self, e: IntegrityError) -> bool:
        """Check if IntegrityError is due to duplicate username.

        Args:
            e: The IntegrityError to check

        Returns:
            True if error is due to duplicate username constraint

        """
        error_str = str(e)
        return "ix_users_username_unique" in error_str or "Key (username)" in error_str

    def _is_duplicate_email_error(self, e: IntegrityError) -> bool:
        """Check if IntegrityError is due to duplicate email.

        Args:
            e: The IntegrityError to check

        Returns:
            True if error is due to duplicate email constraint

        """
        error_str = str(e)
        return "ix_users_email_unique" in error_str or "Key (email)" in error_str

    async def _commit_with_duplicate_check(self, username: str, email: str | None = None) -> None:
        """Commit database transaction with duplicate error handling.

        Args:
            username: Username of user being created/updated
            email: Email of user being created/updated

        Raises:
            UserUsernameConflictError: If duplicate username constraint violated
            UserEmailConflictError: If duplicate email constraint violated
            IntegrityError: For other integrity constraint violations

        """
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            if self._is_duplicate_username_error(e):
                raise UserUsernameConflictError(username) from e
            if self._is_duplicate_email_error(e):
                raise UserEmailConflictError(email or "") from e
            raise

    async def create_user(
        self,
        username: str,
        first_name: str,
        password: str,
        *,
        last_name: str | None = None,
        email: str | None = None,
        is_enabled: bool = True,
        group_names: list[str] | None = None,
    ) -> User:
        """Create a new local user.

        Args:
            username: Unique username
            first_name: User's first name
            password: Plaintext password (will be hashed)
            last_name: User's last name (optional)
            email: Email address (optional)
            is_enabled: Account activation status
            group_names: Groups to assign. None = use setting default, [] = no groups.

        Returns:
            Created user

        Raises:
            UserUsernameConflictError: If username already exists

        """
        username = username.lower()

        user = User(
            id=uuid4(),
            username=username,
            email=email.lower() if email else None,
            first_name=first_name,
            last_name=last_name,
            password_hash=hash_password(password),
            is_enabled=is_enabled,
        )

        self.session.add(user)
        await self._commit_with_duplicate_check(username, email=user.email)
        await self.session.refresh(user)

        explicit = group_names is not None
        resolved_names = list(group_names) if group_names is not None else []

        # Always include the authenticated group
        if AUTHENTICATED_GROUP_NAME not in resolved_names:
            resolved_names.append(AUTHENTICATED_GROUP_NAME)

        result = await self.session.exec(select(Group).where(col(Group.name).in_(resolved_names)))
        groups = list(result.all())
        found_names = {g.name for g in groups}
        if AUTHENTICATED_GROUP_NAME not in found_names:
            msg = f"Required built-in group '{AUTHENTICATED_GROUP_NAME}' is missing from the database"
            raise RuntimeError(msg)
        if explicit:
            missing = [n for n in (group_names or []) if n not in found_names]
            if missing:
                raise GroupNamesNotFoundError(missing)
        if groups:
            await self.session.exec(
                sa_insert(user_groups).values([{"user_id": user.id, "group_id": g.id} for g in groups])
            )
            await self.session.commit()
            for group in groups:
                AuditEventDispatcher.dispatch(
                    GroupMembershipEvent(
                        user_id=user.id,
                        username=user.username,
                        group_id=group.id,
                        group_name=group.name,
                        action="added",
                    ),
                )

        return user

    async def list_users_cursor(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
        id_restriction: list[UUID] | None = None,
    ) -> UserListResponse:
        """List users with filtering, sorting, and pagination.

        Args:
            limit: Maximum number of users to return (default 20)
            cursor: Cursor token for pagination
            sort: Sort parameter (e.g., "username", "-created_at")
            query_params_items: Raw query parameter items from request (for filtering)
            include_total: Whether to include total count in response
            id_restriction: Optional list of allowed user IDs to filter by

        Returns:
            UserListResponse with users, pagination metadata, and optional total

        """
        auth_source: str | None = None
        filtered_params: list[tuple[str, str]] = []
        if query_params_items:
            for key, value in query_params_items:
                if key == "auth_source":
                    auth_source = value
                else:
                    filtered_params.append((key, value))

        if auth_source:
            if auth_source == "Local":
                filtered_params.append(("auth_type", "local"))
            else:
                provider_user_ids = await self._get_user_ids_by_provider_name(auth_source)
                if id_restriction is not None:
                    allowed = set(provider_user_ids)
                    id_restriction = [uid for uid in id_restriction if uid in allowed]
                else:
                    id_restriction = provider_user_ids

        response = await self.list_resources(
            model=User,
            response_type=UserListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort or "-created_at",
            query_params_items=filtered_params,
            include_total=include_total,
            id_restriction=id_restriction,
        )

        await self._populate_auth_sources(response)
        return response

    async def _get_user_ids_by_provider_name(self, provider_name: str) -> list[UUID]:
        """Get user IDs linked to a specific identity provider by name."""
        result = await self.session.exec(
            select(UserIdentity.user_id)
            .join(IdentityProvider, col(IdentityProvider.id) == UserIdentity.identity_provider_id)
            .where(
                col(IdentityProvider.name) == provider_name,
            )
        )
        return list(result.all())

    async def _populate_auth_sources(self, response: UserListResponse) -> None:
        """Batch-populate auth_sources for federated users in a list response."""
        federated_ids = [r.id for r in response.resources if r.auth_type == AuthType.FEDERATED]
        if not federated_ids:
            return

        result = await self.session.exec(
            select(UserIdentity.user_id, IdentityProvider.name)
            .join(IdentityProvider, col(IdentityProvider.id) == UserIdentity.identity_provider_id)
            .where(
                col(UserIdentity.user_id).in_(federated_ids),
            )
        )
        provider_map: dict[UUID, list[str]] = {}
        for user_id, provider_name in result.all():
            provider_map.setdefault(user_id, []).append(provider_name)

        for user_read in response.resources:
            if user_read.id in provider_map:
                user_read.auth_sources = sorted(provider_map[user_read.id])

    async def get_user_by_id(self, user_id: UUID) -> User:
        """Get a user by ID.

        Args:
            user_id: User UUID

        Returns:
            User instance

        Raises:
            UserNotFoundError: If user not found or deleted

        """
        return await get_user_by_id(self.session, user_id)

    async def update_user(
        self,
        user_id: UUID,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None | _Sentinel = UNSET,
        email: str | None = None,
        password: str | None = None,
        *,
        is_enabled: bool | None = None,
    ) -> User:
        """Update user fields.

        Args:
            user_id: UUID of user to update
            username: New username (optional)
            first_name: New first name (optional)
            last_name: New last name, pass None to clear, omit to keep (optional)
            email: New email (optional)
            password: New plaintext password (optional, will be hashed)
            is_enabled: New activation status (optional)

        Returns:
            Updated user

        Raises:
            UserNotFoundError: If user not found
            UserUsernameConflictError: If new username conflicts

        """
        target_user = await self.get_user_by_id(user_id)

        # Protect built-in users: only the builtin admin itself can modify its properties.
        # Other admins can only re-enable the account (is_enabled=True with no other changes).
        if target_user.is_builtin:
            self._guard_builtin_update(
                is_self=self.user.id == target_user.id,
                is_enabled=is_enabled,
                username=username,
                first_name=first_name,
                last_name=last_name,
                email=email,
                password=password,
            )

        # Prevent disabling a user if it would leave no enabled admins.
        # Note: _guard_builtin_update allows the builtin admin to set is_enabled=False
        # on itself, but this check catches it if no other admins remain.
        if is_enabled is False:
            await self._ensure_other_admins_exist(exclude_user_id=user_id)

        if password is not None and target_user.auth_type == AuthType.FEDERATED:
            raise PasswordOnFederatedUserError(user_id)

        updates = self._build_update_fields(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=password,
            is_enabled=is_enabled,
        )
        for attr, value in updates.items():
            setattr(target_user, attr, value)

        if updates:
            target_user.updated_at = datetime.now(UTC)

        await self._commit_with_duplicate_check(target_user.username, email=target_user.email)
        await self.session.refresh(target_user)

        return target_user

    async def delete_user(self, user_id: UUID) -> None:
        """Soft delete a user.

        Args:
            user_id: UUID of user to delete

        Raises:
            UserNotFoundError: If user not found

        """
        user = await self.get_user_by_id(user_id)
        if user.is_builtin:
            raise AdminDeleteError
        await self._ensure_other_admins_exist(exclude_user_id=user_id)
        user.soft_delete(self.user.id)
        await self.session.commit()

    @staticmethod
    def _build_update_fields(
        *,
        username: str | None,
        first_name: str | None,
        last_name: str | None | _Sentinel,
        email: str | None,
        password: str | None,
        is_enabled: bool | None,
    ) -> dict[str, Any]:
        """Build a dict of fields to update on the user model."""
        updates: dict[str, Any] = {}
        if username is not None:
            updates["username"] = strip_control_chars(username).lower()
        if first_name is not None:
            updates["first_name"] = strip_control_chars(first_name)
        if last_name is not UNSET:
            updates["last_name"] = strip_control_chars(last_name) if last_name else last_name
        if email is not None:
            updates["email"] = strip_control_chars(email).lower()
        if password is not None:
            updates["password_hash"] = hash_password(password)
        if is_enabled is not None:
            updates["is_enabled"] = is_enabled
        return updates

    @staticmethod
    def _guard_builtin_update(
        *,
        is_self: bool,
        is_enabled: bool | None,
        username: str | None,
        first_name: str | None,
        last_name: str | None | _Sentinel,
        email: str | None,
        password: str | None,
    ) -> None:
        """Enforce modification rules for the built-in admin user."""
        last_name_changed = last_name is not UNSET
        if is_self:
            # Self can do anything except change protected fields
            if any(field is not None for field in (username, first_name, email)) or last_name_changed:
                raise AdminModifyError
            return
        # Non-self: only re-enabling is allowed (is_enabled=True, nothing else)
        if (
            is_enabled is not True
            or any(field is not None for field in (username, first_name, email, password))
            or last_name_changed
        ):
            raise AdminModifyError

    async def _ensure_other_admins_exist(self, exclude_user_id: UUID | None = None) -> None:
        """Raise if disabling/deleting this user would leave no enabled admins.

        Skips the check if the user is not in the admins group.

        Args:
            exclude_user_id: User being disabled/deleted (excluded from count).
                             If None, checks total count without exclusion.

        """
        # Lock the admins group row to serialize concurrent disable/delete
        # operations, preventing a race where two requests both see enough
        # admins and then both disable, leaving zero.
        await self.session.exec(
            select(Group)
            .where(
                col(Group.name) == "admins",
                col(Group.is_builtin).is_(True),
            )
            .with_for_update()
        )

        query = (
            select(func.count())
            .select_from(user_groups)
            .join(Group, col(Group.id) == user_groups.c.group_id)
            .join(User, col(User.id) == user_groups.c.user_id)
            .where(
                col(Group.name) == "admins",
                col(Group.is_builtin).is_(True),
                User.deleted_at.is_(None),  # type: ignore[union-attr]
                col(User.is_enabled).is_(True),
            )
        )
        if exclude_user_id is not None:
            query = query.where(col(User.id) != exclude_user_id)

        result = await self.session.exec(query)
        if result.one() < 1:
            raise AdminDisableNoOtherAdminsError
