"""Role lifecycle domain events and audit handlers.

Emits audit trail events for role create, update, and delete operations.

Requirements: AAP-73907
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData

if TYPE_CHECKING:
    from uuid import UUID


# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass
class RoleLifecycleEvent:
    """Domain event fired when a role is created, updated, or deleted."""

    role_id: UUID
    role_name: str
    action: str  # "created" | "updated" | "deleted"
    project_id: UUID | None = field(default=None)
    affected_assignments_count: int = field(default=0)
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Audit handlers (produce AuditEvent for persistence)
# ---------------------------------------------------------------------------


class RoleLifecycleHandler(AuditEventHandler[RoleLifecycleEvent]):
    """Maps a RoleLifecycleEvent to an AuditEvent."""

    def handle(self, event: RoleLifecycleEvent) -> AuditEvent:
        """Map a RoleLifecycleEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None

        severity = EventSeverity.INFO
        if is_error:
            severity = EventSeverity.ERROR
        elif event.action == "deleted" and event.affected_assignments_count > 0:
            severity = EventSeverity.WARNING

        data = AuditContextData(
            data_type="role-lifecycle",
            action=event.action,
            role_name=event.role_name,
        )
        if event.affected_assignments_count > 0:
            data.affected_assignments_count = event.affected_assignments_count
        if is_error:
            data.error_type = event.error_type

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=severity,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action=f"role_{event.action}",
            event_message=f"Role {event.action}: {event.role_name}",
            source_component="syntara.authz",
            structured_data=data,
            resource_urn=f"urn:syntara:role:{event.role_id}",
            resource_name=event.role_name,
        )
