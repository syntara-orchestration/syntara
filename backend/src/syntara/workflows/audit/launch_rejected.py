"""Audit event for a workflow launch rejected by authorization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData

if TYPE_CHECKING:
    from syntara.workflows.node_launch_checks import WorkflowLaunchRejection


@dataclass(frozen=True)
class WorkflowLaunchRejectedEvent:
    """One rejected launch with its complete decision context."""

    rejection: WorkflowLaunchRejection


class WorkflowLaunchRejectedHandler(AuditEventHandler[WorkflowLaunchRejectedEvent]):
    """Map the launch rejection to one structured security audit event."""

    def handle(self, event: WorkflowLaunchRejectedEvent) -> AuditEvent:
        """Return the normalized audit record."""
        rejection = event.rejection
        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="workflow.launch_rejected",
            event_message=f"Workflow launch rejected: {rejection.reason}",
            source_component="syntara.workflows",
            structured_data=AuditContextData(
                data_type="workflow-launch-rejected",
                code="WORKFLOW_LAUNCH_REJECTED",
                reason=rejection.reason,
                principal_id=str(rejection.principal_id),
                project_id=str(rejection.project_id),
                trigger_type=rejection.trigger_type,
                denied_steps=rejection.denied_steps,
                denied_by=rejection.denied_by,
            ),
            actor_id=rejection.principal_id,
            workflow_id=None,
            resource_urn=f"urn:syntara:project:{rejection.project_id}",
        )
