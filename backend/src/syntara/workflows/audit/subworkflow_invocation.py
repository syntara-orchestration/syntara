"""Audit events for Reference-mode Sub-workflow invocations."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class SubWorkflowInvocationEvent:
    """A Reference-mode child execution was created for a parent invocation."""

    actor_id: UUID
    parent_workflow_id: UUID
    parent_execution_id: UUID
    parent_node_id: str
    child_workflow_id: UUID
    child_execution_id: UUID


class SubWorkflowInvocationHandler(AuditEventHandler[SubWorkflowInvocationEvent]):
    """Map a successful Sub-workflow invocation to a queryable audit record."""

    def handle(self, event: SubWorkflowInvocationEvent) -> AuditEvent:
        """Normalize a successful invocation for the shared audit pipeline."""
        data = AuditContextData(
            data_type="subworkflow-invocation",
            parent_workflow_id=str(event.parent_workflow_id),
            parent_execution_id=str(event.parent_execution_id),
            parent_node_id=event.parent_node_id,
            child_workflow_id=str(event.child_workflow_id),
            child_execution_id=str(event.child_execution_id),
            mode="reference",
            status="success",
        )
        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="subworkflow_invocation",
            event_message="Sub-workflow reference invocation accepted",
            source_component="syntara.workflows",
            structured_data=data,
            actor_id=event.actor_id,
            workflow_id=event.parent_workflow_id,
            execution_id=event.parent_execution_id,
            resource_urn=f"urn:syntara:workflow:{event.child_workflow_id}",
        )


@dataclass
class SubWorkflowAuthorizationDeniedEvent:
    """The actor was denied permission to invoke a child workflow."""

    actor_id: UUID
    parent_workflow_id: UUID
    parent_execution_id: UUID
    parent_node_id: str
    child_workflow_id: UUID
    denial_reason: str


class SubWorkflowAuthorizationDeniedHandler(AuditEventHandler[SubWorkflowAuthorizationDeniedEvent]):
    """Map a Sub-workflow authorization denial to a security audit record."""

    def handle(self, event: SubWorkflowAuthorizationDeniedEvent) -> AuditEvent:
        """Normalize an authorization denial for the shared audit pipeline."""
        data = AuditContextData(
            data_type="subworkflow-authorization-denied",
            parent_workflow_id=str(event.parent_workflow_id),
            parent_execution_id=str(event.parent_execution_id),
            parent_node_id=event.parent_node_id,
            child_workflow_id=str(event.child_workflow_id),
            denial_reason=event.denial_reason,
            mode="reference",
            status="denied",
        )
        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="subworkflow_authorization_denied",
            event_message="Sub-workflow invocation authorization denied",
            source_component="syntara.workflows",
            structured_data=data,
            actor_id=event.actor_id,
            workflow_id=event.parent_workflow_id,
            execution_id=event.parent_execution_id,
            resource_urn=f"urn:syntara:workflow:{event.child_workflow_id}",
        )
