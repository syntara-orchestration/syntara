"""Approval domain events and audit handlers.

Emits audit trail events for HitL approval requests and decisions.

Requirements: AAP-72358, AAP-72359
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
from syntara.audit.utils import resolve_actor_type
from syntara.core.models.principal import PrincipalType

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID


_SOURCE_COMPONENT = "syntara.approvals"

# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass
class ApprovalRequestedEvent:
    """Domain event fired when a HitL approval request is created."""

    approval_id: UUID
    execution_id: UUID
    approval_node_id: str
    name: str
    project_id: UUID | None = field(default=None)
    timeout_at: datetime | None = field(default=None)


@dataclass
class ApprovalDecidedEvent:
    """Domain event fired when a HitL approval is approved or rejected."""

    approval_id: UUID
    execution_id: UUID
    approval_node_id: str
    decision: str  # "approved" or "rejected"
    decided_by: UUID
    decided_at: datetime
    wait_time_ms: int  # ms between request creation and decision
    decision_notes: str | None = field(default=None)
    principal_type: PrincipalType | None = field(default=None)


@dataclass
class ApprovalDecisionDeniedEvent:
    """Domain event fired when a user is denied an approval decision.

    Covers approver-list denials (user has permission but is not in the
    approval's approver_users/groups) for both single and batch endpoints.
    """

    approval_id: UUID
    execution_id: UUID
    approval_node_id: str
    user_id: UUID
    username: str
    action: str = field(default="decide")
    principal_type: PrincipalType | None = field(default=None)


@dataclass
class ApprovalExpiredEvent:
    """Domain event fired when a pending approval request expires due to decision window timeout."""

    approval_id: UUID
    execution_id: UUID
    approval_node_id: str


# ---------------------------------------------------------------------------
# Audit handlers (produce AuditEvent for persistence)
# ---------------------------------------------------------------------------


class ApprovalRequestedHandler(AuditEventHandler[ApprovalRequestedEvent]):
    """Maps an ApprovalRequestedEvent to an AuditEvent."""

    def handle(self, event: ApprovalRequestedEvent) -> AuditEvent:
        """Map an ApprovalRequestedEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="approval-requested",
            name=event.name,
        )

        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="approval_requested",
            event_message=f"Approval requested: {event.name}",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            execution_id=event.execution_id,
            activity_id=event.approval_node_id,
            resource_urn=f"urn:syntara:approval:{event.approval_id}",
            resource_name=event.approval_node_id,
        )


class ApprovalExpiredHandler(AuditEventHandler[ApprovalExpiredEvent]):
    """Maps an ApprovalExpiredEvent to an AuditEvent."""

    def handle(self, event: ApprovalExpiredEvent) -> AuditEvent:
        """Map an ApprovalExpiredEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="approval-expired",
        )

        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.SUCCESS,
            event_action="approval_expired",
            event_message="Approval request expired due to decision window timeout",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            actor_type=PrincipalType.SYSTEM,
            execution_id=event.execution_id,
            activity_id=event.approval_node_id,
            resource_urn=f"urn:syntara:approval:{event.approval_id}",
            resource_name=event.approval_node_id,
        )


class ApprovalDecisionDeniedHandler(AuditEventHandler[ApprovalDecisionDeniedEvent]):
    """Maps an ApprovalDecisionDeniedEvent to a SECURITY_EVENT AuditEvent."""

    def handle(self, event: ApprovalDecisionDeniedEvent) -> AuditEvent:
        """Map an ApprovalDecisionDeniedEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="authorization-denied",
            resource_type="approval",
            action=event.action,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="authorization_denied",
            event_message=f"Authorization denied: {event.action} on approval",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            actor_id=event.user_id,
            actor_type=resolve_actor_type(actor_id=event.user_id, principal_type=event.principal_type),
            actor_username=event.username,
            execution_id=event.execution_id,
            activity_id=event.approval_node_id,
            resource_urn=f"urn:syntara:approval:{event.approval_id}",
            resource_name=event.approval_node_id,
        )


class ApprovalDecidedHandler(AuditEventHandler[ApprovalDecidedEvent]):
    """Maps an ApprovalDecidedEvent to an AuditEvent."""

    def handle(self, event: ApprovalDecidedEvent) -> AuditEvent:
        """Map an ApprovalDecidedEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="approval-decided",
            decision=event.decision,
            wait_time_ms=event.wait_time_ms,
        )

        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="approval_decided",
            event_message=f"Approval {event.decision}",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            actor_id=event.decided_by,
            actor_type=resolve_actor_type(actor_id=event.decided_by, principal_type=event.principal_type),
            execution_id=event.execution_id,
            activity_id=event.approval_node_id,
            resource_urn=f"urn:syntara:approval:{event.approval_id}",
            resource_name=event.approval_node_id,
        )
