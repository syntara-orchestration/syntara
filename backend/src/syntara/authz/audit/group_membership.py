"""Group membership domain events and audit handlers.

Emits audit trail events for adding and removing users from groups.
Group membership is an authorization-relevant change: members inherit
roles assigned to the group.

Requirements: AAP-83643
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlmodel import col, select

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models import Group

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass
class GroupMembershipEvent:
    """Domain event fired when a user is added to or removed from a group."""

    user_id: UUID
    username: str
    group_id: UUID
    group_name: str
    action: str  # "added" | "removed"
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Shared dispatch helpers
# ---------------------------------------------------------------------------


async def dispatch_membership_diff_events(
    db: AsyncSession,
    *,
    user_id: UUID,
    username: str,
    added: set[UUID],
    removed: set[UUID],
) -> None:
    """Emit GroupMembershipEvent for each membership added or removed."""
    if not added and not removed:
        return

    changed_ids = added | removed
    name_result = await db.exec(select(Group.id, Group.name).where(col(Group.id).in_(changed_ids)))
    group_names = dict(name_result.all())
    for gid in added:
        AuditEventDispatcher.dispatch(
            GroupMembershipEvent(
                user_id=user_id,
                username=username,
                group_id=gid,
                group_name=group_names.get(gid, str(gid)),
                action="added",
            ),
        )
    for gid in removed:
        AuditEventDispatcher.dispatch(
            GroupMembershipEvent(
                user_id=user_id,
                username=username,
                group_id=gid,
                group_name=group_names.get(gid, str(gid)),
                action="removed",
            ),
        )


# ---------------------------------------------------------------------------
# Audit handlers (produce AuditEvent for persistence)
# ---------------------------------------------------------------------------


class GroupMembershipHandler(AuditEventHandler[GroupMembershipEvent]):
    """Maps a GroupMembershipEvent to an AuditEvent."""

    def handle(self, event: GroupMembershipEvent) -> AuditEvent:
        """Map a GroupMembershipEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None
        severity = EventSeverity.ERROR if is_error else EventSeverity.INFO

        data = AuditContextData(
            data_type="group-membership",
            action=event.action,
            username=event.username,
            group_name=event.group_name,
            user_id=str(event.user_id),
            group_id=str(event.group_id),
        )
        if is_error:
            data.error_type = event.error_type

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=severity,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action=f"group_member_{event.action}",
            event_message=f"Group member {event.action}: {event.username} -> group {event.group_name}",
            source_component="syntara.authz",
            structured_data=data,
            resource_urn=f"urn:syntara:group-membership:{event.group_id}:{event.user_id}",
            resource_name=event.group_name,
        )
