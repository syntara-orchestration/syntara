"""Workflow lifecycle — domain event and audit handler.

Fired by WorkflowService when a user creates, updates, deletes, publishes,
unpublishes, or restores a workflow definition. These are user-initiated
CRUD actions (category: USER_ACTION), not runtime execution events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
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


class WorkflowAction(StrEnum):
    """Actions that can occur during a workflow lifecycle."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    RESTORED = "restored"


@dataclass
class WorkflowLifecycleEvent:
    """Domain event fired when a workflow lifecycle action completes."""

    workflow_id: UUID
    workflow_name: str
    action: WorkflowAction
    actor_id: UUID | None = field(default=None)
    version: int | None = field(default=None)
    project_id: UUID | None = field(default=None)
    error_type: str | None = field(default=None)
    referencing_parent_ids: list[UUID] | None = field(default=None)


class WorkflowLifecycleHandler(AuditEventHandler[WorkflowLifecycleEvent]):
    """Maps a WorkflowLifecycleEvent to an AuditEvent."""

    def handle(self, event: WorkflowLifecycleEvent) -> AuditEvent:
        """Map a WorkflowLifecycleEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None

        data = AuditContextData(
            data_type="workflow-lifecycle",
            action=event.action,
            workflow_name=event.workflow_name,
        )
        if event.version is not None:
            data.version = event.version
        if event.project_id is not None:
            data.project_id = str(event.project_id)
        if is_error:
            data.error_type = event.error_type
        if event.referencing_parent_ids:
            # Internal audit record of which published parents referenced a deleted workflow.
            # Unfiltered by visibility on purpose; this is the audit log, not a public API response.
            data.referencing_parent_ids = [str(parent_id) for parent_id in event.referencing_parent_ids]
            data.referencing_parent_count = len(event.referencing_parent_ids)

        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=EventSeverity.ERROR if is_error else EventSeverity.INFO,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action=f"workflow_{event.action}",
            event_message=f"Workflow {event.action}: {event.workflow_name}",
            source_component="syntara.workflows",
            structured_data=data,
            actor_id=event.actor_id,
            workflow_id=event.workflow_id,
            resource_urn=f"urn:syntara:workflow:{event.workflow_id}",
            resource_name=event.workflow_name,
        )
