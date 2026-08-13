"""Approver resolution activity for converting usernames/group names to UUIDs.

This activity resolves string-based approver configurations from workflow
definitions into UUID-based approver lists for the Approvals API.
"""

from typing import TYPE_CHECKING

import structlog
from temporalio import activity, workflow

if TYPE_CHECKING:
    from uuid import UUID

with workflow.unsafe.imports_passed_through():
    from syntara.core.database.session import get_db
    from syntara.workflows.workflow_engine.services.approver_resolution import ApproverResolutionService

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name="resolve_approvers")
async def resolve_approvers_activity(
    approver_users: list[str] | None,
    approver_groups: list[str] | None,
) -> dict[str, list[str]]:
    """Resolve approver usernames and group names to UUIDs.

    Args:
        approver_users: List of usernames to resolve (None = no user restriction)
        approver_groups: List of group names to resolve (None = no group restriction)

    Returns:
        Dict with:
        - "user_ids": List of UUID strings for resolved users
        - "group_ids": List of UUID strings for resolved groups

    Note:
        Non-existent usernames/groups are silently filtered out.

    """
    logger.info(
        "Resolving approvers to UUIDs",
        approver_users=approver_users,
        approver_groups=approver_groups,
    )

    # Initialize variables before loop to handle case where get_db() yields no sessions
    user_ids: list[UUID] = []
    group_ids: list[UUID] = []

    async for session in get_db():
        service = ApproverResolutionService(session)

        if approver_users:
            user_ids = await service.resolve_usernames_to_ids(approver_users)

        if approver_groups:
            group_ids = await service.resolve_group_names_to_ids(approver_groups)

    # Convert UUIDs to strings for JSON serialization
    result = {
        "user_ids": [str(uid) for uid in user_ids],
        "group_ids": [str(gid) for gid in group_ids],
    }

    logger.info(
        "Resolved approvers to UUIDs",
        user_count=len(user_ids),
        group_count=len(group_ids),
    )

    return result
