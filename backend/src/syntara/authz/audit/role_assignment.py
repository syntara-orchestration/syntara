"""Role assignment domain events and audit handlers.

Emits audit trail events for role assignment and revocation.

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
class RoleAssignmentEvent:
    """Domain event fired when a role is assigned to or revoked from a principal.

    Exactly one of (principal_id, principal_name, principal_type) or
    (group_id, group_name) is populated — mirrors the XOR constraint on
    the RoleAssignment model.
    """

    assignment_id: UUID
    role_name: str
    action: str  # "assigned" | "revoked"
    principal_id: UUID | None = field(default=None)
    principal_type: str | None = field(default=None)
    principal_name: str | None = field(default=None)
    group_id: UUID | None = field(default=None)
    group_name: str | None = field(default=None)
    project_id: UUID | None = field(default=None)
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Audit handlers (produce AuditEvent for persistence)
# ---------------------------------------------------------------------------


class RoleAssignmentHandler(AuditEventHandler[RoleAssignmentEvent]):
    """Maps a RoleAssignmentEvent to an AuditEvent."""

    def handle(self, event: RoleAssignmentEvent) -> AuditEvent:
        """Map a RoleAssignmentEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None
        severity = EventSeverity.ERROR if is_error else EventSeverity.INFO

        is_group = event.group_id is not None
        if is_group:
            target_label = f"group {event.group_name}" if event.group_name else "group"
        elif event.principal_type and event.principal_name:
            target_label = f"{event.principal_type} {event.principal_name}"
        else:
            target_label = "principal"

        data = AuditContextData(
            data_type="role-assignment",
            action=event.action,
            role_name=event.role_name,
        )
        if is_group:
            data.group_name = event.group_name
        elif event.principal_type:
            data.principal_type = event.principal_type
            data.principal_name = event.principal_name
        if event.project_id is not None:
            data.project_id = str(event.project_id)
        if is_error:
            data.error_type = event.error_type

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=severity,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action=f"role_{event.action}",
            event_message=f"Role {event.action}: {event.role_name} -> {target_label}",
            source_component="syntara.authz",
            structured_data=data,
            resource_urn=f"urn:syntara:role-assignment:{event.assignment_id}",
            resource_name=event.role_name,
        )
