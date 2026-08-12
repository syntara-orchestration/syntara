"""Webhook authentication audit events.

Fired when an external caller attempts to invoke a webhook/EDA trigger endpoint.
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
from syntara.core.models.principal import PrincipalType

if TYPE_CHECKING:
    from uuid import UUID


@dataclass
class WebhookAuthSuccessEvent:
    """Fired when a service account successfully authenticates to a webhook trigger."""

    service_account_id: UUID
    webhook_path: str
    trigger_type: str
    workflow_id: UUID


class WebhookAuthSuccessHandler(AuditEventHandler[WebhookAuthSuccessEvent]):
    """Maps a WebhookAuthSuccessEvent to an AuditEvent."""

    def handle(self, event: WebhookAuthSuccessEvent) -> AuditEvent:
        """Map to a normalized AuditEvent."""
        data = AuditContextData(data_type="webhook-auth-success")
        data.trigger_type = event.trigger_type

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="webhook_auth_success",
            event_message=f"SA {event.service_account_id} authenticated for webhook '{event.webhook_path}'",
            source_component="syntara.workflows.webhook_router",
            structured_data=data,
            workflow_id=event.workflow_id,
            resource_urn=f"urn:syntara:webhook:{event.webhook_path}",
            resource_name=event.webhook_path,
            actor_id=event.service_account_id,
            actor_type=PrincipalType.SERVICE_ACCOUNT,
        )


@dataclass
class WebhookAuthFailureEvent:
    """Fired when webhook authentication fails."""

    webhook_path: str
    trigger_type: str
    failure_reason: str
    service_account_id: UUID | None = field(default=None)


class WebhookAuthFailureHandler(AuditEventHandler[WebhookAuthFailureEvent]):
    """Maps a WebhookAuthFailureEvent to an AuditEvent."""

    def handle(self, event: WebhookAuthFailureEvent) -> AuditEvent:
        """Map to a normalized AuditEvent."""
        data = AuditContextData(data_type="webhook-auth-failure")
        data.trigger_type = event.trigger_type

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="webhook_auth_failure",
            event_message=(f"Webhook auth failed for '{event.webhook_path}': {event.failure_reason}"),
            source_component="syntara.workflows.webhook_router",
            structured_data=data,
            resource_urn=f"urn:syntara:webhook:{event.webhook_path}",
            resource_name=event.webhook_path,
        )
