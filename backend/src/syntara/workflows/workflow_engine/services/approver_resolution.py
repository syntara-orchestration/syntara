"""Approver resolution service for converting usernames/group names to UUIDs.

Provides functionality to resolve string-based approver configurations
from workflow definitions into UUID-based approver lists for the Approvals API.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlmodel import select

from syntara.core.models import Group, User

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)


class ApproverResolutionService:
    """Service for resolving approver usernames and group names to UUIDs."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service with database session.

        Args:
            session: SQLModel async database session

        """
        self.session = session

    def _log_filtered_approvers(self, resolved_count: int, requested_count: int, resource_type: str) -> None:
        """Log warning when approvers are filtered out due to deletion or non-existence.

        Args:
            resolved_count: Number of approvers successfully resolved
            requested_count: Number of approvers requested
            resource_type: Type of resource being resolved ("users" or "groups")

        """
        logger.warning(
            "Approver resolution filtered out non-existent %s: "
            "%d/%d %s resolved. "
            "If all approvers are filtered, approval will fall back to "
            "AC5 (any user with approval:decide permission).",
            resource_type,
            resolved_count,
            requested_count,
            resource_type,
        )

    async def resolve_usernames_to_ids(self, usernames: list[str]) -> list[UUID]:
        """Resolve list of usernames to user IDs.

        Args:
            usernames: List of usernames to resolve

        Returns:
            List of UUIDs for users that exist (silently filters non-existent users)

        Note:
            - Returns empty list if usernames is empty or None
            - Usernames are case-sensitive
            - Non-existent usernames are filtered out (no error raised)

        SECURITY: Silent filtering is intentional and safe. Workflow definitions store
        usernames (portable across environments), which may become stale if users are
        deleted. Filtering ensures workflows remain executable even with stale references.
        When all approvers filtered out, approval falls back to AC5 (any user with
        approval:decide permission), which is validated at the endpoint level.

        """
        if not usernames:
            return []

        stmt = (
            select(User.id)
            .where(User.username.in_(usernames))  # type: ignore[attr-defined]
            .where(User.deleted_at.is_(None))  # type: ignore[union-attr]
        )
        result = await self.session.execute(stmt)
        user_ids = result.scalars().all()

        # Log warning if any usernames were filtered out (deleted/non-existent users)
        if len(user_ids) < len(usernames):
            self._log_filtered_approvers(len(user_ids), len(usernames), "users")

        return list(user_ids)

    async def resolve_group_names_to_ids(self, group_names: list[str]) -> list[UUID]:
        """Resolve list of group names to group IDs.

        Args:
            group_names: List of group names to resolve

        Returns:
            List of UUIDs for groups that exist (silently filters non-existent groups)

        Note:
            - Returns empty list if group_names is empty or None
            - Group names are case-sensitive
            - Non-existent groups are filtered out (no error raised)
            - Only returns IDs for non-deleted groups

        SECURITY: Silent filtering is intentional and safe. Workflow definitions store
        group names (portable across environments), which may become stale if groups are
        deleted or renamed. Filtering ensures workflows remain executable even with stale
        references. When all approvers filtered out, approval falls back to AC5 (any user
        with approval:decide permission), which is validated at the endpoint level.

        """
        if not group_names:
            return []

        stmt = (
            select(Group.id)
            .where(Group.name.in_(group_names))  # type: ignore[attr-defined]
            .where(Group.deleted_at.is_(None))  # type: ignore[union-attr]
        )
        result = await self.session.execute(stmt)
        group_ids = result.scalars().all()

        # Log warning if any group names were filtered out (deleted/non-existent groups)
        if len(group_ids) < len(group_names):
            self._log_filtered_approvers(len(group_ids), len(group_names), "groups")

        return list(group_ids)
