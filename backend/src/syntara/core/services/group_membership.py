"""Group membership service for authorization and access control.

Provides shared functionality to check if a user belongs to specified groups.
Used across multiple domains (approvals, RBAC, notifications, etc.).
"""

from uuid import UUID

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import Group
from syntara.core.models.group import user_groups


class GroupMembershipService:
    """Service for checking user group membership.

    Provides reusable group membership checks for authorization decisions
    across all domains in the system.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service with database session.

        Args:
            session: SQLModel async database session

        """
        self.session = session

    async def is_user_in_any_group(self, user_id: UUID, group_names: list[str]) -> bool:
        """Check if user belongs to any of the specified groups (by name).

        Args:
            user_id: ID of the user to check
            group_names: List of group names to check membership in

        Returns:
            True if user is a member of at least one group, False otherwise

        Note:
            - Returns False if group_names is empty
            - Group names are case-sensitive
            - Only checks non-deleted groups

        """
        if not group_names:
            return False

        # Query groups the user belongs to that match any of the group_names
        stmt = (
            select(Group)
            .join(user_groups, Group.id == user_groups.c.group_id)  # type: ignore[arg-type]
            .where(user_groups.c.user_id == user_id)
            .where(Group.name.in_(group_names))  # type: ignore[attr-defined]
            .where(Group.deleted_at.is_(None))  # type: ignore[union-attr]
        )
        result = await self.session.execute(stmt)
        groups = result.scalars().all()

        return len(groups) > 0

    async def is_user_in_any_group_by_ids(self, user_id: UUID, group_ids: list[UUID]) -> bool:
        """Check if user belongs to any of the specified groups (by ID).

        More efficient than name-based lookup when group IDs are already known.
        Commonly used with FK-based authorization systems.

        Args:
            user_id: ID of the user to check
            group_ids: List of group IDs to check membership in

        Returns:
            True if user is a member of at least one group, False otherwise

        Note:
            - Returns False if group_ids is empty
            - Only checks non-deleted groups

        """
        if not group_ids:
            return False

        # Query groups the user belongs to that match any of the group_ids
        stmt = (
            select(Group)
            .join(user_groups, Group.id == user_groups.c.group_id)  # type: ignore[arg-type]
            .where(user_groups.c.user_id == user_id)
            .where(Group.id.in_(group_ids))  # type: ignore[attr-defined]
            .where(Group.deleted_at.is_(None))  # type: ignore[union-attr]
        )
        result = await self.session.execute(stmt)
        groups = result.scalars().all()

        return len(groups) > 0
