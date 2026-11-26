"""Sanitized record-rejection events for the existing platform audit pipeline."""

from dataclasses import dataclass

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType
from syntara.eventstreams.core.deduplication import DeliveryIdentity
from syntara.eventstreams.core.results import EventFailureCode


@dataclass
class EventRecordRejectedEvent:
    """A content classification; emitting this event never grants commit permission."""

    identity: DeliveryIdentity
    configuration_revision: int
    error_code: EventFailureCode


class EventRecordRejectedHandler(AuditEventHandler[EventRecordRejectedEvent]):
    """Map a rejection to the platform's sanitized OTEL audit contract."""

    def handle(self, event: EventRecordRejectedEvent) -> AuditEvent:
        """Include bounded coordinates and fixed error codes, never record contents."""
        identity = event.identity
        return AuditEvent(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_severity=EventSeverity.ERROR,
            event_status=EventStatus.ERROR,
            event_action="event_subscription_record_rejected",
            event_message="Event subscription record rejected",
            source_component="syntara.eventstreams.processing",
            actor_type=PrincipalType.SYSTEM,
            workflow_id=identity.workflow_id,
            resource_urn=f"urn:syntara:event-subscription:{identity.subscription_id}",
            structured_data=AuditContextData(
                data_type="event-subscription-record-rejection",
                subscription_id=str(identity.subscription_id),
                source_id=str(identity.source_id),
                source_generation=identity.source_generation,
                configuration_revision=event.configuration_revision,
                record=identity.record.model_dump(mode="json"),
                error_code=event.error_code.value,
            ),
        )
