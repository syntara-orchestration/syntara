"""EventSubscriptionLifecycleEvent and handler for publication sync audit.

Sanitized lifecycle audit: identifiers and counts only, never event payloads,
credentials, topics or group identifiers. Authoritative state lives in the
database; this audit record (and any optional post-commit hint) is advisory.
"""

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData

_OPERATIONAL_LOGS_HINT = "See operational logs for details."

# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass
class EventSubscriptionLifecycleEvent:
    """Domain event summarizing one workflow publication's subscription projection.

    ``action`` is the publication operation (for example ``"published"`` or
    ``"unpublished"``). ``error_type`` is None on success or the technical
    exception class name on failure.
    """

    workflow_id: UUID
    action: str
    created_count: int = field(default=0)
    updated_count: int = field(default=0)
    retired_count: int = field(default=0)
    disabled_count: int = field(default=0)
    error_type: str | None = field(default=None)


@dataclass(frozen=True)
class EventSubscriptionStateChangedEvent:
    """An individual subscription transition in the publication transaction."""

    workflow_id: UUID
    subscription_id: UUID
    actor_id: UUID
    action: Literal["created", "enabled", "disabled", "retired"]
    configuration_revision: int


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class EventSubscriptionStateChangedHandler(AuditEventHandler[EventSubscriptionStateChangedEvent]):
    """Record the desired state change using identifiers only."""

    def handle(self, event: EventSubscriptionStateChangedEvent) -> AuditEvent:
        """Describe a specific subscription transition without its settings."""
        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_status=EventStatus.SUCCESS,
            event_action=f"event_subscription_{event.action}",
            event_message=f"Event subscription {event.action}",
            source_component="syntara.eventstreams.subscription",
            resource_urn=f"urn:syntara:event-subscription:{event.subscription_id}",
            actor_id=event.actor_id,
            workflow_id=event.workflow_id,
            structured_data=AuditContextData(
                data_type="event-subscription-state-change",
                subscription_id=str(event.subscription_id),
                configuration_revision=event.configuration_revision,
            ),
        )


class EventSubscriptionLifecycleHandler(AuditEventHandler[EventSubscriptionLifecycleEvent]):
    """Maps an EventSubscriptionLifecycleEvent to a normalized AuditEvent."""

    def handle(self, event: EventSubscriptionLifecycleEvent) -> AuditEvent:
        """Map an EventSubscriptionLifecycleEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None

        if is_error:
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = f"Event subscription sync failed for workflow {event.workflow_id}"
            error_message: str | None = _OPERATIONAL_LOGS_HINT
        else:
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Event subscriptions synced for workflow {event.workflow_id}"
            error_message = None

        data = AuditContextData(
            data_type="event-subscription-lifecycle-context",
            error_type=event.error_type,
            error_message=error_message,
            action=event.action,
            created_count=event.created_count,
            updated_count=event.updated_count,
            retired_count=event.retired_count,
            disabled_count=event.disabled_count,
        )

        return AuditEvent(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_severity=severity,
            event_status=status,
            event_action="event_subscriptions_synced",
            event_message=message,
            source_component="syntara.eventstreams.subscription",
            structured_data=data,
            resource_urn=f"urn:syntara:workflow:{event.workflow_id}",
            workflow_id=event.workflow_id,
        )
