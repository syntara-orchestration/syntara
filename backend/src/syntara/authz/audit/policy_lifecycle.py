"""Policy lifecycle domain events and audit handlers.

Emits audit trail events for policy create, update, and delete operations.

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
class PolicyLifecycleEvent:
    """Domain event fired when a policy is created, updated, or deleted."""

    policy_id: UUID
    policy_name: str
    action: str  # "created" | "updated" | "deleted"
    project_id: UUID | None = field(default=None)
    affected_roles_count: int = field(default=0)
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Audit handlers (produce AuditEvent for persistence)
# ---------------------------------------------------------------------------


class PolicyLifecycleHandler(AuditEventHandler[PolicyLifecycleEvent]):
    """Maps a PolicyLifecycleEvent to an AuditEvent."""

    def handle(self, event: PolicyLifecycleEvent) -> AuditEvent:
        """Map a PolicyLifecycleEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None

        severity = EventSeverity.INFO
        if is_error:
            severity = EventSeverity.ERROR
        elif event.action == "deleted" and event.affected_roles_count > 0:
            severity = EventSeverity.WARNING

        data = AuditContextData(
            data_type="policy-lifecycle",
            action=event.action,
            policy_name=event.policy_name,
        )
        if event.affected_roles_count > 0:
            data.affected_roles_count = event.affected_roles_count
        if is_error:
            data.error_type = event.error_type

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=severity,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action=f"policy_{event.action}",
            event_message=f"Policy {event.action}: {event.policy_name}",
            source_component="syntara.authz",
            structured_data=data,
            resource_urn=f"urn:syntara:policy:{event.policy_id}",
            resource_name=event.policy_name,
        )
